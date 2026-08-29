"""services.api.app.routes._errors — stable error envelope + exception handlers.

Every error response uses the contract envelope::

    { "error": { "code": str, "message": str } }

No stack trace, secret, DB URL, or internal SQL detail is ever surfaced
(DEC-011). :func:`register_exception_handlers` maps the db-layer signal
exceptions and FastAPI validation errors onto the envelope.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.db.connection import DatabaseUnavailable, NoData, NotFound

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """A handler-level error that maps directly to the stable envelope."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers that always emit the stable error envelope."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Contract: 400 invalid params (FastAPI defaults to 422).
        return JSONResponse(
            status_code=400,
            content=error_body("invalid_params", "One or more query parameters are invalid."),
        )

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_body("not_found", str(exc) or "Resource not found."),
        )

    @app.exception_handler(DatabaseUnavailable)
    async def _db_unavailable(_: Request, exc: DatabaseUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body("database_unavailable", "Database is not configured for this API."),
        )

    @app.exception_handler(NoData)
    async def _no_data(_: Request, exc: NoData) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body("no_data", "No valid precomputed data is available yet."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log details server-side only; never surface them.
        logger.exception("Unhandled error in API request")
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "Unexpected error."),
        )
