"""
HTTP client for the ExamSentinel REST API.

All public methods return ``(success, payload, error)`` so callers never
need to catch exceptions.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

from client.app.config import API_BASE_URL, REQUEST_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Error descriptor
# ---------------------------------------------------------------------------

@dataclass
class ErrorInfo:
    """Structured error information returned alongside failed requests."""
    http_status: Optional[int] = None
    code: str = "UNKNOWN"
    message: str = "An unknown error occurred."
    field_errors: Dict[str, List[str]] = field(default_factory=dict)


# Type alias for the standard return tuple.
ApiResult = Tuple[bool, Optional[Dict[str, Any]], Optional[ErrorInfo]]


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class ApiClient:
    """Thin wrapper around ``requests`` that normalises every failure into
    an ``(ok, payload, error)`` tuple."""

    def __init__(self, base_url: str = API_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._lock = threading.Lock()

    # -- token management ---------------------------------------------------

    def set_token(self, token: str) -> None:
        with self._lock:
            self._token = token

    def clear_token(self) -> None:
        with self._lock:
            self._token = None

    # -- public HTTP verbs --------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> ApiResult:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, body: Optional[Dict] = None, **kwargs: Any) -> ApiResult:
        return self._request("POST", path, json=body, **kwargs)

    def put(self, path: str, body: Optional[Dict] = None, **kwargs: Any) -> ApiResult:
        return self._request("PUT", path, json=body, **kwargs)

    def patch(self, path: str, body: Optional[Dict] = None, **kwargs: Any) -> ApiResult:
        return self._request("PATCH", path, json=body, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> ApiResult:
        return self._request("DELETE", path, **kwargs)

    # -- internals ----------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        with self._lock:
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> ApiResult:
        url = f"{self._base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
        kwargs.setdefault("headers", self._headers())

        try:
            resp = requests.request(method, url, **kwargs)
        except requests.ConnectionError:
            return (
                False,
                None,
                ErrorInfo(code="TRANSPORT", message="Cannot reach server."),
            )
        except requests.Timeout:
            return (
                False,
                None,
                ErrorInfo(code="TIMEOUT", message="Request timed out."),
            )
        except requests.RequestException as exc:
            return (
                False,
                None,
                ErrorInfo(code="TRANSPORT", message=str(exc)),
            )

        return self._process_response(resp)

    @staticmethod
    def _process_response(resp: requests.Response) -> ApiResult:
        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.ok:
            return (True, data, None)

        # Parse the server's error envelope.
        error = data.get("error", {}) if isinstance(data, dict) else {}
        return (
            False,
            None,
            ErrorInfo(
                http_status=resp.status_code,
                code=error.get("code", f"HTTP_{resp.status_code}"),
                message=error.get("message", resp.reason or "Request failed."),
                field_errors=error.get("details", {}),
            ),
        )
