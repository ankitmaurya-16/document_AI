"""Feedback (thumbs up/down) on assistant messages."""
from __future__ import annotations

from typing import Annotated

from flask import Blueprint, jsonify, request
from pydantic import Field, StringConstraints

from extensions import limiter
from logging_config import get_logger
from rag.auth import require_auth
from rag.database import insert_feedback
from schemas import _StrictModel, parse_json
from settings import get_settings

bp = Blueprint("feedback", __name__)
log = get_logger("routes.feedback")


class FeedbackIn(_StrictModel):
    chatId: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    messageTimestamp: float = Field(..., ge=0)
    rating: int = Field(..., ge=-1, le=1)
    comment: Annotated[str, StringConstraints(max_length=2000)] | None = None


@bp.post("")
@limiter.limit(lambda: get_settings().rate_limit_default)
@require_auth
def submit_feedback():
    payload = parse_json(FeedbackIn, request)
    if payload.rating == 0:
        # 0 is ambiguous (no-opinion). Treat as "undo" by writing 0.
        pass
    stored = insert_feedback(
        user_id=request.user_id,
        chat_id=payload.chatId,
        message_timestamp=payload.messageTimestamp,
        rating=payload.rating,
        comment=payload.comment,
    )
    log.info(
        "feedback.submitted",
        user_id=request.user_id,
        chat_id=payload.chatId,
        rating=payload.rating,
    )
    return jsonify(stored), 201
