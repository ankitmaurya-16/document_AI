"""RAG endpoints: query, streaming, async upload.

- ``/chat`` checks the exact + semantic cache before calling OpenAI.
- ``/chat/stream`` returns tokens via Server-Sent Events.
- ``/chat/upload`` can enqueue ingestion via Celery when ``ASYNC_MODE=celery``,
  returning a jobId the client can poll at ``/chat/jobs/<id>``.
"""
from __future__ import annotations

import json
import os
import uuid

from flask import Blueprint, Response, jsonify, request, stream_with_context

import cache
from errors import NotFoundError, PaymentRequiredError, ValidationError
from extensions import limiter
from logging_config import get_logger
from metrics import CREDIT_BURN
from rag.auth import optional_auth
from rag.database import (
    add_messages_to_chat,
    create_chat,
    get_recent_messages,
    get_user_by_id,
    insert_document,
    update_user_credits,
)
from rag.generate import generate_answer, generate_answer_stream
from rag.retrieve import embed_query, retrieve_top_chunks
from rag.user_store import paths_for, read_user_bytes, save_raw_file
from schemas import ChatIn, UploadPromptIn, parse_form, parse_json
from security import scan_for_malware, validate_uploads
from settings import get_settings
from tasks import ASYNC_MODE, enqueue_ingest, get_job_status

bp = Blueprint("rag", __name__)
log = get_logger("routes.rag")

_UPLOAD_TMP = os.getenv("UPLOAD_TMP_DIR", "/tmp/docai_uploads")  # nosec B108 - container-scoped scratch dir; overridable via env
os.makedirs(_UPLOAD_TMP, exist_ok=True)

# How many prior turns (user+assistant combined) to replay into the model for
# follow-up questions. Small number because each turn burns tokens.
_HISTORY_TURNS = int(os.getenv("CHAT_HISTORY_TURNS", "10"))


def _history_for(user_id: str | None, chat_id: str | None) -> list[dict]:
    if not user_id or not chat_id:
        return []
    return get_recent_messages(chat_id, limit=_HISTORY_TURNS)


def _check_credits(user_id: str | None):
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    if user and user.get("credits", 0) <= 0:
        raise PaymentRequiredError(
            "Credits exhausted. Please purchase more credits to continue using DocAI.",
        )
    return user


def _persist_chat_messages(
    *, user_id: str, chat_id: str | None, prompt: str, answer: str,
    file_names: list[str] | None, sources: list[str] | None = None,
) -> str:
    if not chat_id:
        user = get_user_by_id(user_id)
        user_name = user.get("name", "User") if user else "User"
        name = prompt[:30] + "..." if len(prompt) > 30 else prompt
        chat = create_chat(user_id, user_name, name)
        chat_id = chat["_id"]

    messages = [
        {
            "role": "user",
            "content": prompt,
            "files": file_names or [],
            "isImage": False,
            "isPublished": False,
        },
        {
            "role": "assistant",
            "content": answer,
            "sources": sources or [],
            "isImage": False,
            "isPublished": False,
        },
    ]
    add_messages_to_chat(chat_id, messages)
    return chat_id


def _retrieve_with_cache(user_id: str | None, prompt: str, top_k: int):
    """Returns (answer_or_none, chunks, embedding); embedding is computed once and
    reused for retrieval. On a cache hit, chunks is []."""
    exact = cache.get_exact(user_id, prompt, top_k)
    if exact:
        log.info("cache.exact.hit", user_id=user_id)
        return exact.answer, [], None

    q_emb = embed_query(prompt)
    sem = cache.semantic_get(user_id, q_emb)
    if sem:
        return sem.answer, [], q_emb

    chunks = retrieve_top_chunks(prompt, user_id=user_id, top_k=top_k)
    return None, chunks, q_emb


