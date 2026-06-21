"""Chat CRUD endpoints (ownership-checked)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import ForbiddenError, NotFoundError
from extensions import limiter
from rag.auth import require_auth
from rag.database import (
    add_messages_to_chat,
    create_chat,
    delete_chat,
    get_chat_by_id,
    get_user_by_id,
    get_user_chats,
    update_chat_name,
)
from schemas import CreateChatIn, UpdateChatIn, parse_json
from settings import get_settings

bp = Blueprint("chats", __name__)


@bp.get("")
@require_auth
@limiter.limit(lambda: get_settings().rate_limit_default)
def list_chats():
    return jsonify({"chats": get_user_chats(request.user_id)}), 200


@bp.post("")
@require_auth
@limiter.limit(lambda: get_settings().rate_limit_default)
def new_chat():
    payload = parse_json(CreateChatIn, request) if request.data else CreateChatIn()
    user = get_user_by_id(request.user_id)
    user_name = user.get("name", "User") if user else "User"
    chat = create_chat(request.user_id, user_name, payload.name)
    return jsonify({"chat": chat}), 201


def _owned_chat_or_raise(chat_id: str) -> dict:
    chat = get_chat_by_id(chat_id)
    if not chat:
        raise NotFoundError("Chat not found")
    if chat.get("userId") != request.user_id:
        raise ForbiddenError("You do not own this chat")
    return chat


@bp.get("/<chat_id>")
@require_auth
@limiter.limit(lambda: get_settings().rate_limit_default)
def single_chat(chat_id: str):
    chat = _owned_chat_or_raise(chat_id)
    return jsonify({"chat": chat}), 200


@bp.put("/<chat_id>")
@require_auth
@limiter.limit(lambda: get_settings().rate_limit_default)
def update_single_chat(chat_id: str):
    _owned_chat_or_raise(chat_id)
    payload = parse_json(UpdateChatIn, request)
    if payload.name is not None:
        update_chat_name(chat_id, payload.name)
    if payload.messages:
        add_messages_to_chat(chat_id, [m.model_dump() for m in payload.messages])
    return jsonify({"chat": get_chat_by_id(chat_id)}), 200


@bp.delete("/<chat_id>")
@require_auth
@limiter.limit(lambda: get_settings().rate_limit_default)
def delete_single_chat(chat_id: str):
    if not delete_chat(chat_id, request.user_id):
        raise NotFoundError("Chat not found")
    return jsonify({"message": "Chat deleted successfully"}), 200
