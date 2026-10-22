"""Errors of the API and the HTTP status each one answers with.

Request handlers raise these plain exceptions; :func:`install_error_handlers`
turns them into ``{"detail": "..."}`` answers, the same shape FastAPI uses.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .stores import Forbidden, StoreNameError
from .times import TimeError
from .vm import VMUnavailable
from .vocabulary import VocabularyError, VocabularyUnavailable


class InvalidRequest(ValueError):
    """A request the API does not accept (HTTP 422)."""


class NotFound(LookupError):
    """Nothing matches (HTTP 404)."""


STATUS = {
    StoreNameError: 422,
    TimeError: 422,
    VocabularyError: 422,
    InvalidRequest: 422,
    Forbidden: 403,
    NotFound: 404,
    VocabularyUnavailable: 502,
    VMUnavailable: 502,
}


def _json_safe(value: Any) -> Any:
    """Replace NaN and infinities, which JSON cannot carry, by their names."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 answer, also for a body with NaN (FastAPI's own fails with 500)."""
    return JSONResponse(
        status_code=422, content={"detail": _json_safe(jsonable_encoder(error.errors()))}
    )


def install_error_handlers(app: FastAPI) -> None:
    """Answer each error of :data:`STATUS` with its status and its message."""
    app.add_exception_handler(RequestValidationError, _validation_error)

    def handler(status: int):
        async def handle(request: Request, error: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(error)})

        return handle

    for error_class, status in STATUS.items():
        app.add_exception_handler(error_class, handler(status))
