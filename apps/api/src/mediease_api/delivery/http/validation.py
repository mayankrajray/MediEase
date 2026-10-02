"""Request body validation with Pydantic at the HTTP boundary (apps/api/CLAUDE.md "Patterns").

``parse_json(Model)`` accepts only ``application/json`` (415 otherwise — this
also keeps cross-site HTML forms out, since they cannot send JSON without a
CORS preflight), and turns validation errors into ``REQ_VALIDATION_FAILED``
listing each field and reason. Submitted values are never echoed back.
"""

from __future__ import annotations

from flask import request
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import UnsupportedMediaType

from mediease_api.domain.shared.errors import DomainError


class RequestValidationFailed(DomainError):
    code = "REQ_VALIDATION_FAILED"

    def __init__(self, fields: list[dict[str, str]]) -> None:
        super().__init__("Some fields are missing or not valid.")
        self.fields = fields


def parse_json[ModelT: BaseModel](model: type[ModelT]) -> ModelT:
    if not request.is_json:
        raise UnsupportedMediaType("Send the request body as application/json.")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise RequestValidationFailed([{"field": "<body>", "reason": "must be a JSON object"}])
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationFailed(
            [
                {"field": ".".join(str(p) for p in err["loc"]) or "<body>", "reason": err["msg"]}
                for err in exc.errors(include_input=False, include_url=False)
            ]
        ) from None
