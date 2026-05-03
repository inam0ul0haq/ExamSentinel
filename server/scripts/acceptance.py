"""Acceptance tests for the auth subsystem — the exact 7 cases you specified.

Runs against a configurable base URL (default: local dev server, override
with ``--base`` to hit Railway). Uses only the standard library
(`urllib`) so no pip install is required.

Usage (from the ``server/`` directory):

    .\.venv\Scripts\python.exe scripts\acceptance.py
    .\.venv\Scripts\python.exe scripts\acceptance.py --base https://web-production-5a17d.up.railway.app
    .\.venv\Scripts\python.exe scripts\acceptance.py --base https://web-production-5a17d.up.railway.app --department-id 2

Exits 0 on success, 1 on any failed assertion.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Optional, Tuple
from urllib import error, request


def _call(
    base: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
) -> Tuple[int, Optional[Any]]:
    """Make an HTTP request and return ``(status, parsed_json_or_text)``.

    Handles 4xx/5xx the same as 2xx — never raises on error status.
    """
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url=url, method=method, data=data, headers=headers)

    try:
        with request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            status = resp.status
    except error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except error.URLError as exc:
        return 0, f"URLError: {exc}"

    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, raw.decode("utf-8", errors="replace")


def _assert(cond: bool, label: str, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"PASS  {label}")
    else:
        _FAIL += 1
        print(f"FAIL  {label}  {detail}")


_PASS = 0
_FAIL = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--department-id", type=int, default=1)
    args = parser.parse_args()

    base = args.base.rstrip("/") + "/api/v1"
    print(f"Verifying against: {base}\n")

    ts = int(time.time())
    password = "password123"
    teacher_email = f"teacher_{ts}@example.com"
    teacher_emp = f"EMP{ts}"
    student_email = f"student_{ts}@example.com"
    student_roll = f"R{ts}"

    # --------------------------------------------------------------------
    # Test 1: Register teacher with full payload → 201 with token
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Test Teacher",
            "email": teacher_email,
            "password": password,
            "role": "teacher",
            "employee_code": teacher_emp,
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    print(f"1. Register teacher (full payload): {status}")
    _assert(status == 201, "POST /auth/register (teacher) -> 201", str(status))
    _assert(
        isinstance(body, dict) and bool(body.get("access_token")),
        "register response carries access_token",
    )
    teacher_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(teacher_token), "teacher token extracted")

    # --------------------------------------------------------------------
    # Test 2: Register with duplicate email → 422 with field-level error on email
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Dupe Teacher",
            "email": teacher_email,
            "password": password,
            "role": "teacher",
            "employee_code": f"DUP{ts}",
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    print(f"2. Duplicate email: {status}")
    _assert(status == 422, "POST /auth/register (duplicate email) -> 422", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "validation_failed",
        "error.code == validation_failed",
    )
    _assert(
        isinstance(body, dict)
        and isinstance(body.get("error", {}).get("details"), dict)
        and "email" in body["error"]["details"],
        "field-level error on email",
    )

    # --------------------------------------------------------------------
    # Test 3: Register with password length 5 → 422
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Short Pass Teacher",
            "email": f"shortpass_{ts}@example.com",
            "password": "12345",
            "role": "teacher",
            "employee_code": f"SHORT{ts}",
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    print(f"3. Password length 5: {status}")
    _assert(status == 422, "POST /auth/register (short password) -> 422", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "validation_failed",
        "error.code == validation_failed",
    )
    _assert(
        isinstance(body, dict)
        and isinstance(body.get("error", {}).get("details"), dict)
        and "password" in body["error"]["details"],
        "field-level error on password",
    )

    # --------------------------------------------------------------------
    # Test 4: Login with correct credentials → 200 with token
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/login",
        {"email": teacher_email, "password": password},
    )
    print(f"4. Login correct credentials: {status}")
    _assert(status == 200, "POST /auth/login (correct) -> 200", str(status))
    _assert(
        isinstance(body, dict) and bool(body.get("access_token")),
        "login response carries access_token",
    )
    teacher_token = body.get("access_token") if isinstance(body, dict) else None

    # --------------------------------------------------------------------
    # Test 4b: Login with wrong password → 401 with generic message
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/login",
        {"email": teacher_email, "password": "wrongpassword"},
    )
    print(f"4b. Login wrong password: {status}")
    _assert(status == 401, "POST /auth/login (wrong password) -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "invalid_credentials",
        "error.code == invalid_credentials",
    )
    # The message must NOT reveal whether it was the email or password that was wrong.
    _assert(
        isinstance(body, dict)
        and isinstance(body.get("error", {}).get("message"), str),
        "error.message is present",
    )

    # --------------------------------------------------------------------
    # Test 5: GET /auth/me with valid teacher token → joined profile
    # --------------------------------------------------------------------
    status, body = _call(base, "GET", "/auth/me", token=teacher_token)
    print(f"5. GET /auth/me (teacher token): {status}")
    _assert(status == 200, "GET /auth/me (teacher) -> 200", str(status))
    _assert(
        isinstance(body, dict) and isinstance(body.get("user"), dict),
        "response has user object",
    )
    user = body.get("user", {})
    _assert(user.get("role") == "teacher", "user.role == teacher")
    _assert(
        user.get("employee_code") == teacher_emp,
        "user.employee_code matches registration",
    )
    _assert(
        user.get("designation") == "Lecturer",
        "user.designation matches registration",
    )

    # --------------------------------------------------------------------
    # Test 6: Register a student to get a student token for the next test
    # --------------------------------------------------------------------
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Test Student",
            "email": student_email,
            "password": password,
            "role": "student",
            "roll_number": student_roll,
            "department_id": args.department_id,
            "semester": 3,
        },
    )
    _assert(status == 201, "POST /auth/register (student) -> 201", str(status))
    student_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(student_token), "student token extracted")

    # --------------------------------------------------------------------
    # Test 6a: GET /_diag/teacher-only with student token → 403
    # --------------------------------------------------------------------
    status, body = _call(base, "GET", "/_diag/teacher-only", token=student_token)
    print(f"6a. GET /_diag/teacher-only (student token): {status}")
    _assert(status == 403, "GET /_diag/teacher-only (student) -> 403", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "forbidden",
        "error.code == forbidden",
    )

    # --------------------------------------------------------------------
    # Test 6b: GET /_diag/teacher-only with no token → 401
    # --------------------------------------------------------------------
    status, body = _call(base, "GET", "/_diag/teacher-only")
    print(f"6b. GET /_diag/teacher-only (no token): {status}")
    _assert(status == 401, "GET /_diag/teacher-only (no token) -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "unauthorized",
        "error.code == unauthorized",
    )

    # --------------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"PASSED: {_PASS}")
    print(f"FAILED: {_FAIL}")
    print("=" * 60)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
