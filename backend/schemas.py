"""Request-body schemas. Pydantic v2.

Route handlers use ``parse_json(Model)`` or ``parse_form(Model, request.form)``
to coerce, validate, and strip extra fields. Bad payloads raise
``pydantic.ValidationError`` which the registered error handler renders.
"""
from __future__ import annotations

import re
from typing import Annotated

from flask import Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from errors import ValidationError as AppValidationError

# Shared constraints
_NonEmptyStr = Annotated[str, StringConstraints(min_length=1, max_length=10_000, strip_whitespace=True)]
_ShortStr = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
_Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
_Name = Annotated[str, StringConstraints(min_length=2, max_length=100, strip_whitespace=True)]

# Strip control characters from incoming strings.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _scrub(s: str) -> str:
    return _CONTROL_CHARS.sub("", s)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterIn(_StrictModel):
    name: _Name
    email: EmailStr
    password: _Password


class LoginIn(_StrictModel):
    email: EmailStr
    password: _Password


class GoogleAuthIn(_StrictModel):
    access_token: Annotated[str, StringConstraints(min_length=10, max_length=4096)]


class CreateChatIn(_StrictModel):
    name: _ShortStr = "New Chat"


class UpdateChatIn(_StrictModel):
    name: _ShortStr | None = None
    messages: list["MessageIn"] | None = None


class MessageIn(_StrictModel):
    role: Annotated[str, StringConstraints(pattern=r"^(user|assistant|system)$")]
    content: _NonEmptyStr
    isImage: bool = False
    isPublished: bool = False
    files: list[_ShortStr] | None = None

    @field_validator("content")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _scrub(v)


UpdateChatIn.model_rebuild()


class ChatIn(_StrictModel):
    prompt: _NonEmptyStr = Field(..., max_length=8000)
    chatId: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None

    @field_validator("prompt")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _scrub(v)


def parse_json(model: type[BaseModel], request: Request) -> BaseModel:
    """Validate JSON body against ``model`` or raise."""
    if not request.is_json:
        raise AppValidationError("Request body must be JSON", code="bad_content_type")
    data = request.get_json(silent=True)
    if data is None:
        raise AppValidationError("Invalid or missing JSON body")
    return model.model_validate(data)


def parse_form(model: type[BaseModel], form_data) -> BaseModel:
    """Validate a werkzeug MultiDict against ``model``."""
    return model.model_validate({k: form_data.get(k) for k in form_data.keys()})


class UploadPromptIn(_StrictModel):
    """Form-based: multipart upload; ``files`` validated separately."""

    prompt: _NonEmptyStr = Field(..., max_length=8000)
    chatId: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None

    @field_validator("prompt")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _scrub(v)
