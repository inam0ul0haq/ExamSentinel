"""End-to-end verification script for the auth subsystem.

Originally written for the Part-7 Definition of Done; kept committed as
ongoing scaffolding because the same checks (register / login / /me /
role-gated routes / error envelope) need to run against every new
deployment and against the local dev server after every auth change.

Usage from the ``server/`` directory after the dev server is up:

    .\.venv\Scripts\python.exe scripts\verify_auth.py
    .\.venv\Scripts\python.exe scripts\verify_auth.py --base https://your.app.up.railway.app
    .\.venv\Scripts\python.exe scripts\verify_auth.py --department-id 2

Re-runnable by design: every account it creates uses a fresh email /
employee_code / roll_number derived from the current Unix timestamp,
so the uniqueness checks in ``/auth/register`` don't trip on prior
runs. Exits 0 on success and 1 on any failed assertion.

Pre-flight requirements:

* The target server must be reachable at ``--base``.
* At least one ``Department`` row must exist; pass its id via
  ``--department-id`` (defaults to ``1``). On Railway PG you can seed
  one once with::

      INSERT INTO departments (name, code) VALUES ('Computer Science', 'CS');
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

    Uses ``urllib`` so the script has no third-party dependencies. 4xx
    and 5xx responses are returned the same as 2xx — we never want a
    failing assertion to be masked by a thrown HTTPError.
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


def _show(label: str, status: int, body: Any) -> None:
    print(f"--- {label} ---")
    print(f"  status: {status}")
    if isinstance(body, (dict, list)):
        print("  body:  " + json.dumps(body, indent=2)[:1500])
    else:
        print(f"  body:  {body!r}")


_PASS = 0
_FAIL = 0


def _assert(cond: bool, label: str, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"PASS  {label}")
    else:
        _FAIL += 1
        print(f"FAIL  {label}  {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--department-id", type=int, default=1)
    args = parser.parse_args()

    base = args.base.rstrip("/") + "/api/v1"
    print(f"Verifying against: {base}\n")

    ts = int(time.time())
    t_email = f"teacher_{ts}@example.com"
    t_emp = f"EMP{ts}"
    s_email = f"student_{ts}@example.com"
    s_roll = f"R{ts}"
    password = "secret-pass-1"

    # 0. Health probe
    status, body = _call(base, "GET", "/health")
    _show("0. health", status, body)
    _assert(status == 200, "GET /health -> 200", str(status))

    # 1. Register a teacher *without* department_id (DoD core requirement).
    # The teacher branch of registration must succeed when the caller
    # omits ``department_id``, because the column is nullable for the
    # ``teachers`` table (migration ``0ef080486833``).
    status, body = _call(
        base, "POST", "/auth/register",
        {
            "full_name": "Test Teacher",
            "email": t_email,
            "password": password,
            "role": "teacher",
            "employee_code": t_emp,
            "designation": "Lecturer",
        },
    )
    _show("1. register teacher (no department_id)", status, body)
    _assert(status == 201, "POST /auth/register (teacher, no dept) -> 201", str(status))
    _assert(
        isinstance(body, dict) and bool(body.get("access_token")),
        "register response carries access_token",
    )
    _assert(
        isinstance(body, dict)
        and body.get("user", {}).get("department_id") is None,
        "teacher.user.department_id is null when omitted",
    )

    # 1b. Register a second teacher *with* department_id — the optional
    # field is still validated for type and existence when supplied.
    status, body = _call(
        base, "POST", "/auth/register",
        {
            "full_name": "Test Teacher Two",
            "email": f"teacher2_{ts}@example.com",
            "password": password,
            "role": "teacher",
            "employee_code": f"{t_emp}B",
            "designation": "Senior Lecturer",
            "department_id": args.department_id,
        },
    )
    _show("1b. register teacher (with department_id)", status, body)
    _assert(status == 201, "POST /auth/register (teacher, with dept) -> 201", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("user", {}).get("department_id") == args.department_id,
        "teacher.user.department_id reflects supplied value",
    )

    # 2. Login as teacher returns a JWT
    status, body = _call(
        base, "POST", "/auth/login",
        {"email": t_email, "password": password},
    )
    _show("2. login teacher", status, body)
    _assert(status == 200, "POST /auth/login (teacher) -> 200", str(status))
    teacher_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(teacher_token), "login response carries access_token")
    _assert(
        isinstance(body, dict) and body.get("user", {}).get("role") == "teacher",
        "login.user.role == teacher",
    )

    # 3. /auth/me with teacher token
    status, body = _call(base, "GET", "/auth/me", token=teacher_token)
    _show("3. /auth/me (teacher)", status, body)
    _assert(status == 200, "GET /auth/me (teacher token) -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("user", {}).get("role") == "teacher",
        "me.user.role == teacher",
    )
    _assert(
        isinstance(body, dict)
        and body.get("user", {}).get("employee_code") == t_emp,
        "me.user.employee_code matches registration",
    )

    # 4. Diagnostic teacher-only access matrix
    status, body = _call(base, "GET", "/_diag/teacher-only", token=teacher_token)
    _show("4a. teacher-only (teacher)", status, body)
    _assert(status == 200, "GET /_diag/teacher-only (teacher) -> 200", str(status))

    # Need a student to try the negative case.
    status, body = _call(
        base, "POST", "/auth/register",
        {
            "full_name": "Test Student",
            "email": s_email,
            "password": password,
            "role": "student",
            "roll_number": s_roll,
            "department_id": args.department_id,
            "semester": 3,
        },
    )
    _show("4b. register student", status, body)
    _assert(status == 201, "POST /auth/register (student) -> 201", str(status))
    student_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(student_token), "student register carries access_token")

    status, body = _call(
        base, "GET", "/_diag/teacher-only", token=student_token,
    )
    _show("4c. teacher-only (student)", status, body)
    _assert(status == 403, "GET /_diag/teacher-only (student) -> 403", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "forbidden",
        "error.code == forbidden",
    )

    status, body = _call(base, "GET", "/_diag/teacher-only")
    _show("4d. teacher-only (no token)", status, body)
    _assert(status == 401, "GET /_diag/teacher-only (no token) -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "unauthorized",
        "error.code == unauthorized",
    )

    # 5. Symmetric: /_diag/student-only
    status, _ = _call(base, "GET", "/_diag/student-only", token=student_token)
    _assert(status == 200, "GET /_diag/student-only (student) -> 200", str(status))
    status, body = _call(base, "GET", "/_diag/student-only", token=teacher_token)
    _assert(status == 403, "GET /_diag/student-only (teacher) -> 403", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "forbidden",
        "/_diag/student-only forbidden code",
    )
    status, body = _call(base, "GET", "/_diag/student-only")
    _assert(status == 401, "GET /_diag/student-only (no token) -> 401", str(status))

    # 6. Login failure cases — generic 401
    status, body = _call(
        base, "POST", "/auth/login",
        {"email": t_email, "password": "wrong-password"},
    )
    _assert(status == 401, "Login wrong password -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "invalid_credentials",
        "wrong password -> invalid_credentials",
    )

    status, body = _call(
        base, "POST", "/auth/login",
        {"email": "noone@example.com", "password": "anything"},
    )
    _assert(status == 401, "Login unknown email -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "invalid_credentials",
        "unknown email -> invalid_credentials",
    )

    # 7. Validation failure on register
    status, body = _call(base, "POST", "/auth/register", {"email": "bad"})
    _show("7. register bad body", status, body)
    _assert(status == 422, "POST /auth/register (bad body) -> 422", str(status))
    # 7b. Teacher supplying a non-existent department_id is still rejected
    # — the field is optional but, when supplied, must reference a real row.
    status, body = _call(
        base, "POST", "/auth/register",
        {
            "full_name": "Bad Dept Teacher",
            "email": f"baddept_{ts}@example.com",
            "password": password,
            "role": "teacher",
            "employee_code": f"BAD{ts}",
            "designation": "Lecturer",
            "department_id": 99999,
        },
    )
    _assert(status == 422, "Teacher with bogus department_id -> 422", str(status))
    _assert(
        isinstance(body, dict)
        and "department_id" in body.get("error", {}).get("details", {}),
        "department_id error detail present for bogus id",
    )
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "validation_failed",
        "error.code == validation_failed",
    )
    _assert(
        isinstance(body, dict)
        and isinstance(body.get("error", {}).get("details"), dict)
        and body["error"]["details"],
        "error.details populated",
    )

    # 8. /auth/me with garbage token
    status, body = _call(base, "GET", "/auth/me", token="this.is.not.a.real.jwt")
    _assert(status == 401, "GET /auth/me (invalid token) -> 401", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") in {"unauthorized", "token_expired"},
        "/auth/me invalid token -> unauthorized envelope",
    )

    # 9. Conflict on duplicate email
    status, body = _call(
        base, "POST", "/auth/register",
        {
            "full_name": "Test Teacher",
            "email": t_email,
            "password": password,
            "role": "teacher",
            "employee_code": f"DUP{ts}",
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    _assert(status == 409, "Duplicate email -> 409", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "conflict",
        "duplicate email -> conflict code",
    )

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"PASSED: {_PASS}")
    print(f"FAILED: {_FAIL}")
    print("=" * 60)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
