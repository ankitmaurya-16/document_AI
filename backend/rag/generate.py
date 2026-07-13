"""LLM generation — blocking and streaming variants."""
from __future__ import annotations

import os
from typing import Dict, Generator, List

from dotenv import load_dotenv
from openai import OpenAI

from logging_config import get_logger
from resilience import with_retry

try:
    from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError
    _OPENAI_RETRY_TYPES = (APIError, APIConnectionError, APITimeoutError, RateLimitError)
except ImportError:  # very old openai SDK or stub in tests
    _OPENAI_RETRY_TYPES = (Exception,)

_OPENAI_TIMEOUT_S = 30.0

load_dotenv()

log = get_logger("generate")

# Generation is provider-agnostic: any OpenAI-compatible endpoint works via
# OPENAI_BASE_URL (e.g. Groq, Gemini, a local Ollama). Defaults to OpenAI.
_DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    return _client


SYSTEM_PROMPT = (
    "You are a careful assistant. Answer the user's question using ONLY the "
    "provided context. You may use multiple context chunks. Cite sources like: "
    "[Source: filename]. If the answer is not contained in the context, say: "
    '"The documents don\'t have enough information to answer this question." '
    "When the user refers to earlier parts of this conversation (e.g. \"what did I just ask?\"), "
    "use the prior turns below in addition to the context."
)


def _context_block(context_chunks: List[Dict]) -> str:
    return "\n\n".join(
        f"[Source:{chunk['source']}]\n{chunk['text']}" for chunk in context_chunks
    )


def build_messages(
    question: str,
    context_chunks: List[Dict],
    history: List[Dict] | None = None,
) -> List[Dict]:
    """Build the OpenAI messages list: system prompt + prior turns + context+question."""
    context_text = _context_block(context_chunks)
    user_turn = (
        f"Context:\n{context_text}\n\nQuestion:\n{question}"
        if context_text
        else f"Question:\n{question}"
    )
    messages: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_turn})
    return messages


def build_prompt(question: str, context_chunks: List[Dict]) -> str:
    """Legacy helper kept for callers that want a single flat prompt string."""
    msgs = build_messages(question, context_chunks, history=None)
    return "\n\n".join(m["content"] for m in msgs)


@with_retry("openai", exception_types=_OPENAI_RETRY_TYPES)
def _openai_chat(**kwargs):
    return _openai().chat.completions.create(timeout=_OPENAI_TIMEOUT_S, **kwargs)


def generate_answer(
    question: str,
    context_chunks: List[Dict],
    history: List[Dict] | None = None,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.0,
) -> str:
    messages = build_messages(question, context_chunks, history=history)
    try:
        response = _openai_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=512,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        log.exception("generate.openai_failed", error=str(e))
        return "AI response temporarily unavailable."


def generate_answer_stream(
    question: str,
    context_chunks: List[Dict],
    history: List[Dict] | None = None,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.0,
) -> Generator[str, None, None]:
    """Yield response token deltas as they arrive from OpenAI."""
    messages = build_messages(question, context_chunks, history=history)
    try:
        stream = _openai_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=512,
            stream=True,
        )
        for event in stream:
            choice = event.choices[0] if event.choices else None
            if not choice:
                continue
            delta = getattr(choice.delta, "content", None)
            if delta:
                yield delta
    except Exception as e:
        log.exception("generate.stream_failed", error=str(e))
        yield "\n[AI response temporarily unavailable]"
