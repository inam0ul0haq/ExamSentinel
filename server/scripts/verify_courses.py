"""Verification script for courses and enrollments endpoints.

Tests the Definition of Done:
- Teacher can create a course, enroll a student by email, list their courses
  with student counts, and remove an enrollment.
- Student sees only courses they're enrolled in.
- Cross-tenant attempts (teacher A editing teacher B's course) return 403.

Usage from the ``server/`` directory after the dev server is up:

    .\.venv\Scripts\python.exe scripts\verify_courses.py
    .\.venv\Scripts\python.exe scripts\verify_courses.py --base https://your.app.up.railway.app
    .\.venv\Scripts\python.exe scripts\verify_courses.py --base https://your.app.up.railway.app --department-id 2
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
    """Make an HTTP request and return ``(status, parsed_json_or_text)``."""
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

    # --------------------------------------------------------------------
    # Setup: Register a teacher and a student
    # --------------------------------------------------------------------
    print("--- Setup: Register teacher ---")
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Course Teacher",
            "email": f"teacher_{ts}@example.com",
            "password": password,
            "role": "teacher",
            "employee_code": f"CT{ts}",
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    _assert(status == 201, "Register teacher", str(status))
    teacher_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(teacher_token), "Teacher token extracted")

    print("\n--- Setup: Register student ---")
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Course Student",
            "email": f"student_{ts}@example.com",
            "password": password,
            "role": "student",
            "roll_number": f"R{ts}",
            "department_id": args.department_id,
            "semester": 3,
        },
    )
    _assert(status == 201, "Register student", str(status))
    student_token = body.get("access_token") if isinstance(body, dict) else None
    student_email = f"student_{ts}@example.com"
    _assert(bool(student_token), "Student token extracted")

    # Register a second teacher for cross-tenant test
    print("\n--- Setup: Register second teacher (for cross-tenant test) ---")
    status, body = _call(
        base,
        "POST",
        "/auth/register",
        {
            "full_name": "Other Teacher",
            "email": f"other_{ts}@example.com",
            "password": password,
            "role": "teacher",
            "employee_code": f"OT{ts}",
            "designation": "Lecturer",
            "department_id": args.department_id,
        },
    )
    _assert(status == 201, "Register second teacher", str(status))
    other_teacher_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(other_teacher_token), "Other teacher token extracted")

    # --------------------------------------------------------------------
    # Test 1: List departments (public)
    # --------------------------------------------------------------------
    print("\n--- Test 1: List departments (public) ---")
    status, body = _call(base, "GET", "/departments")
    _assert(status == 200, "GET /departments -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body and "pagination" in body,
        "Departments response has pagination envelope",
    )

    # --------------------------------------------------------------------
    # Test 2: Create course (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 2: Create course ---")
    status, body = _call(
        base,
        "POST",
        "/courses",
        {
            "title": "Introduction to Programming",
            "code": f"CS{ts}",
            "description": "A beginner course on programming.",
        },
        token=teacher_token,
    )
    _assert(status == 201, "POST /courses -> 201", str(status))
    _assert(
        isinstance(body, dict) and body.get("teacher_id") and body.get("id"),
        "Course response has id and teacher_id",
    )
    course_id = body.get("id")
    course_code = body.get("code")
    _assert(bool(course_id), "Course id extracted")
    _assert(
        body.get("enrollment_count") == 0,
        "New course has enrollment_count = 0",
    )

    # --------------------------------------------------------------------
    # Test 3: Duplicate course code returns 422
    # --------------------------------------------------------------------
    print("\n--- Test 3: Duplicate course code -> 422 ---")
    status, body = _call(
        base,
        "POST",
        "/courses",
        {
            "title": "Another Course",
            "code": course_code,
        },
        token=teacher_token,
    )
    _assert(status == 422, "Duplicate code -> 422", str(status))
    _assert(
        isinstance(body, dict)
        and body.get("error", {}).get("code") == "validation_failed",
        "Duplicate code -> validation_failed",
    )
    _assert(
        isinstance(body, dict)
        and isinstance(body.get("error", {}).get("details"), dict)
        and "code" in body["error"]["details"],
        "Duplicate code -> field-level error on code",
    )

    # --------------------------------------------------------------------
    # Test 4: Get course detail (teacher owner)
    # --------------------------------------------------------------------
    print("\n--- Test 4: Get course detail (teacher owner) ---")
    status, body = _call(base, "GET", f"/courses/{course_id}", token=teacher_token)
    _assert(status == 200, "GET /courses/{id} (owner) -> 200", str(status))
    _assert(
        isinstance(body, dict) and "enrolled_students" in body,
        "Teacher view includes enrolled_students",
    )

    # --------------------------------------------------------------------
    # Test 5: Get course detail (student not enrolled) -> 403
    # --------------------------------------------------------------------
    print("\n--- Test 5: Get course detail (student not enrolled) -> 403 ---")
    status, body = _call(base, "GET", f"/courses/{course_id}", token=student_token)
    _assert(status == 403, "GET /courses/{id} (not enrolled) -> 403", str(status))

    # --------------------------------------------------------------------
    # Test 6: Enroll student by email (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 6: Enroll student by email ---")
    status, body = _call(
        base,
        "POST",
        f"/courses/{course_id}/enrollments",
        {"student_email": student_email},
        token=teacher_token,
    )
    _assert(status == 201, "POST /courses/{id}/enrollments -> 201", str(status))
    _assert(
        isinstance(body, dict) and body.get("student_email") == student_email,
        "Enrollment response includes student_email",
    )
    enrollment_id = body.get("id")
    _assert(bool(enrollment_id), "Enrollment id extracted")

    # --------------------------------------------------------------------
    # Test 7: Enroll same student again -> 409
    # --------------------------------------------------------------------
    print("\n--- Test 7: Enroll same student again -> 409 ---")
    status, body = _call(
        base,
        "POST",
        f"/courses/{course_id}/enrollments",
        {"student_email": student_email},
        token=teacher_token,
    )
    _assert(status == 409, "Duplicate enrollment -> 409", str(status))

    # --------------------------------------------------------------------
    # Test 8: Get course detail (student now enrolled) -> 200
    # --------------------------------------------------------------------
    print("\n--- Test 8: Get course detail (student enrolled) -> 200 ---")
    status, body = _call(base, "GET", f"/courses/{course_id}", token=student_token)
    _assert(status == 200, "GET /courses/{id} (enrolled) -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("enrolled_students") is None,
        "Student view does NOT include enrolled_students",
    )

    # --------------------------------------------------------------------
    # Test 9: List my courses (teacher) -> shows owned courses
    # --------------------------------------------------------------------
    print("\n--- Test 9: GET /courses/me (teacher) ---")
    status, body = _call(base, "GET", "/courses/me", token=teacher_token)
    _assert(status == 200, "GET /courses/me (teacher) -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body,
        "Courses response has items",
    )
    # Should have enrollment_count for teachers
    if body.get("items"):
        _assert(
            body["items"][0].get("enrollment_count") is not None,
            "Teacher view includes enrollment_count",
        )

    # --------------------------------------------------------------------
    # Test 10: List my courses (student) -> shows enrolled courses
    # --------------------------------------------------------------------
    print("\n--- Test 10: GET /courses/me (student) ---")
    status, body = _call(base, "GET", "/courses/me", token=student_token)
    _assert(status == 200, "GET /courses/me (student) -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body,
        "Student courses response has items",
    )
    # Should NOT have enrollment_count for students
    if body.get("items"):
        _assert(
            body["items"][0].get("enrollment_count") is None,
            "Student view does NOT include enrollment_count",
        )
        _assert(
            body["items"][0].get("active_exam_count") is not None,
            "Student view includes active_exam_count",
        )

    # --------------------------------------------------------------------
    # Test 11: Cross-tenant - other teacher tries to edit course -> 403
    # --------------------------------------------------------------------
    print("\n--- Test 11: Cross-tenant PATCH -> 403 ---")
    status, body = _call(
        base,
        "PATCH",
        f"/courses/{course_id}",
        {"title": "Hacked Title"},
        token=other_teacher_token,
    )
    _assert(status == 403, "PATCH by non-owner -> 403", str(status))

    # --------------------------------------------------------------------
    # Test 12: Cross-tenant - other teacher tries to delete course -> 403
    # --------------------------------------------------------------------
    print("\n--- Test 12: Cross-tenant DELETE -> 403 ---")
    status, body = _call(
        base, "DELETE", f"/courses/{course_id}", token=other_teacher_token
    )
    _assert(status == 403, "DELETE by non-owner -> 403", str(status))

    # --------------------------------------------------------------------
    # Test 13: List enrolled students (teacher owner)
    # --------------------------------------------------------------------
    print("\n--- Test 13: GET /courses/{id}/students (owner) ---")
    status, body = _call(
        base, "GET", f"/courses/{course_id}/students", token=teacher_token
    )
    _assert(status == 200, "GET /courses/{id}/students -> 200", str(status))
    _assert(
        isinstance(body, list) and len(body) == 1,
        "Students list has one item",
    )

    # --------------------------------------------------------------------
    # Test 14: List enrolled students (other teacher) -> 403
    # --------------------------------------------------------------------
    print("\n--- Test 14: GET /courses/{id}/students (non-owner) -> 403 ---")
    status, body = _call(
        base, "GET", f"/courses/{course_id}/students", token=other_teacher_token
    )
    _assert(status == 403, "GET /courses/{id}/students (non-owner) -> 403", str(status))

    # --------------------------------------------------------------------
    # Test 15: Drop enrollment (teacher owner)
    # --------------------------------------------------------------------
    print("\n--- Test 15: DELETE enrollment (owner) ---")
    status, body = _call(
        base,
        "DELETE",
        f"/courses/{course_id}/enrollments/{enrollment_id}",
        token=teacher_token,
    )
    _assert(status == 204, "DELETE enrollment -> 204", str(status))

    # --------------------------------------------------------------------
    # Test 16: Student can no longer see course after drop
    # --------------------------------------------------------------------
    print("\n--- Test 16: Student view after drop -> 403 ---")
    status, body = _call(base, "GET", f"/courses/{course_id}", token=student_token)
    _assert(status == 403, "GET course after drop -> 403", str(status))

    # --------------------------------------------------------------------
    # Test 17: List students with filters (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 17: GET /users/students (teacher) ---")
    status, body = _call(base, "GET", "/users/students", token=teacher_token)
    _assert(status == 200, "GET /users/students -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body and "pagination" in body,
        "Students list has pagination envelope",
    )

    # --------------------------------------------------------------------
    # Test 18: List teachers (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 18: GET /users/teachers (teacher) ---")
    status, body = _call(base, "GET", "/users/teachers", token=teacher_token)
    _assert(status == 200, "GET /users/teachers -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body and "pagination" in body,
        "Teachers list has pagination envelope",
    )

    # --------------------------------------------------------------------
    # Test 19: Student tries to access /users/students -> 403
    # --------------------------------------------------------------------
    print("\n--- Test 19: GET /users/students (student) -> 403 ---")
    status, body = _call(base, "GET", "/users/students", token=student_token)
    _assert(status == 403, "GET /users/students (student) -> 403", str(status))

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