@bp.post("/chat")
@limiter.limit(lambda: get_settings().rate_limit_chat)
def chat():
    payload = parse_json(ChatIn, request)
    user_id = optional_auth()
    user = _check_credits(user_id)

    top_k = 5
    cached_answer, chunks, q_emb = _retrieve_with_cache(user_id, payload.prompt, top_k)
    history = _history_for(user_id, payload.chatId)
    sources: list[str] = []

    if cached_answer is not None:
        answer = cached_answer
        # Cache hit: semantic/exact caches also store the source list.
        cached_sources = cache.get_exact(user_id, payload.prompt, top_k)
        if cached_sources and getattr(cached_sources, "sources", None):
            sources = list(cached_sources.sources)
    elif not chunks:
        if history:
            answer = generate_answer(payload.prompt, [], history=history)
        else:
            answer = (
                "I don't have enough information to answer this question. "
                "Please upload documents first."
            )
    else:
        answer = generate_answer(payload.prompt, chunks, history=history)
        sources = sorted({c["source"] for c in chunks})
        cache.set_exact(user_id, payload.prompt, top_k, answer, sources)
        if q_emb is not None:
            cache.semantic_set(user_id, payload.prompt, q_emb, answer, sources)

    chat_id = payload.chatId
    if user_id:
        chat_id = _persist_chat_messages(
            user_id=user_id, chat_id=chat_id, prompt=payload.prompt, answer=answer,
            file_names=None, sources=sources,
        )
        credits = user.get("credits", 0) if user else 0
        if credits > 0:
            update_user_credits(user_id, credits - 1)
            CREDIT_BURN.labels(route="chat").inc()

    return jsonify({"response": answer, "chatId": chat_id, "sources": sources}), 200


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@bp.post("/chat/stream")
@limiter.limit(lambda: get_settings().rate_limit_chat)
def chat_stream():
    """Stream tokens as SSE frames: meta {chatId, sources}, token {text},
    done {answer}, error {message}."""
    payload = parse_json(ChatIn, request)
    user_id = optional_auth()
    user = _check_credits(user_id)

    top_k = 5
    cached_answer, chunks, q_emb = _retrieve_with_cache(user_id, payload.prompt, top_k)
    sources = sorted({c["source"] for c in chunks}) if chunks else (
        [] if cached_answer is None else []
    )
    history = _history_for(user_id, payload.chatId)

    # Pre-create chat id so clients can commit it even if the stream drops.
    chat_id = payload.chatId
    if user_id and not chat_id:
        user_obj = get_user_by_id(user_id)
        user_name = user_obj.get("name", "User") if user_obj else "User"
        name = payload.prompt[:30] + "..." if len(payload.prompt) > 30 else payload.prompt
        chat_id = create_chat(user_id, user_name, name)["_id"]

    @stream_with_context
    def generator():
        yield _sse("meta", {"chatId": chat_id, "sources": sources})

        collected: list[str] = []

        if cached_answer is not None:
            # Replay the cached answer as pseudo-tokens so UX is identical.
            for token in cached_answer.split(" "):
                collected.append(token + " ")
                yield _sse("token", {"text": token + " "})
            answer = cached_answer
        elif not chunks:
            if history:
                for delta in generate_answer_stream(payload.prompt, [], history=history):
                    collected.append(delta)
                    yield _sse("token", {"text": delta})
                answer = "".join(collected).strip()
            else:
                answer = (
                    "I don't have enough information to answer this question. "
                    "Please upload documents first."
                )
                yield _sse("token", {"text": answer})
        else:
            for delta in generate_answer_stream(payload.prompt, chunks, history=history):
                collected.append(delta)
                yield _sse("token", {"text": delta})
            answer = "".join(collected).strip()
            cache.set_exact(user_id, payload.prompt, top_k, answer, sources)
            if q_emb is not None:
                cache.semantic_set(user_id, payload.prompt, q_emb, answer, sources)

        if user_id:
            _persist_chat_messages(
                user_id=user_id,
                chat_id=chat_id,
                prompt=payload.prompt,
                answer=answer,
                file_names=None,
                sources=sources,
            )
            credits = user.get("credits", 0) if user else 0
            if credits > 0:
                update_user_credits(user_id, credits - 1)
                CREDIT_BURN.labels(route="chat_stream").inc()

        yield _sse("done", {"answer": answer, "chatId": chat_id})

    return Response(
        generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            "Connection": "keep-alive",
        },
    )


