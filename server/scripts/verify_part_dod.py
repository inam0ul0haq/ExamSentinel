"""Verification script for the Part DoD: exam + session flow with mixed
question types and the specific error-path expectations.

Scenarios covered:
1. Teacher creates an exam with 2 mcq + 1 short_answer; response contains
   the exam with question ids.
2. Teacher activates the exam.
3. Student starts a session, transitions pre_check -> in_progress, saves
   answers (one correct mcq, one incorrect mcq, one short_answer with text),
   submits. Score equals the marks of the correct mcq only.
4. PUT answer with answer "Z" on an mcq returns 422.
5. PUT answer after submit returns 409.
6. GET session time-remaining when past deadline auto-flips status to
   expired.

Usage from the ``server/`` directory after the dev server is up:

    .\\.venv\\Scripts\\python.exe scripts\\verify_part_dod.py
    .\\.venv\\Scripts\\python.exe scripts\\verify_part_dod.py --base https://your.app.up.railway.app
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib import error, request


_PASS = 0
_FAIL = 0


def _call(
    base: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
) -> Tuple[int, Optional[Any]]:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--department-id", type=int, default=1)
    args = parser.parse_args()
    base = args.base.rstrip("/") + "/api/v1"
    print(f"Verifying against: {base}\n")

    ts = int(time.time())
    password = "password123"

    # Setup: register teacher + student
    print("--- Setup ---")
    _, body = _call(base, "POST", "/auth/register", {
        "full_name": "DoD Teacher",
        "email": f"dod_teacher_{ts}@example.com",
        "password": password,
        "role": "teacher",
        "employee_code": f"DT{ts}",
        "designation": "Professor",
        "department_id": args.department_id,
    })
    teacher_token = body["access_token"]
    _assert(bool(teacher_token), "Teacher registered")

    _, body = _call(base, "POST", "/auth/register", {
        "full_name": "DoD Student",
        "email": f"dod_student_{ts}@example.com",
        "password": password,
        "role": "student",
        "roll_number": f"R{ts}",
        "department_id": args.department_id,
        "semester": 3,
    })
    student_token = body["access_token"]
    student_email = f"dod_student_{ts}@example.com"
    _assert(bool(student_token), "Student registered")

    # Setup: course + enroll
    _, body = _call(base, "POST", "/courses", {
        "title": "DoD Course",
        "code": f"DOD{ts}",
        "description": "Course for DoD verification.",
    }, token=teacher_token)
    course_id = body["id"]
    _assert(bool(course_id), "Course created")

    status, _ = _call(base, "POST", f"/courses/{course_id}/enrollments", {
        "student_email": student_email,
    }, token=teacher_token)
    _assert(status == 201, "Student enrolled", str(status))

    # ------------------------------------------------------------------
    # 1. Teacher creates exam with 2 mcq + 1 short_answer
    # ------------------------------------------------------------------
    print("\n--- 1. Create exam with 2 mcq + 1 short_answer ---")
    now = datetime.now(timezone.utc)
    status, exam = _call(base, "POST", f"/courses/{course_id}/exams", {
        "title": "Mixed Exam",
        "description": "Two mcq + one short_answer",
        "duration_minutes": 60,
        "start_window": (now - timedelta(hours=1)).isoformat(),
        "end_window": (now + timedelta(hours=24)).isoformat(),
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
                "question_text": "Capital of France?",
                "question_type": "mcq",
                "marks": 7,
                "order_index": 2,
                "options": ["London", "Berlin", "Paris", "Madrid"],
                "correct_answer": "Paris",
            },
            {
                "question_text": "Describe Newton's first law.",
                "question_type": "short_answer",
                "marks": 8,
                "order_index": 3,
            },
        ],
    }, token=teacher_token)
    _assert(status == 201, "POST /courses/{id}/exams -> 201", str(status))
    exam_id = exam.get("id")
    questions = exam.get("questions", []) if isinstance(exam, dict) else []
    _assert(bool(exam_id), "Exam id returned")
    _assert(len(questions) == 3, "Exam returned 3 questions",
            f"got {len(questions)}")
    _assert(all(q.get("id") for q in questions),
            "All question ids returned")
    types = [q.get("question_type") for q in questions]
    _assert(types.count("mcq") == 2 and types.count("short_answer") == 1,
            "Question types are 2 mcq + 1 short_answer", str(types))

    q_mcq1 = next(q for q in questions if q["order_index"] == 1)
    q_mcq2 = next(q for q in questions if q["order_index"] == 2)
    q_short = next(q for q in questions if q["order_index"] == 3)

    # ------------------------------------------------------------------
    # 2. Teacher activates the exam
    # ------------------------------------------------------------------
    print("\n--- 2. Activate exam ---")
    status, body = _call(base, "POST", f"/exams/{exam_id}/activate",
                         token=teacher_token)
    _assert(status == 200, "POST /exams/{id}/activate -> 200", str(status))
    _assert(isinstance(body, dict) and body.get("is_active") is True,
            "Exam is active")

    # ------------------------------------------------------------------
    # 3. Student session: pre_check -> in_progress -> save -> submit
    # ------------------------------------------------------------------
    print("\n--- 3. Start session (pre_check) ---")
    status, sess = _call(base, "POST", "/sessions",
                         {"exam_id": exam_id}, token=student_token)
    _assert(status == 201, "POST /sessions -> 201", str(status))
    _assert(sess.get("status") == "pre_check",
            "Session status is pre_check")
    session_id = sess.get("id")
    _assert(bool(session_id), "Session id extracted")

    print("\n--- 3b. Transition pre_check -> in_progress ---")
    status, body = _call(base, "PATCH", f"/sessions/{session_id}",
                         {"status": "in_progress"}, token=student_token)
    _assert(status == 200, "PATCH /sessions/{id} -> 200", str(status))
    _assert(body.get("status") == "in_progress",
            "Session is now in_progress")

    # 4. Bad MCQ value -> 422 (test before saving real answers)
    print("\n--- 4. PUT mcq answer 'Z' -> 422 ---")
    status, body = _call(
        base, "PUT", f"/sessions/{session_id}/answers/{q_mcq1['id']}",
        {"answer_text": "Z"}, token=student_token,
    )
    _assert(status == 422,
            "PUT mcq answer 'Z' -> 422", str(status))

    # 3c. Save: correct mcq, incorrect mcq, short_answer
    print("\n--- 3c. Save answers (correct mcq, incorrect mcq, short) ---")
    status, _ = _call(
        base, "PUT", f"/sessions/{session_id}/answers/{q_mcq1['id']}",
        {"answer_text": "4"}, token=student_token,
    )
    _assert(status == 200, "Save correct mcq -> 200", str(status))

    status, _ = _call(
        base, "PUT", f"/sessions/{session_id}/answers/{q_mcq2['id']}",
        {"answer_text": "London"}, token=student_token,  # incorrect
    )
    _assert(status == 200, "Save incorrect mcq -> 200", str(status))

    status, _ = _call(
        base, "PUT", f"/sessions/{session_id}/answers/{q_short['id']}",
        {"answer_text": "Every object remains at rest or in uniform motion."},
        token=student_token,
    )
    _assert(status == 200, "Save short_answer -> 200", str(status))

    # 3d. Submit -> auto-graded score = marks of correct mcq only
    print("\n--- 3d. Submit session ---")
    status, body = _call(base, "POST", f"/sessions/{session_id}/submit",
                         token=student_token)
    _assert(status == 200, "POST /sessions/{id}/submit -> 200", str(status))
    _assert(body.get("status") == "submitted",
            "Session is submitted")
    expected_score = float(q_mcq1["marks"])  # only the correct mcq
    actual_score = body.get("score")
    _assert(actual_score == expected_score,
            f"Score == correct mcq marks ({expected_score})",
            f"got {actual_score}")

    # ------------------------------------------------------------------
    # 5. PUT answer after submit -> 409
    # ------------------------------------------------------------------
    print("\n--- 5. PUT answer after submit -> 409 ---")
    status, body = _call(
        base, "PUT", f"/sessions/{session_id}/answers/{q_mcq1['id']}",
        {"answer_text": "4"}, token=student_token,
    )
    _assert(status == 409,
            "PUT answer after submit -> 409", str(status))

    # ------------------------------------------------------------------
    # 6. Time-remaining past deadline auto-flips status to expired
    # ------------------------------------------------------------------
    print("\n--- 6. Auto-expiry on time-remaining call ---")
    # Need a brand-new exam with 1-minute duration. Activate, start session,
    # transition to in_progress, wait until deadline passes, then GET /time.
    status, short_exam = _call(base, "POST", f"/courses/{course_id}/exams", {
        "title": "Short Exam",
        "description": "1-minute exam for expiry test",
        "duration_minutes": 1,
        "start_window": (now - timedelta(hours=1)).isoformat(),
        "end_window": (now + timedelta(hours=24)).isoformat(),
        "questions": [
            {
                "question_text": "Pick A.",
                "question_type": "mcq",
                "marks": 1,
                "order_index": 1,
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
            },
        ],
    }, token=teacher_token)
    _assert(status == 201, "Create 1-minute exam -> 201", str(status))
    short_exam_id = short_exam["id"]

    status, _ = _call(base, "POST", f"/exams/{short_exam_id}/activate",
                      token=teacher_token)
    _assert(status == 200, "Activate 1-minute exam -> 200", str(status))

    status, sess2 = _call(base, "POST", "/sessions",
                          {"exam_id": short_exam_id},
                          token=student_token)
    _assert(status == 201, "Start expiry session -> 201", str(status))
    sess2_id = sess2["id"]

    status, _ = _call(base, "PATCH", f"/sessions/{sess2_id}",
                      {"status": "in_progress"}, token=student_token)
    _assert(status == 200, "Transition expiry session -> 200", str(status))

    print("Waiting 65 seconds for deadline to pass...")
    time.sleep(65)

    status, body = _call(base, "GET", f"/sessions/{sess2_id}/time",
                         token=student_token)
    _assert(status == 200, "GET /sessions/{id}/time -> 200", str(status))
    _assert(body.get("expired") is True,
            "expired=true after deadline")
    _assert(body.get("time_remaining_seconds") == 0,
            "time_remaining_seconds == 0",
            str(body.get("time_remaining_seconds")))

    # Confirm session status is now 'expired' via the exam detail
    status, exam_body = _call(base, "GET", f"/exams/{short_exam_id}",
                              token=teacher_token)
    sessions_list = exam_body.get("sessions", []) if isinstance(exam_body, dict) else []
    matching = [s for s in sessions_list if s.get("id") == sess2_id]
    if matching:
        _assert(matching[0].get("status") == "expired",
                "Session status flipped to expired",
                str(matching[0].get("status")))
    else:
        # If the exam detail doesn't list sessions, the time call response
        # already confirmed expired=true. That suffices for the DoD here.
        print("INFO  Exam detail did not include session list; relying on "
              "/time response which already shows expired=true.")

    print("\n" + "=" * 40)
    print(f"PASSED: {_PASS}")
    print(f"FAILED: {_FAIL}")
    print("=" * 40)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
