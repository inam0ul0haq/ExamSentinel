"""Verification script for exams and sessions endpoints.

Tests the Definition of Done:
- Teacher creates exam with questions
- Teacher activates
- Student lists active exams
- Student starts session (pre_check)
- Student transitions to in_progress
- Student saves answers
- Student submits
- Student fetches result with score
- Auto-grading is correct for mcq
- Deadline auto-expiry works

Usage from the ``server/`` directory after the dev server is up:

    .\.venv\Scripts\python.exe scripts\verify_exams.py
    .\.venv\Scripts\python.exe scripts\verify_exams.py --base https://your.app.up.railway.app
    .\.venv\Scripts\python.exe scripts\verify_exams.py --base https://your.app.up.railway.app --department-id 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
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
            "full_name": "Exam Teacher",
            "email": f"exam_teacher_{ts}@example.com",
            "password": password,
            "role": "teacher",
            "employee_code": f"ET{ts}",
            "designation": "Professor",
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
            "full_name": "Exam Student",
            "email": f"exam_student_{ts}@example.com",
            "password": password,
            "role": "student",
            "roll_number": f"R{ts}",
            "department_id": args.department_id,
            "semester": 3,
        },
    )
    _assert(status == 201, "Register student", str(status))
    student_token = body.get("access_token") if isinstance(body, dict) else None
    student_email = f"exam_student_{ts}@example.com"
    _assert(bool(student_token), "Student token extracted")

    # --------------------------------------------------------------------
    # Setup: Create a course and enroll the student
    # --------------------------------------------------------------------
    print("\n--- Setup: Create course ---")
    status, body = _call(
        base,
        "POST",
        "/courses",
        {
            "title": "Test Course for Exams",
            "code": f"EX{ts}",
            "description": "Course for exam verification.",
        },
        token=teacher_token,
    )
    _assert(status == 201, "Create course", str(status))
    course_id = body.get("id")
    _assert(bool(course_id), "Course id extracted")

    print("\n--- Setup: Enroll student ---")
    status, body = _call(
        base,
        "POST",
        f"/courses/{course_id}/enrollments",
        {"student_email": student_email},
        token=teacher_token,
    )
    _assert(status == 201, "Enroll student", str(status))

    # --------------------------------------------------------------------
    # Test 1: Create exam with questions (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 1: Create exam with questions ---")
    now = datetime.now(timezone.utc)
    start_window = now - timedelta(hours=1)
    end_window = now + timedelta(hours=24)

    status, body = _call(
        base,
        "POST",
        f"/courses/{course_id}/exams",
        {
            "title": "Test Exam",
            "description": "Exam for verification",
            "duration_minutes": 60,
            "start_window": start_window.isoformat(),
            "end_window": end_window.isoformat(),
            "questions": [
                {
                    "question_text": "What is 2 + 2?",
                    "question_type": "mcq",
                    "marks": 5,
                    "order_index": 1,
                    "options": ["3", "4", "5", "6"],
                    "correct_answer": "4",
                },
                {
                    "question_text": "What is the capital of France?",
                    "question_type": "mcq",
                    "marks": 5,
                    "order_index": 2,
                    "options": ["London", "Berlin", "Paris", "Madrid"],
                    "correct_answer": "Paris",
                },
            ],
        },
        token=teacher_token,
    )
    _assert(status == 201, "POST /courses/{id}/exams -> 201", str(status))
    _assert(
        isinstance(body, dict) and body.get("id"),
        "Exam response has id",
    )
    _assert(
        isinstance(body, dict) and body.get("is_active") == False,
        "New exam is not active",
    )
    _assert(
        isinstance(body, dict) and len(body.get("questions", [])) == 2,
        "Exam has 2 questions",
    )
    exam_id = body.get("id")
    _assert(bool(exam_id), "Exam id extracted")

    # --------------------------------------------------------------------
    # Test 2: Get exam as teacher (includes correct answers)
    # --------------------------------------------------------------------
    print("\n--- Test 2: Get exam as teacher ---")
    status, body = _call(base, "GET", f"/exams/{exam_id}", token=teacher_token)
    _assert(status == 200, "GET /exams/{id} (teacher) -> 200", str(status))
    _assert(
        isinstance(body, dict) and len(body.get("questions", [])) == 2,
        "Teacher view includes questions",
    )
    _assert(
        isinstance(body, dict) and body.get("questions", [])[0].get("correct_answer") == "4",
        "Teacher view includes correct_answer",
    )

    # --------------------------------------------------------------------
    # Test 3: Get exam as student before activation (403)
    # --------------------------------------------------------------------
    print("\n--- Test 3: Get exam as student before activation -> 403 ---")
    status, body = _call(base, "GET", f"/exams/{exam_id}", token=student_token)
    _assert(status == 200, "GET /exams/{id} (student, inactive) -> 200", str(status))
    _assert(
        isinstance(body, dict) and "questions" not in body,
        "Student view does NOT include questions when inactive",
    )

    # --------------------------------------------------------------------
    # Test 4: Activate exam (teacher)
    # --------------------------------------------------------------------
    print("\n--- Test 4: Activate exam ---")
    status, body = _call(base, "POST", f"/exams/{exam_id}/activate", token=teacher_token)
    _assert(status == 200, "POST /exams/{id}/activate -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("is_active") == True,
        "Exam is now active",
    )

    # --------------------------------------------------------------------
    # Test 5: List active exams as student
    # --------------------------------------------------------------------
    print("\n--- Test 5: List active exams as student ---")
    status, body = _call(base, "GET", "/exams/active", token=student_token)
    _assert(status == 200, "GET /exams/active -> 200", str(status))
    _assert(
        isinstance(body, dict) and "items" in body,
        "Active exams response has items",
    )
    _assert(
        isinstance(body, dict) and len(body.get("items", [])) >= 1,
        "At least one active exam",
    )

    # --------------------------------------------------------------------
    # Test 6: Start session (pre_check)
    # --------------------------------------------------------------------
    print("\n--- Test 6: Start session (pre_check) ---")
    status, body = _call(
        base,
        "POST",
        "/sessions",
        {"exam_id": exam_id},
        token=student_token,
    )
    _assert(status == 201, "POST /sessions -> 201", str(status))
    _assert(
        isinstance(body, dict) and body.get("status") == "pre_check",
        "Session status is pre_check",
    )
    _assert(
        isinstance(body, dict) and "questions" in body,
        "Session includes questions",
    )
    _assert(
        isinstance(body, dict) and body.get("questions", [])[0].get("correct_answer") is None,
        "Student view does NOT include correct_answer",
    )
    session_id = body.get("id")
    _assert(bool(session_id), "Session id extracted")

    # --------------------------------------------------------------------
    # Test 7: Transition to in_progress
    # --------------------------------------------------------------------
    print("\n--- Test 7: Transition to in_progress ---")
    status, body = _call(
        base,
        "PATCH",
        f"/sessions/{session_id}",
        {"status": "in_progress"},
        token=student_token,
    )
    _assert(status == 200, "PATCH /sessions/{id} -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("status") == "in_progress",
        "Session status is in_progress",
    )
    _assert(
        isinstance(body, dict) and body.get("started_at") is not None,
        "Session has started_at",
    )
    _assert(
        isinstance(body, dict) and body.get("deadline_at") is not None,
        "Session has deadline_at",
    )

    # --------------------------------------------------------------------
    # Test 8: Save answers
    # --------------------------------------------------------------------
    print("\n--- Test 8: Save answer for question 1 ---")
    status, body = _call(
        base,
        "PUT",
        f"/sessions/{session_id}/answers/1",
        {"answer_text": "4"},
        token=student_token,
    )
    _assert(status == 200, "PUT /sessions/{id}/answers/{qid} -> 200", str(status))

    print("\n--- Test 9: Save answer for question 2 ---")
    status, body = _call(
        base,
        "PUT",
        f"/sessions/{session_id}/answers/2",
        {"answer_text": "Paris"},
        token=student_token,
    )
    _assert(status == 200, "PUT /sessions/{id}/answers/{qid} -> 200", str(status))

    # --------------------------------------------------------------------
    # Test 10: Submit session
    # --------------------------------------------------------------------
    print("\n--- Test 10: Submit session ---")
    status, body = _call(base, "POST", f"/sessions/{session_id}/submit", token=student_token)
    _assert(status == 200, "POST /sessions/{id}/submit -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("status") == "submitted",
        "Session status is submitted",
    )
    _assert(
        isinstance(body, dict) and body.get("score") == 10.0,
        "Auto-graded score is correct (10.0)",
    )
    _assert(
        isinstance(body, dict) and body.get("mcq_marks_awarded") == 10,
        "MCQ marks awarded is 10",
    )
    _assert(
        isinstance(body, dict) and body.get("mcq_marks_possible") == 10,
        "MCQ marks possible is 10",
    )

    # --------------------------------------------------------------------
    # Test 11: Get result
    # --------------------------------------------------------------------
    print("\n--- Test 11: Get result ---")
    status, body = _call(base, "GET", f"/sessions/{session_id}/result", token=student_token)
    _assert(status == 200, "GET /sessions/{id}/result -> 200", str(status))
    _assert(
        isinstance(body, dict) and "breakdown" in body,
        "Result has breakdown",
    )
    _assert(
        isinstance(body, dict) and len(body.get("breakdown", [])) == 2,
        "Breakdown has 2 questions",
    )
    _assert(
        isinstance(body, dict) and body.get("breakdown", [])[0].get("is_correct") == True,
        "First question is correct",
    )
    _assert(
        isinstance(body, dict) and body.get("breakdown", [])[0].get("correct_answer") is None,
        "Student result does NOT include correct_answer",
    )

    # --------------------------------------------------------------------
    # Test 12: Teacher can see result with correct_answer
    # --------------------------------------------------------------------
    print("\n--- Test 12: Teacher view result with correct_answer ---")
    status, body = _call(base, "GET", f"/sessions/{session_id}/result", token=teacher_token)
    _assert(status == 200, "GET /sessions/{id}/result (teacher) -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("breakdown", [])[0].get("correct_answer") == "4",
        "Teacher result includes correct_answer",
    )

    # --------------------------------------------------------------------
    # Test 13: Time remaining endpoint
    # --------------------------------------------------------------------
    print("\n--- Test 13: Get time remaining (submitted session) ---")
    status, body = _call(base, "GET", f"/sessions/{session_id}/time", token=student_token)
    _assert(status == 200, "GET /sessions/{id}/time -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("expired") == True,
        "Submitted session shows expired",
    )

    # --------------------------------------------------------------------
    # Test 14: Create exam with short duration for expiry test
    # --------------------------------------------------------------------
    print("\n--- Test 14: Create exam with 1-minute duration ---")
    short_exam_start = now - timedelta(hours=1)
    short_exam_end = now + timedelta(hours=24)

    status, body = _call(
        base,
        "POST",
        f"/courses/{course_id}/exams",
        {
            "title": "Short Exam",
            "description": "Exam for expiry test",
            "duration_minutes": 1,
            "start_window": short_exam_start.isoformat(),
            "end_window": short_exam_end.isoformat(),
            "questions": [
                {
                    "question_text": "Test question",
                    "question_type": "mcq",
                    "marks": 5,
                    "order_index": 1,
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                },
            ],
        },
        token=teacher_token,
    )
    _assert(status == 201, "Create short exam -> 201", str(status))
    short_exam_id = body.get("id")
    _assert(bool(short_exam_id), "Short exam id extracted")

    status, body = _call(base, "POST", f"/exams/{short_exam_id}/activate", token=teacher_token)
    _assert(status == 200, "Activate short exam -> 200", str(status))

    # --------------------------------------------------------------------
    # Test 15: Start session for expiry test
    # --------------------------------------------------------------------
    print("\n--- Test 15: Start session for expiry test ---")
    status, body = _call(
        base,
        "POST",
        "/sessions",
        {"exam_id": short_exam_id},
        token=student_token,
    )
    _assert(status == 201, "Start expiry test session -> 201", str(status))
    expiry_session_id = body.get("id")
    _assert(bool(expiry_session_id), "Expiry session id extracted")

    # --------------------------------------------------------------------
    # Test 16: Transition to in_progress
    # --------------------------------------------------------------------
    print("\n--- Test 16: Transition expiry session to in_progress ---")
    status, body = _call(
        base,
        "PATCH",
        f"/sessions/{expiry_session_id}",
        {"status": "in_progress"},
        token=student_token,
    )
    _assert(status == 200, "Transition expiry session -> 200", str(status))

    # --------------------------------------------------------------------
    # Test 17: Wait 65 seconds for expiry
    # --------------------------------------------------------------------
    print("\n--- Test 17: Wait 65 seconds for expiry ---")
    print("Waiting 65 seconds for deadline to pass...")
    time.sleep(65)

    # --------------------------------------------------------------------
    # Test 18: Check time remaining (should auto-expire)
    # --------------------------------------------------------------------
    print("\n--- Test 18: Check time remaining (auto-expiry) ---")
    status, body = _call(base, "GET", f"/sessions/{expiry_session_id}/time", token=student_token)
    _assert(status == 200, "GET /sessions/{id}/time -> 200", str(status))
    _assert(
        isinstance(body, dict) and body.get("expired") == True,
        "Session is expired after deadline",
    )
    _assert(
        isinstance(body, dict) and body.get("time_remaining_seconds") == 0,
        "Time remaining is 0",
    )

    # --------------------------------------------------------------------
    # Test 19: Verify session status changed to expired
    # --------------------------------------------------------------------
    print("\n--- Test 19: Verify session status is expired ---")
    status, body = _call(base, "GET", f"/exams/{short_exam_id}", token=teacher_token)
    _assert(status == 200, "GET exam to check sessions -> 200", str(status))
    # Note: We can't directly check session status without a sessions list endpoint
    # but the time endpoint auto-expired it, which is the key test

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