@bp.post("/chat/upload")
@limiter.limit(lambda: get_settings().rate_limit_upload)
def chat_upload():
    user_id = optional_auth()
    user = _check_credits(user_id)

    if "files" not in request.files:
        raise ValidationError("No files provided")
    payload = parse_form(UploadPromptIn, request.form)
    files = request.files.getlist("files")

    current_bytes = read_user_bytes(user_id)
    validated = validate_uploads(files, user_id=user_id, current_user_bytes=current_bytes)

    ns = paths_for(user_id).namespace
    saved_paths: list[str] = []
    file_names: list[str] = []
    total_new = 0
    for f, info in validated:
        dest = os.path.join(_UPLOAD_TMP, f"{ns}__{uuid.uuid4().hex}__{info.safe_name}")
        f.save(dest)
        scan_for_malware(dest)
        saved_paths.append(dest)
        file_names.append(info.original_name)
        total_new += info.size

        # Persist raw file + document record (per-user).
        if user_id:
            raw_path = save_raw_file(user_id, dest, info.original_name)
            insert_document(user_id, info.original_name, info.size, raw_path)

    # Sync mode: ingest inline, answer immediately (same UX as before).
    # Celery mode: enqueue and return jobId; the client polls and then asks.
    if ASYNC_MODE == "celery":
        job_id = enqueue_ingest(file_paths=saved_paths, total_bytes=total_new, user_id=user_id)
        return (
            jsonify({
                "jobId": job_id,
                "status": "queued",
                "poll": f"/api/v1/chat/jobs/{job_id}",
                "prompt": payload.prompt,
                "chatId": payload.chatId,
                "fileNames": file_names,
            }),
            202,
        )

    # Sync path: run the pipeline inline so single-shot uploads keep working.
    enqueue_ingest(file_paths=saved_paths, total_bytes=total_new, user_id=user_id)
    cache.invalidate_user(user_id)

    top_k = 5
    cached_answer, chunks, q_emb = _retrieve_with_cache(user_id, payload.prompt, top_k)
    history = _history_for(user_id, payload.chatId)
    if cached_answer is not None:
        answer = cached_answer
    elif not chunks:
        answer = "I don't have enough information to answer this question."
    else:
        answer = generate_answer(payload.prompt, chunks, history=history)
        sources = sorted({c["source"] for c in chunks})
        cache.set_exact(user_id, payload.prompt, top_k, answer, sources)
        if q_emb is not None:
            cache.semantic_set(user_id, payload.prompt, q_emb, answer, sources)

    chat_id = payload.chatId
    doc_sources = sorted({c["source"] for c in chunks}) if chunks else []
    if user_id:
        chat_id = _persist_chat_messages(
            user_id=user_id,
            chat_id=chat_id,
            prompt=payload.prompt,
            answer=answer,
            file_names=file_names,
            sources=doc_sources,
        )
        credits = user.get("credits", 0) if user else 0
        if credits > 0:
            update_user_credits(user_id, credits - 1)
            CREDIT_BURN.labels(route="chat_upload").inc()

    return jsonify({
        "response": answer,
        "chatId": chat_id,
        "sources": sorted({c["source"] for c in chunks}) if chunks else [],
    }), 200


@bp.post("/upload")
@limiter.limit(lambda: get_settings().rate_limit_upload)
def upload_files():
    user_id = optional_auth()
    if "files" not in request.files:
        raise ValidationError("No files provided")
    files = request.files.getlist("files")

    current_bytes = read_user_bytes(user_id)
    validated = validate_uploads(files, user_id=user_id, current_user_bytes=current_bytes)

    ns = paths_for(user_id).namespace
    saved_paths: list[str] = []
    total_new = 0
    for f, info in validated:
        dest = os.path.join(_UPLOAD_TMP, f"{ns}__{uuid.uuid4().hex}__{info.safe_name}")
        f.save(dest)
        scan_for_malware(dest)
        saved_paths.append(dest)
        total_new += info.size

        if user_id:
            raw_path = save_raw_file(user_id, dest, info.original_name)
            insert_document(user_id, info.original_name, info.size, raw_path)

    job_id = enqueue_ingest(file_paths=saved_paths, total_bytes=total_new, user_id=user_id)
    cache.invalidate_user(user_id)

    if ASYNC_MODE == "celery":
        return (
            jsonify({
                "message": "Ingestion queued",
                "jobId": job_id,
                "poll": f"/api/v1/chat/jobs/{job_id}",
            }),
            202,
        )
    return jsonify({"message": "Files ingested and index updated successfully", "jobId": job_id}), 200


@bp.get("/chat/jobs/<job_id>")
@limiter.limit(lambda: get_settings().rate_limit_default)
def job_status(job_id: str):
    state = get_job_status(job_id)
    if not state:
        raise NotFoundError("Job not found")
    return jsonify(state), 200
