"""Verification script for Part 12: incidents, teacher reports, dummy seed.

Definition of Done coverage:
  1. POST /_seed without token -> 404
  2. POST /_seed with token -> 200 + summary + credentials
  3. Login as the demo teacher and the demo student
  4. Teacher's first exam can be activated if not already; student starts a
     session against it, transitions to in_progress, posts a single incident,
     posts a bulk batch of incidents, saves answers, submits.
  5. Teacher reports:
       - GET /teacher/exams/<id>/sessions -> includes the student's session
         with incident_count > 0 and highest_incident_severity == 'critical'
       - GET /teacher/sessions/<id>/detail -> includes questions with
         correct_option for the teacher, incidents ordered by occurred_at,
         and aggregate by_type / by_severity
       - POST /teacher/sessions/<id>/grade -> marks_awarded set on the
         short_answer questions; score recomputed
       - GET /teacher/exams/<id>/analytics -> includes sessions_by_status,
         score_stats, top incident types, percent_submitted_with_critical
  6. Negative auth checks (student blocked from teacher reports, etc.)

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\verify_part12.py
    .\\.venv\\Scripts\\python.exe scripts\\verify_part12.py --base https://your.app.up.railway.app --seed-token <token>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Optional[Any]]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(url=url, method=method, data=data, headers=headers)
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
    parser.add_argument("--seed-token",
                        default=os.environ.get("SEED_TOKEN",
                                               "dev-seed-token-local"))
    args = parser.parse_args()
    base = args.base.rstrip("/") + "/api/v1"
    print(f"Verifying against: {base}\n")

    # ------------------------------------------------------------------
    # 1. Seed without token -> 404
    # ------------------------------------------------------------------
    print("--- 1. /_seed without token -> 404 ---")
    status, _ = _call(base, "POST", "/_seed")
    _assert(status == 404, "POST /_seed (no header) -> 404", str(status))

    print("\n--- 1b. /_seed with wrong token -> 404 ---")
    status, _ = _call(base, "POST", "/_seed",
                      extra_headers={"X-Seed-Token": "wrong"})
    _assert(status == 404, "POST /_seed (bad header) -> 404", str(status))

    # ------------------------------------------------------------------
    # 2. Seed with correct token -> 200 + summary
    # ------------------------------------------------------------------
    print("\n--- 2. /_seed with correct token ---")
    status, body = _call(base, "POST", "/_seed",
                         extra_headers={"X-Seed-Token": args.seed_token})
    _assert(status == 200, "POST /_seed -> 200", str(status))
    _assert(isinstance(body, dict) and body.get("ok") is True,
            "Seed response ok=true")
    counts = body.get("counts", {}) if isinstance(body, dict) else {}
    _assert(counts.get("departments") == 2, "2 departments",
            str(counts.get("departments")))
    _assert(counts.get("teachers") == 3, "3 teachers",
            str(counts.get("teachers")))
    _assert(counts.get("courses") == 6, "6 courses",
            str(counts.get("courses")))
    _assert(counts.get("students") == 30, "30 students",
            str(counts.get("students")))
    _assert(counts.get("exams") == 12, "12 exams",
            str(counts.get("exams")))
    _assert(counts.get("questions") == 120, "120 questions",
            str(counts.get("questions")))

    creds = body.get("credentials", {}) if isinstance(body, dict) else {}
    teacher_email = creds.get("demo_teacher_email")
    student_email = creds.get("demo_student_email")
    password = creds.get("password")
    _assert(bool(teacher_email), "Demo teacher email returned")
    _assert(bool(student_email), "Demo student email returned")
    _assert(password == "pass123", "Shared password is pass123",
            str(password))

    # ------------------------------------------------------------------
    # 3. Login as both
    # ------------------------------------------------------------------
    print("\n--- 3. Login demo accounts ---")
    status, body = _call(base, "POST", "/auth/login",
                         {"email": teacher_email, "password": password})
    _assert(status == 200, "Teacher login -> 200", str(status))
    teacher_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(teacher_token), "Teacher token extracted")

    status, body = _call(base, "POST", "/auth/login",
                         {"email": student_email, "password": password})
    _assert(status == 200, "Student login -> 200", str(status))
    student_token = body.get("access_token") if isinstance(body, dict) else None
    _assert(bool(student_token), "Student token extracted")

    # ------------------------------------------------------------------
    # 4. Find an active exam the demo student is enrolled in
    # ------------------------------------------------------------------
    print("\n--- 4. Find a workable active exam for the demo student ---")
    status, body = _call(base, "GET", "/exams/active?page_size=100",
                         token=student_token)
    _assert(status == 200, "GET /exams/active -> 200", str(status))
    items = body.get("items", []) if isinstance(body, dict) else []
    _assert(len(items) >= 1, "Student has at least one active exam",
            str(len(items)))
    if not items:
        print(f"\nPASSED: {_PASS}\nFAILED: {_FAIL}")
        return 1

    # Pick an exam whose course is owned by the demo teacher.
    # Strategy: try each active exam until /exams/{id}/sessions returns 200
    # for the teacher (i.e. teacher owns the course).
    exam_id = None
    for item in items:
        candidate = item.get("id")
        st, _ = _call(base, "GET",
                      f"/teacher/exams/{candidate}/sessions",
                      token=teacher_token)
        if st == 200:
            exam_id = candidate
            break
    _assert(exam_id is not None,
            "Found an active exam owned by the demo teacher",
            "no overlap")
    if exam_id is None:
        print(f"\nPASSED: {_PASS}\nFAILED: {_FAIL}")
        return 1

    # ------------------------------------------------------------------
    # 5. Student starts session, transitions to in_progress, posts
    #    a single incident, then a bulk batch.
    # ------------------------------------------------------------------
    print("\n--- 5. Start session ---")
    status, body = _call(base, "POST", "/sessions",
                         {"exam_id": exam_id}, token=student_token)
    _assert(status == 201, "POST /sessions -> 201", str(status))
    session = body if isinstance(body, dict) else {}
    session_id = session.get("id")
    _assert(bool(session_id), "Session id extracted")
    question_list = session.get("questions", [])

    print("\n--- 5b. Transition to in_progress ---")
    status, _ = _call(base, "PATCH", f"/sessions/{session_id}",
                      {"status": "in_progress"}, token=student_token)
    _assert(status == 200, "PATCH /sessions/{id} -> 200", str(status))

    # ------------------------------------------------------------------
    # 6. Post a single incident
    # ------------------------------------------------------------------
    print("\n--- 6. POST single incident ---")
    status, body = _call(
        base, "POST",
        f"/sessions/{session_id}/incident",
        {
            "type": "FOCUS_LOST",
            "severity": "warning",
            "description": "Alt-tab detected during exam.",
        },
        token=student_token,
    )
    _assert(status == 201, "POST single incident -> 201", str(status))
    if isinstance(body, dict):
        _assert(body.get("type") == "FOCUS_LOST", "Returned type matches")
        _assert(body.get("severity") == "warning", "Returned severity matches")
        _assert(body.get("occurred_at") is not None,
                "Server-set occurred_at present")

    # ------------------------------------------------------------------
    # 7. Reject unknown type -> 422
    # ------------------------------------------------------------------
    print("\n--- 7. Unknown incident type -> 422 ---")
    status, _ = _call(
        base, "POST",
        f"/sessions/{session_id}/incident",
        {"type": "TOTALLY_BOGUS", "severity": "info"},
        token=student_token,
    )
    _assert(status == 422, "Unknown type -> 422", str(status))

    # ------------------------------------------------------------------
    # 8. Bulk post -- one critical + two info
    # ------------------------------------------------------------------
    print("\n--- 8. POST bulk incidents ---")
    status, body = _call(
        base, "POST",
        f"/sessions/{session_id}/incidents",
        {
            "incidents": [
                {"type": "VM_DETECTED", "severity": "critical",
                 "description": "VirtualBox guest additions present.",
                 "cpu_thermal_value": 300.0},
                {"type": "TIMING_ANOMALY", "severity": "info",
                 "timing_latency_ms": 1.23},
                {"type": "CLIPBOARD_SCRUB", "severity": "info",
                 "description": "Clipboard wiped on tick."},
            ],
        },
        token=student_token,
    )
    _assert(status == 201, "POST bulk incidents -> 201", str(status))
    if isinstance(body, dict):
        _assert(body.get("count") == 3, "Bulk count == 3",
                str(body.get("count")))
        _assert(len(body.get("items", [])) == 3, "Bulk items length == 3")
        _assert(all(isinstance(i.get("id"), int) for i in body.get("items", [])),
                "All bulk items have ids")

    # ------------------------------------------------------------------
    # 9. Save answers + submit so analytics has a non-empty submitted bucket
    # ------------------------------------------------------------------
    print("\n--- 9. Save one mcq answer + submit ---")
    if question_list:
        first_mcq = next(
            (q for q in question_list if q.get("question_type") == "mcq"),
            None,
        )
        if first_mcq:
            opt = (first_mcq.get("options") or ["A"])[0]
            st, _ = _call(
                base, "PUT",
                f"/sessions/{session_id}/answers/{first_mcq['id']}",
                {"answer_text": opt}, token=student_token,
            )
            _assert(st == 200, "Save first mcq answer -> 200", str(st))

    status, body = _call(base, "POST", f"/sessions/{session_id}/submit",
                         token=student_token)
    _assert(status == 200, "POST submit -> 200", str(status))
    score_after_submit = body.get("score") if isinstance(body, dict) else None
    _assert(score_after_submit is not None,
            "Submit returned a numeric score",
            str(score_after_submit))

    # ------------------------------------------------------------------
    # 10. Teacher: list sessions
    # ------------------------------------------------------------------
    print("\n--- 10. Teacher: GET /teacher/exams/{id}/sessions ---")
    status, body = _call(base, "GET",
                         f"/teacher/exams/{exam_id}/sessions",
                         token=teacher_token)
    _assert(status == 200, "GET teacher sessions list -> 200", str(status))
    items = body.get("items", []) if isinstance(body, dict) else []
    target = next((s for s in items if s.get("id") == session_id), None)
    _assert(target is not None, "Demo session present in teacher list")
    if target:
        _assert(target.get("incident_count", 0) >= 4,
                "incident_count >= 4 (1 single + 3 bulk)",
                str(target.get("incident_count")))
        _assert(target.get("highest_incident_severity") == "critical",
                "highest severity is 'critical'",
                str(target.get("highest_incident_severity")))
        _assert(target.get("student") is not None and
                target["student"].get("roll_number"),
                "Student summary includes roll_number")

    # ------------------------------------------------------------------
    # 11. Teacher: session detail
    # ------------------------------------------------------------------
    print("\n--- 11. Teacher: GET /teacher/sessions/{id}/detail ---")
    status, detail = _call(
        base, "GET", f"/teacher/sessions/{session_id}/detail",
        token=teacher_token,
    )
    _assert(status == 200, "GET teacher session detail -> 200", str(status))
    if isinstance(detail, dict):
        questions = detail.get("questions", [])
        _assert(len(questions) >= 1,
                "Detail includes questions",
                str(len(questions)))
        mcqs = [q for q in questions if q.get("question_type") == "mcq"]
        _assert(any(q.get("correct_option") for q in mcqs),
                "Teacher view includes correct_option on MCQs")
        incidents = detail.get("incidents", [])
        _assert(len(incidents) >= 4,
                "Detail incidents >= 4", str(len(incidents)))
        # Ordered by occurred_at ascending
        if len(incidents) >= 2:
            _assert(
                incidents[0].get("occurred_at") <= incidents[-1].get("occurred_at"),
                "Incidents ordered by occurred_at",
            )
        counts = detail.get("incident_counts", {})
        _assert(counts.get("total", 0) >= 4,
                "incident_counts.total >= 4",
                str(counts.get("total")))
        by_type = counts.get("by_type", {})
        _assert("VM_DETECTED" in by_type,
                "by_type includes VM_DETECTED")
        _assert(counts.get("by_severity", {}).get("critical", 0) >= 1,
                "by_severity.critical >= 1",
                str(counts.get("by_severity")))

    # ------------------------------------------------------------------
    # 12. Teacher: grade a short_answer question
    # ------------------------------------------------------------------
    print("\n--- 12. Teacher: POST /teacher/sessions/{id}/grade ---")
    short_qs = [q for q in (detail.get("questions") if isinstance(detail, dict) else []) if q.get("question_type") == "short_answer"]
    if short_qs:
        q = short_qs[0]
        target_marks = float(q["marks"])
        status, gbody = _call(
            base, "POST",
            f"/teacher/sessions/{session_id}/grade",
            {"grades": [{"question_id": q["id"],
                         "marks_awarded": target_marks}]},
            token=teacher_token,
        )
        _assert(status == 200, "POST grade -> 200", str(status))
        if isinstance(gbody, dict):
            _assert(gbody.get("graded_count") == 1, "graded_count == 1")
            _assert(gbody.get("score") is not None
                    and gbody.get("score") >= target_marks,
                    "New score includes the manual marks",
                    str(gbody.get("score")))

        # Out-of-range marks -> 422
        st, _ = _call(
            base, "POST",
            f"/teacher/sessions/{session_id}/grade",
            {"grades": [{"question_id": q["id"], "marks_awarded": 999.0}]},
            token=teacher_token,
        )
        _assert(st == 422, "Grade out-of-range -> 422", str(st))

        # Grading an MCQ question -> 422
        mcq_q = next((qq for qq in detail.get("questions", []) if qq.get("question_type") == "mcq"), None)
        if mcq_q:
            st, _ = _call(
                base, "POST",
                f"/teacher/sessions/{session_id}/grade",
                {"grades": [{"question_id": mcq_q["id"], "marks_awarded": 1.0}]},
                token=teacher_token,
            )
            _assert(st == 422, "Grade MCQ -> 422", str(st))

    # ------------------------------------------------------------------
    # 13. Teacher: analytics
    # ------------------------------------------------------------------
    print("\n--- 13. Teacher: GET /teacher/exams/{id}/analytics ---")
    status, an = _call(base, "GET",
                       f"/teacher/exams/{exam_id}/analytics",
                       token=teacher_token)
    _assert(status == 200, "GET analytics -> 200", str(status))
    if isinstance(an, dict):
        _assert("sessions_by_status" in an, "analytics has sessions_by_status")
        _assert(an.get("submitted_count", 0) >= 1, "submitted_count >= 1")
        _assert("score_stats" in an, "analytics has score_stats")
        _assert("incidents" in an, "analytics has incidents block")
        _assert(an["incidents"]["total"] >= 4,
                "analytics incidents.total >= 4")
        _assert(an["incidents"]["percent_submitted_with_critical"] >= 0,
                "percent_submitted_with_critical present")
        _assert(len(an["incidents"]["top_types"]) >= 1,
                "top_types has at least one entry")

    # ------------------------------------------------------------------
    # 14. Negative auth: student blocked from teacher endpoints
    # ------------------------------------------------------------------
    print("\n--- 14. Student blocked from teacher reports ---")
    status, _ = _call(base, "GET",
                      f"/teacher/exams/{exam_id}/sessions",
                      token=student_token)
    _assert(status == 403, "Student GET teacher sessions -> 403",
            str(status))

    status, _ = _call(base, "GET",
                      f"/teacher/sessions/{session_id}/detail",
                      token=student_token)
    _assert(status == 403, "Student GET teacher detail -> 403",
            str(status))

    # ------------------------------------------------------------------
    # 15. Submitted session rejects new incidents -> 409
    # ------------------------------------------------------------------
    print("\n--- 15. POST incident on submitted session -> 409 ---")
    status, _ = _call(
        base, "POST",
        f"/sessions/{session_id}/incident",
        {"type": "NETWORK_DROP", "severity": "info"},
        token=student_token,
    )
    _assert(status == 409, "Incident on submitted session -> 409",
            str(status))

    print("\n" + "=" * 40)
    print(f"PASSED: {_PASS}")
    print(f"FAILED: {_FAIL}")
    print("=" * 40)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
