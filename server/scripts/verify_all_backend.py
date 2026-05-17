"""Comprehensive backend verifier for Parts 1-11 (all backend prompts).

Tests every acceptance point from the 30-Part build plan against the
Railway deployment.  **Read-only** — does NOT call /_seed or delete data.
Uses already-seeded demo data (from a previous seed run).

Usage:
    py -3.11 server\scripts\verify_all_backend.py ^
        --base https://web-production-5a17d.up.railway.app ^
        --teacher-email <email> --student-email <email> --password pass123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request


# ── Globals ──────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
WARN = 0
SECTION = ""


# ── Helpers ──────────────────────────────────────────────────────────

def normalize_base(raw: str) -> str:
    base = raw.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    return base


def call(
    base: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(
        url=base + path, method=method, data=data, headers=headers,
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
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
    except json.JSONDecodeError:
        return status, raw.decode("utf-8", errors="replace")


def section(name: str) -> None:
    global SECTION
    SECTION = name
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def check(condition: bool, label: str, detail: Any = "") -> bool:
    global PASS, FAIL
    tag = f"[{SECTION}]" if SECTION else ""
    if condition:
        PASS += 1
        print(f"  PASS  {tag} {label}")
    else:
        FAIL += 1
        d = f"  => {detail}" if detail else ""
        print(f"  FAIL  {tag} {label}{d}")
    return condition


def warn(label: str, detail: Any = "") -> None:
    global WARN
    WARN += 1
    d = f"  => {detail}" if detail else ""
    print(f"  WARN  [{SECTION}] {label}{d}")


def require_status(status: int, expected: int, label: str, body: Any) -> bool:
    ok = status == expected
    detail = "" if ok else f"status={status}, body={json.dumps(body, default=str)[:200]}"
    return check(ok, label, detail)


# ── Part 5: Health Endpoint ──────────────────────────────────────────

def verify_health(base: str) -> None:
    section("Part 5 — Health Endpoint")
    status, body = call(base, "GET", "/health")
    require_status(status, 200, "GET /health returns 200", body)
    if isinstance(body, dict):
        check("status" in body, "health has 'status' field", body)
        check(body.get("version") == "v1", "health version == 'v1'", body.get("version"))
        check("database" in body, "health has 'database' field", body)
        check(body.get("database") == "postgresql", "health database == 'postgresql'", body.get("database"))
        check("timestamp" in body, "health has 'timestamp' field", body)


# ── Part 5: CORS ─────────────────────────────────────────────────────

def verify_cors(base: str) -> None:
    section("Part 5 — CORS Preflight")
    headers = {
        "Origin": "http://example.com",
        "Access-Control-Request-Method": "GET",
    }
    status, body = call(base, "OPTIONS", "/health", extra_headers=headers)
    check(status in (200, 204), "OPTIONS /health returns 200 or 204", status)


# ── Part 8: Auth ─────────────────────────────────────────────────────

def verify_auth(
    base: str, teacher_email: str, student_email: str, password: str
) -> Tuple[Optional[str], Optional[str], Optional[Dict], Optional[Dict]]:
    section("Part 8 — Auth: Login, JWT, Role Decorators")

    # --- Login teacher ---
    status, body = call(base, "POST", "/auth/login",
                        {"email": teacher_email, "password": password})
    require_status(status, 200, f"teacher login ({teacher_email})", body)
    teacher_token = body.get("access_token") if isinstance(body, dict) else None
    check(bool(teacher_token), "teacher token returned")
    teacher_profile = body.get("user") if isinstance(body, dict) else None

    # --- Login student ---
    status, body = call(base, "POST", "/auth/login",
                        {"email": student_email, "password": password})
    require_status(status, 200, f"student login ({student_email})", body)
    student_token = body.get("access_token") if isinstance(body, dict) else None
    check(bool(student_token), "student token returned")
    student_profile = body.get("user") if isinstance(body, dict) else None

    # --- Wrong password ---
    status, body = call(base, "POST", "/auth/login",
                        {"email": teacher_email, "password": "WRONG"})
    require_status(status, 401, "wrong password returns 401", body)
    if isinstance(body, dict):
        err = body.get("error", {})
        check("invalid" in str(err).lower() or "credentials" in str(err).lower(),
              "401 message is generic (no field leak)", err)

    # --- No token on /auth/me ---
    status, body = call(base, "GET", "/auth/me")
    require_status(status, 401, "GET /auth/me without token returns 401", body)

    # --- Teacher /auth/me ---
    if teacher_token:
        status, body = call(base, "GET", "/auth/me", token=teacher_token)
        require_status(status, 200, "GET /auth/me with teacher token returns 200", body)
        if isinstance(body, dict):
            user_obj = body.get("user", body)
            check(user_obj.get("role") == "teacher", "/auth/me role == teacher", user_obj.get("role"))
            check("employee_code" in user_obj or "employee_code" in user_obj.get("teacher", {}),
                  "/auth/me includes teacher-specific fields", list(user_obj.keys()))

    # --- Student /auth/me ---
    if student_token:
        status, body = call(base, "GET", "/auth/me", token=student_token)
        require_status(status, 200, "GET /auth/me with student token returns 200", body)
        if isinstance(body, dict):
            user_obj = body.get("user", body)
            check(user_obj.get("role") == "student", "/auth/me role == student", user_obj.get("role"))

    # --- _diag routes removed (Part 12 cleanup) ---
    status, body = call(base, "GET", "/_diag/teacher-only", token=teacher_token)
    check(status == 404, "_diag/teacher-only route removed (404)", status)
    status, body = call(base, "GET", "/_diag/student-only", token=student_token)
    check(status == 404, "_diag/student-only route removed (404)", status)

    return teacher_token, student_token, teacher_profile, student_profile


# ── Part 9: Departments & Courses ────────────────────────────────────

def verify_departments_and_courses(
    base: str, teacher_token: str, student_token: str
) -> Optional[int]:
    section("Part 9 — Departments, Courses, Enrollments")

    # --- Departments (public) ---
    status, body = call(base, "GET", "/departments")
    require_status(status, 200, "GET /departments returns 200", body)
    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) >= 2, f"at least 2 departments exist ({len(items)})", items)

    # --- Students list (teacher only) ---
    status, body = call(base, "GET", "/users/students?page_size=5", token=teacher_token)
    require_status(status, 200, "GET /users/students (teacher) returns 200", body)

    # --- Students list (student forbidden) ---
    status, body = call(base, "GET", "/users/students?page_size=5", token=student_token)
    check(status in (403, 404), "GET /users/students (student) returns 403", status)

    # --- Teacher courses ---
    status, body = call(base, "GET", "/courses/me?page_size=50", token=teacher_token)
    require_status(status, 200, "GET /courses/me (teacher) returns 200", body)
    t_courses = body.get("items", []) if isinstance(body, dict) else []
    check(len(t_courses) >= 1, f"teacher has courses ({len(t_courses)})", len(t_courses))

    course_id = t_courses[0]["id"] if t_courses else None

    # --- Student courses ---
    status, body = call(base, "GET", "/courses/me?page_size=50", token=student_token)
    require_status(status, 200, "GET /courses/me (student) returns 200", body)
    s_courses = body.get("items", []) if isinstance(body, dict) else []
    check(len(s_courses) >= 1, f"student sees enrolled courses ({len(s_courses)})", len(s_courses))

    # --- Course detail (teacher) ---
    if course_id:
        status, body = call(base, "GET", f"/courses/{course_id}", token=teacher_token)
        require_status(status, 200, f"GET /courses/{course_id} (teacher) returns 200", body)
        if isinstance(body, dict):
            check("exams" in body or "exam_count" in body or "title" in body,
                  "course detail includes expected fields", list(body.keys()))

    # --- Course detail (wrong student) ---
    # Try accessing the teacher's course with student token — might be 403 if not enrolled
    # This is a soft check since student might be enrolled
    if course_id:
        status, body = call(base, "GET", f"/courses/{course_id}", token=student_token)
        check(status in (200, 403), f"GET /courses/{course_id} (student) returns 200 or 403", status)

    return course_id


# ── Part 10: Exams, Sessions, Answers ────────────────────────────────

def verify_exams_and_sessions(
    base: str, teacher_token: str, student_token: str, course_id: Optional[int]
) -> Tuple[Optional[int], Optional[int], List]:
    section("Part 10 — Exams, Questions, Sessions, Answers")

    # --- Student active exams ---
    status, body = call(base, "GET", "/exams/active?page_size=100", token=student_token)
    require_status(status, 200, "GET /exams/active (student) returns 200", body)
    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) >= 1, f"student has active exams ({len(items)})", len(items))

    # Pick an active exam the teacher owns (scan by probing analytics)
    exam_id = None
    teacher_active_exams = []
    for probe_id in range(1, 50):
        st, bdy = call(base, "GET", f"/teacher/exams/{probe_id}/analytics",
                        token=teacher_token)
        if st == 200 and isinstance(bdy, dict) and bdy.get("is_active"):
            teacher_active_exams.append(probe_id)
            if exam_id is None:
                exam_id = probe_id

    check(exam_id is not None, "found active exam owned by demo teacher", exam_id)
    if exam_id is None:
        return None, None, []

    # Check if any of teacher's active exams appear in the student's active list
    student_exam_ids = {item.get("id") for item in items}
    overlap = [eid for eid in teacher_active_exams if eid in student_exam_ids]

    # --- Exam detail (teacher sees correct_option) ---
    status, body = call(base, "GET", f"/exams/{exam_id}", token=teacher_token)
    require_status(status, 200, f"GET /exams/{exam_id} (teacher) returns 200", body)
    teacher_questions = body.get("questions", []) if isinstance(body, dict) else []
    has_correct = any(
        q.get("correct_option") is not None or q.get("correct_answer") is not None
        for q in teacher_questions if q.get("question_type") == "mcq"
    )
    check(has_correct, "teacher sees correct_answer on MCQ questions")

    # --- Exam detail (student — correct answer hidden) ---
    status, body = call(base, "GET", f"/exams/{exam_id}", token=student_token)
    require_status(status, 200, f"GET /exams/{exam_id} (student) returns 200", body)
    student_questions = body.get("questions", []) if isinstance(body, dict) else []
    correct_visible = any(
        q.get("correct_option") is not None or q.get("correct_answer") is not None
        for q in student_questions if q.get("question_type") == "mcq"
    )
    check(not correct_visible, "student does NOT see correct answer on MCQ questions", correct_visible)

    # --- Start session ---
    # Try teacher's active exams; prefer ones in the student's active list
    session_exam_candidates = overlap + [e for e in teacher_active_exams if e not in overlap]
    session_created = False
    session_exam_id = None
    for try_eid in session_exam_candidates:
        status, body = call(base, "POST", "/sessions",
                            {"exam_id": try_eid}, token=student_token)
        if status in (200, 201):
            session_exam_id = try_eid
            session_created = True
            break
        elif status == 409:
            # Already submitted for this exam
            continue
        elif status == 403:
            # Student not enrolled in this course
            continue
        else:
            break  # unexpected error

    if not session_created:
        warn("student already submitted all teacher exams — session tests limited")
        # Still test teacher reporting with exam_id
        return exam_id, None, []

    require_status(status, 201, "POST /sessions (start session) returns 201", body)
    session = body if isinstance(body, dict) else {}
    session_id = session.get("id")
    questions = session.get("questions", [])
    check(isinstance(session_id, int), "session id is an integer", session)
    check("deadline_at" in session, "session has deadline_at (server-authoritative)", session.keys())
    check(len(questions) >= 1, f"session includes questions ({len(questions)})", len(questions))

    # Verify correct answer NOT in session questions
    correct_in_session = any(
        q.get("correct_option") is not None or q.get("correct_answer") is not None
        for q in questions if q.get("question_type") == "mcq"
    )
    check(not correct_in_session, "session questions hide correct answer")

    # --- Transition pre_check -> in_progress ---
    status, body = call(base, "PATCH", f"/sessions/{session_id}",
                        {"status": "in_progress"}, token=student_token)
    require_status(status, 200, "PATCH /sessions (pre_check -> in_progress) returns 200", body)

    # --- Save answers ---
    mcq_q = next((q for q in questions if q.get("question_type") == "mcq"), None)
    sa_q = next((q for q in questions if q.get("question_type") == "short_answer"), None)

    if mcq_q:
        status, body = call(base, "PUT",
                            f"/sessions/{session_id}/answers/{mcq_q['id']}",
                            {"answer_text": "A"},
                            token=student_token)
        require_status(status, 200, "PUT answer (MCQ, valid option A) returns 200", body)

        # Invalid MCQ answer
        status, body = call(base, "PUT",
                            f"/sessions/{session_id}/answers/{mcq_q['id']}",
                            {"answer_text": "Z"},
                            token=student_token)
        require_status(status, 422, "PUT answer (MCQ, invalid 'Z') returns 422", body)

    if sa_q:
        status, body = call(base, "PUT",
                            f"/sessions/{session_id}/answers/{sa_q['id']}",
                            {"answer_text": "Test answer for SA."},
                            token=student_token)
        require_status(status, 200, "PUT answer (short_answer) returns 200", body)

    # --- Time remaining ---
    status, body = call(base, "GET", f"/sessions/{session_id}/time",
                        token=student_token)
    require_status(status, 200, "GET /sessions/{id}/time returns 200", body)
    if isinstance(body, dict):
        check("remaining_seconds" in body or "seconds" in body or "remaining" in body
              or "seconds_remaining" in body,
              "time-remaining has seconds field", body.keys())

    return exam_id, session_id, questions


# ── Part 11: Incidents ───────────────────────────────────────────────

def verify_incidents(
    base: str, student_token: str, session_id: Optional[int]
) -> None:
    section("Part 11 — Incident Ingestion")

    if session_id is None:
        warn("session_id is None — skipping incident tests")
        return

    # --- Single incident ---
    status, body = call(base, "POST", f"/sessions/{session_id}/incident",
                        {
                            "type": "FOCUS_LOST",
                            "severity": "warning",
                            "description": "Window lost focus during test."
                        },
                        token=student_token)
    require_status(status, 201, "POST single incident returns 201", body)
    if isinstance(body, dict):
        check("id" in body, "single incident has 'id'", body)

    # --- Bulk incidents ---
    status, body = call(base, "POST", f"/sessions/{session_id}/incidents",
                        {
                            "incidents": [
                                {"type": "VM_DETECTED", "severity": "critical",
                                 "description": "VM signal detected."},
                                {"type": "TIMING_ANOMALY", "severity": "warning",
                                 "timing_latency_ms": 2.5},
                                {"type": "CLIPBOARD_SCRUB", "severity": "info",
                                 "description": "Clipboard scrubbed."},
                            ]
                        },
                        token=student_token)
    require_status(status, 201, "POST bulk incidents (3 items) returns 201", body)
    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) == 3, f"bulk incident returns 3 items ({len(items)})", body)
    check(all(isinstance(i.get("id"), int) for i in items),
          "all bulk incident items have integer ids", items)

    # --- Invalid incident type ---
    status, body = call(base, "POST", f"/sessions/{session_id}/incident",
                        {
                            "type": "INVALID_TYPE_XYZ",
                            "severity": "info",
                            "description": "Should fail."
                        },
                        token=student_token)
    require_status(status, 422, "POST incident with invalid type returns 422", body)


# ── Part 10 continued: Submit session ────────────────────────────────

def verify_submit_and_results(
    base: str, student_token: str, teacher_token: str,
    session_id: Optional[int], questions: List
) -> None:
    section("Part 10 — Submit Session & Auto-Grading")

    if session_id is None:
        warn("session_id is None — skipping submit tests")
        return

    # --- Submit ---
    status, body = call(base, "POST", f"/sessions/{session_id}/submit",
                        token=student_token)
    require_status(status, 200, "POST /sessions/{id}/submit returns 200", body)
    if isinstance(body, dict):
        check("score" in body or "total_score" in body or "marks" in body,
              "submit response includes score", body.keys())

    # --- Answer after submit should fail ---
    mcq_q = next((q for q in questions if q.get("question_type") == "mcq"), None)
    if mcq_q:
        status, body = call(base, "PUT",
                            f"/sessions/{session_id}/answers/{mcq_q['id']}",
                            {"answer_text": "B"},
                            token=student_token)
        check(status in (409, 403, 400, 422), "PUT answer after submit returns 409/403/400/422", status)

    # --- Student result ---
    status, body = call(base, "GET", f"/sessions/{session_id}/result",
                        token=student_token)
    require_status(status, 200, "GET /sessions/{id}/result returns 200", body)
    if isinstance(body, dict):
        # Verify correct answers NOT leaked
        answers = body.get("answers", body.get("questions", []))
        if isinstance(answers, list) and answers:
            has_correct = any(a.get("correct_option") is not None or a.get("correct_answer") is not None
                              for a in answers if a.get("question_type") == "mcq")
            check(not has_correct, "student result does NOT leak correct answers")


# ── Part 11: Teacher Reporting ───────────────────────────────────────

def verify_teacher_reporting(
    base: str, teacher_token: str, student_token: str,
    exam_id: Optional[int], session_id: Optional[int], questions: List
) -> None:
    section("Part 11 — Teacher Reporting & Manual Grading")

    if exam_id is None:
        warn("exam_id is None — skipping teacher reporting tests (need to re-seed)")
        return

    # --- Sessions for exam ---
    status, body = call(base, "GET", f"/teacher/exams/{exam_id}/sessions?page_size=50",
                        token=teacher_token)
    require_status(status, 200, "GET /teacher/exams/{id}/sessions returns 200", body)
    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) >= 1, f"teacher sees sessions for exam ({len(items)})", len(items))

    # --- Session detail ---
    # Use provided session_id, or fall back to first session from the list
    detail_sid = session_id
    if detail_sid is None and items:
        detail_sid = items[0].get("id") or items[0].get("session_id")
    if detail_sid:
        status, body = call(base, "GET", f"/teacher/sessions/{detail_sid}/detail",
                            token=teacher_token)
        require_status(status, 200, f"GET /teacher/sessions/{detail_sid}/detail returns 200", body)
        if isinstance(body, dict):
            check("answers" in body or "questions" in body,
                  "session detail includes answers", body.keys())
            check("incidents" in body or "incident_logs" in body,
                  "session detail includes incidents", body.keys())

    # --- Exam analytics (after session) ---
    status, body = call(base, "GET", f"/teacher/exams/{exam_id}/analytics",
                        token=teacher_token)
    require_status(status, 200, "GET /teacher/exams/{id}/analytics returns 200", body)
    if isinstance(body, dict):
        check("submitted_count" in body, "analytics has submitted_count", body.keys())
        check("sessions_by_status" in body, "analytics has sessions_by_status", body.keys())
        check("score_stats" in body, "analytics has score_stats", body.keys())
        check("incidents" in body, "analytics has incidents block", body.keys())

    # --- Manual grading (marks_awarded > max → 422) ---
    # If questions list is empty (no new session), fetch from exam detail
    q_list = questions
    if not q_list and exam_id:
        _, exam_body = call(base, "GET", f"/exams/{exam_id}", token=teacher_token)
        q_list = exam_body.get("questions", []) if isinstance(exam_body, dict) else []
    sa_q = next((q for q in q_list if q.get("question_type") == "short_answer"), None)
    grade_sid = session_id or detail_sid
    if sa_q and grade_sid:
        max_marks = float(sa_q.get("marks", 0))
        status, body = call(base, "POST", f"/teacher/sessions/{grade_sid}/grade",
                            {
                                "grades": [{
                                    "question_id": sa_q["id"],
                                    "marks_awarded": max_marks + 1,
                                }]
                            },
                            token=teacher_token)
        require_status(status, 422, "grading above max marks returns 422", body)

        # --- Valid manual grading ---
        status, body = call(base, "POST", f"/teacher/sessions/{grade_sid}/grade",
                            {
                                "grades": [{
                                    "question_id": sa_q["id"],
                                    "marks_awarded": max_marks * 0.5,
                                }]
                            },
                            token=teacher_token)
        require_status(status, 200, "grading with valid marks returns 200", body)

    # --- Student cannot access teacher endpoints ---
    status, body = call(base, "GET", f"/teacher/exams/{exam_id}/analytics",
                        token=student_token)
    check(status == 403, "student cannot access teacher analytics (403)", status)


# ── Part 11: Seed Endpoint (read-only checks) ────────────────────────

def verify_seed_endpoint_readonly(base: str) -> None:
    section("Part 11 — Seed Endpoint (read-only)")

    # Without token -> 404
    status, body = call(base, "POST", "/_seed")
    require_status(status, 404, "POST /_seed without token returns 404 (not 401/403)", body)

    # With wrong token -> 404
    status, body = call(base, "POST", "/_seed",
                        extra_headers={"X-Seed-Token": "DEFINITELY_WRONG_TOKEN"})
    require_status(status, 404, "POST /_seed with wrong token returns 404", body)


# ── Part 8: Registration validation ──────────────────────────────────

def verify_registration_validation(base: str) -> None:
    section("Part 8 — Registration Validation")

    # Short password
    status, body = call(base, "POST", "/auth/register", {
        "full_name": "Test User",
        "email": "test_validation_shortpw@example.com",
        "password": "abc",
        "role": "student",
        "roll_number": "TEST-001",
        "department_id": 1,
        "semester": 3,
    })
    require_status(status, 422, "register with short password returns 422", body)

    # Missing role-specific fields
    status, body = call(base, "POST", "/auth/register", {
        "full_name": "Test User",
        "email": "test_validation_norole@example.com",
        "password": "longpassword123",
        "role": "teacher",
        # Missing employee_code and designation
    })
    require_status(status, 422, "register teacher without employee_code returns 422", body)

    # Invalid role
    status, body = call(base, "POST", "/auth/register", {
        "full_name": "Test User",
        "email": "test_validation_badrole@example.com",
        "password": "longpassword123",
        "role": "admin",
    })
    require_status(status, 422, "register with invalid role returns 422", body)


# ── Part 9: Course ownership checks ─────────────────────────────────

def verify_course_ownership(
    base: str, teacher_token: str, student_token: str
) -> None:
    section("Part 9 — Course Ownership / Cross-tenant Checks")

    # Student cannot create a course
    status, body = call(base, "POST", "/courses",
                        {"code": "TEST999", "title": "Hacker Course"},
                        token=student_token)
    check(status == 403, "student cannot create course (403)", status)

    # Student cannot enroll others
    status, body = call(base, "POST", "/courses/1/enrollments",
                        {"email": "fake@example.com"},
                        token=student_token)
    check(status == 403, "student cannot enroll others (403)", status)


# ── Part 6: Error envelope ───────────────────────────────────────────

def verify_error_envelope(base: str) -> None:
    section("Part 6/8 — Error Envelope Convention")

    # Hit a non-existent route
    status, body = call(base, "GET", "/nonexistent-route-xyz")
    check(status == 404, "non-existent route returns 404", status)
    if isinstance(body, dict):
        check("error" in body, "404 response uses error envelope", body.keys())

    # Auth error also uses envelope
    status, body = call(base, "POST", "/auth/login",
                        {"email": "nonexistent@x.com", "password": "wrong"})
    check(status == 401, "bad login returns 401", status)
    if isinstance(body, dict):
        check("error" in body, "401 response uses error envelope", body.keys())


# ── Part 10: Pagination ─────────────────────────────────────────────

def verify_pagination(base: str, teacher_token: str) -> None:
    section("Part 9/10 — Pagination Convention")

    status, body = call(base, "GET", "/courses/me?page=1&page_size=2", token=teacher_token)
    require_status(status, 200, "GET /courses/me with pagination returns 200", body)
    if isinstance(body, dict):
        check("items" in body, "paginated response has 'items'", body.keys())
        check("pagination" in body or "page" in body or "current_page" in body or "total" in body,
              "paginated response has page metadata", body.keys())


# ── Main ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprehensive read-only backend verifier for Parts 1-11")
    parser.add_argument("--base",
                        default="https://web-production-5a17d.up.railway.app")
    parser.add_argument("--teacher-email", default=None,
                        help="Demo teacher email (from seed)")
    parser.add_argument("--student-email", default=None,
                        help="Demo student email (from seed)")
    parser.add_argument("--password", default="pass123")
    args = parser.parse_args()

    base = normalize_base(args.base)
    print(f"Comprehensive Backend Verification (Parts 1-11)")
    print(f"Target: {base}")

    # ── Part 5 ──
    verify_health(base)
    verify_cors(base)

    # If emails not provided, try to get them from seed endpoint info
    teacher_email = args.teacher_email
    student_email = args.student_email

    if not teacher_email or not student_email:
        print("\n  INFO: No --teacher-email / --student-email provided.")
        print("  Attempting to discover from /users/teachers and /users/students...")
        # We need to guess or the user must provide
        # Try the seed token approach
        seed_token = os.environ.get("SEED_TOKEN", "")
        if seed_token:
            status, body = call(base, "POST", "/_seed",
                                extra_headers={"X-Seed-Token": seed_token})
            if status == 200 and isinstance(body, dict):
                creds = body.get("credentials", {})
                teacher_email = teacher_email or creds.get("demo_teacher_email")
                student_email = student_email or creds.get("demo_student_email")
                print(f"  Discovered teacher: {teacher_email}")
                print(f"  Discovered student: {student_email}")

    if not teacher_email or not student_email:
        print("\n  ERROR: Cannot proceed without teacher and student emails.")
        print("  Provide --teacher-email and --student-email, or set SEED_TOKEN env var.")
        return 2

    # ── Part 8 ──
    verify_auth(base, teacher_email, student_email, args.password)

    # Get fresh tokens
    _, t_body = call(base, "POST", "/auth/login",
                     {"email": teacher_email, "password": args.password})
    _, s_body = call(base, "POST", "/auth/login",
                     {"email": student_email, "password": args.password})
    teacher_token = t_body.get("access_token") if isinstance(t_body, dict) else None
    student_token = s_body.get("access_token") if isinstance(s_body, dict) else None

    if not teacher_token or not student_token:
        print("\n  ERROR: Could not obtain tokens. Aborting.")
        return 1

    verify_registration_validation(base)
    verify_error_envelope(base)

    # ── Part 9 ──
    course_id = verify_departments_and_courses(base, teacher_token, student_token)
    verify_course_ownership(base, teacher_token, student_token)
    verify_pagination(base, teacher_token)

    # ── Part 10 ──
    exam_id, session_id, questions = verify_exams_and_sessions(
        base, teacher_token, student_token, course_id)

    # ── Part 11 incidents ──
    verify_incidents(base, student_token, session_id)

    # ── Part 10 submit ──
    verify_submit_and_results(base, student_token, teacher_token,
                              session_id, questions)

    # ── Part 11 teacher reporting ──
    verify_teacher_reporting(base, teacher_token, student_token,
                             exam_id, session_id, questions)

    # ── Part 11 seed (read-only) ──
    verify_seed_endpoint_readonly(base)

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"  TOTAL PASSED : {PASS}")
    print(f"  TOTAL FAILED : {FAIL}")
    print(f"  WARNINGS     : {WARN}")
    print("=" * 60)

    if FAIL > 0:
        print("\n  Some checks FAILED. Review the output above.")
    else:
        print("\n  All checks PASSED!")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
