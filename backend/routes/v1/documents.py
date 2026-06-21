"""Document management: list, delete, re-ingest remaining docs."""
from __future__ import annotations

import tempfile

from flask import Blueprint, jsonify, request

import cache
from errors import NotFoundError
from extensions import limiter
from logging_config import get_logger
from rag.auth import require_auth
from rag.database import (
    delete_document,
    get_document,
    list_documents,
)
from rag.ingest import ingest_files
from rag.retrieve import reload_index
from rag.user_store import (
    list_raw_files,
    paths_for,
    remove_raw_file,
    wipe_namespace,
)
from rag.vector_store import get_store
from settings import get_settings
from storage import materialize_keys_to_dir

bp = Blueprint("documents", __name__)
log = get_logger("routes.documents")


@bp.get("")
@limiter.limit(lambda: get_settings().rate_limit_default)
@require_auth
def list_user_documents():
    docs = list_documents(request.user_id)
    return jsonify({"documents": docs}), 200


@bp.delete("/<doc_id>")
@limiter.limit(lambda: get_settings().rate_limit_default)
@require_auth
def delete_user_document(doc_id: str):
    user_id = request.user_id
    doc = get_document(user_id, doc_id)
    if not doc:
        raise NotFoundError("Document not found")

    # Look up the raw path directly from Mongo (list_documents strips it).
    from rag.database import get_database
    raw = get_database().documents.find_one({"_id": __import__("bson").ObjectId(doc_id), "userId": user_id})
    raw_path = raw.get("rawPath") if raw else None

    delete_document(user_id, doc_id)
    if raw_path:
        remove_raw_file(raw_path)

    # Re-ingest remaining files so the index reflects the deletion.
    remaining_keys = list_raw_files(user_id)
    if remaining_keys:
        # Storage keys may be local paths or s3:// URIs — materialize all of
        # them to a tmp dir so the ingest layer (which only knows local paths)
        # works against either backend.
        with tempfile.TemporaryDirectory(prefix="docai_reingest_") as tmpd:
            local_paths = materialize_keys_to_dir(remaining_keys, tmpd)
            ingest_files(local_paths, user_id=user_id)
        reload_index(user_id=user_id)
    else:
        # No docs left: clear vectors in the active backend AND the local
        # namespace dir (BM25 pickle, raw/ etc. live here even when the
        # vector backend is Qdrant).
        get_store().delete(paths_for(user_id).namespace)
        wipe_namespace(user_id)

    cache.invalidate_user(user_id)
    log.info("document.deleted", user_id=user_id, doc_id=doc_id, remaining=len(remaining_keys))
    return jsonify({"ok": True, "remaining": len(remaining_keys)}), 200
