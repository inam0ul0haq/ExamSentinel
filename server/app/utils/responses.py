"""Reusable helpers that build the standard error envelope.

Every non-2xx response in the API shares the shape documented in
``docs/API.md`` §1.5::

    {
        "error": {
            "code":    "<snake_case>",
            "message": "<single human sentence>",
            "details": { ... }   # optional
        }
    }

Routes and decorators import the helpers below rather than open-coding
the envelope, so a single file owns the contract.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from flask import Response, jsonify, make_response


def error_response(
    code: str,
    message: str,
    status: int,
    details: Optional[Mapping[str, Any]] = None,
) -> Tuple[Response, int]:
    """Return a ``(jsonified_envelope, status)`` tuple.

    ``details`` is omitted from the payload when ``None`` so successful
    branches that don't carry contextual hints don't emit a ``"details": null``
    field clients would have to ignore.
    """
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return jsonify({"error": body}), status


def make_error_response(
    code: str,
    message: str,
    status: int,
    details: Optional[Mapping[str, Any]] = None,
) -> Response:
    """Return a fully-built ``Response`` (status baked in).

    Useful inside callbacks (e.g. Flask-JWT-Extended loaders) and helpers
    that need to call ``flask.abort`` with a response object rather than
    returning a tuple.
    """
    payload, http_status = error_response(code, message, status, details)
    return make_response(payload, http_status)


def validation_error(
    field_errors: Mapping[str, list],
    message: str = "Request body failed validation.",
) -> Tuple[Response, int]:
    """Shortcut for ``422 validation_failed`` with per-field ``details``."""
    return error_response(
        code="validation_failed",
        message=message,
        status=422,
        details=dict(field_errors),
    )


__all__ = ["error_response", "make_error_response", "validation_error"]
