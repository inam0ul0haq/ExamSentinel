"""Focused Railway verifier for prompt 12 acceptance points."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple
from urllib import error, request


PASS = 0
FAIL = 0


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
        url=base + path,
        method=method,
        data=data,
        headers=headers,
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


def check(condition: bool, label: str, detail: Any = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}  {detail}")


def require_status(status: int, expected: int, label: str, body: Any) -> bool:
    ok = status == expected
    detail = status if ok else f"status={status}, body={body}"
    check(ok, label, detail)
    return ok


def login(base: str, email: str, password: str) -> Optional[str]:
    status, body = call(
        base,
        "POST",
        "/auth/login",
        {"email": email, "password": password},
    )
    require_status(status, 200, f"login {email}", body)
    token = body.get("access_token") if isinstance(body, dict) else None
    check(bool(token), f"token extracted for {email}")
    return token


def find_teacher_active_exam(
    base: str,
    teacher_token: str,
    student_token: str,
) -> Optional[int]:
    status, body = call(
        base,
        "GET",
        "/exams/active?page_size=100",
        token=student_token,
    )
    if not require_status(status, 200, "student active exams list", body):
        return None

    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) > 0, "student has at least one active exam", len(items))

    for item in items:
        exam_id = item.get("id")
        if not isinstance(exam_id, int):
            continue
        st, _ = call(
            base,
            "GET",
            f"/teacher/exams/{exam_id}/analytics",
            token=teacher_token,
        )
        if st == 200:
            check(True, "found active demo-teacher exam for student session", exam_id)
            return exam_id

    check(False, "found active demo-teacher exam for student session", "no overlap")
    return None


def find_any_teacher_exam_for_zero_analytics(
    base: str,
    teacher_token: str,
    active_exam_id: Optional[int],
    scan_limit: int,
) -> Optional[int]:
    candidates = []
    if active_exam_id is not None:
        candidates.append(active_exam_id)
    candidates.extend(i for i in range(1, scan_limit + 1) if i != active_exam_id)

    for exam_id in candidates:
        status, body = call(
            base,
            "GET",
            f"/teacher/exams/{exam_id}/analytics",
            token=teacher_token,
        )
        if status == 200:
            check(True, "found one exam owned by demo teacher", exam_id)
            return exam_id

    check(False, "found one exam owned by demo teacher", f"scanned 1..{scan_limit}")
    return None


def assert_zero_analytics(base: str, teacher_token: str, exam_id: int) -> None:
    status, body = call(
        base,
        "GET",
        f"/teacher/exams/{exam_id}/analytics",
        token=teacher_token,
    )
    if not require_status(status, 200, "teacher exam analytics before sessions", body):
        return
    if not isinstance(body, dict):
        check(False, "analytics body is an object", body)
        return

    check(body.get("submitted_count") == 0, "analytics submitted_count == 0", body)
    check(body.get("sessions_by_status") == {}, "analytics sessions_by_status empty", body)
    stats = body.get("score_stats", {})
    check(
        all(stats.get(key) is None for key in ("mean", "median", "min", "max")),
        "analytics score stats are null with no sessions",
        stats,
    )
    incidents = body.get("incidents", {})
    check(incidents.get("total") == 0, "analytics incidents.total == 0", incidents)
    check(incidents.get("top_types") == [], "analytics incidents.top_types empty", incidents)
    check(
        incidents.get("percent_submitted_with_critical") == 0.0,
        "analytics percent critical == 0.0",
        incidents,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default="https://web-production-5a17d.up.railway.app",
    )
    parser.add_argument("--seed-token", default=os.environ.get("SEED_TOKEN"))
    parser.add_argument("--scan-limit", type=int, default=2000)
    args = parser.parse_args()

    if not args.seed_token:
        print("ERROR: provide --seed-token or set SEED_TOKEN.")
        return 2

    base = normalize_base(args.base)
    print(f"Verifying against: {base}\n")

    status, body = call(base, "POST", "/_seed")
    require_status(status, 404, "POST /_seed without header returns 404", body)

    status, body = call(
        base,
        "POST",
        "/_seed",
        extra_headers={"X-Seed-Token": args.seed_token},
    )
    if not require_status(status, 200, "POST /_seed with header returns 200", body):
        print(f"\nPASSED: {PASS}\nFAILED: {FAIL}")
        return 1

    counts = body.get("counts", {}) if isinstance(body, dict) else {}
    expected_counts = {
        "departments": 2,
        "teachers": 3,
        "students": 30,
        "courses": 6,
        "exams": 12,
        "questions": 120,
    }
    for key, expected in expected_counts.items():
        check(counts.get(key) == expected, f"seed count {key} == {expected}", counts)

    creds = body.get("credentials", {}) if isinstance(body, dict) else {}
    teacher_email = creds.get("demo_teacher_email")
    student_email = creds.get("demo_student_email")
    password = creds.get("password")
    check(bool(teacher_email), "credentials include demo teacher email", creds)
    check(bool(student_email), "credentials include demo student email", creds)
    check(bool(password), "credentials include password", creds)

    if not all([teacher_email, student_email, password]):
        print(f"\nPASSED: {PASS}\nFAILED: {FAIL}")
        return 1

    teacher_token = login(base, teacher_email, password)
    student_token = login(base, student_email, password)
    if not teacher_token or not student_token:
        print(f"\nPASSED: {PASS}\nFAILED: {FAIL}")
        return 1

    active_exam_id = find_teacher_active_exam(base, teacher_token, student_token)
    zero_exam_id = find_any_teacher_exam_for_zero_analytics(
        base,
        teacher_token,
        active_exam_id,
        args.scan_limit,
    )
    if zero_exam_id is not None:
        assert_zero_analytics(base, teacher_token, zero_exam_id)

    if active_exam_id is None:
        print(f"\nPASSED: {PASS}\nFAILED: {FAIL}")
        return 1

    status, body = call(
        base,
        "POST",
        "/sessions",
        {"exam_id": active_exam_id},
        token=student_token,
    )
    if not require_status(status, 201, "student starts active session", body):
        print(f"\nPASSED: {PASS}\nFAILED: {FAIL}")
        return 1

    session = body if isinstance(body, dict) else {}
    session_id = session.get("id")
    questions = session.get("questions", [])
    check(isinstance(session_id, int), "session id returned", session)

    status, body = call(
        base,
        "PATCH",
        f"/sessions/{session_id}",
        {"status": "in_progress"},
        token=student_token,
    )
    require_status(status, 200, "session transitions to in_progress", body)

    status, body = call(
        base,
        "POST",
        f"/sessions/{session_id}/incidents",
        {
            "incidents": [
                {"type": "VM_DETECTED", "severity": "critical", "description": "VM signal."},
                {"type": "TIMING_ANOMALY", "severity": "warning", "timing_latency_ms": 2.5},
                {"type": "CLIPBOARD_SCRUB", "severity": "info", "description": "Clipboard scrubbed."},
            ]
        },
        token=student_token,
    )
    require_status(status, 201, "bulk incident with three items returns 201", body)
    items = body.get("items", []) if isinstance(body, dict) else []
    check(len(items) == 3, "bulk incident returns three items", body)
    check(all(isinstance(item.get("id"), int) for item in items), "bulk incident items have ids", items)

    short_answer = next(
        (q for q in questions if q.get("question_type") == "short_answer"),
        None,
    )
    check(short_answer is not None, "session includes a short_answer question")
    if short_answer is not None:
        max_marks = float(short_answer.get("marks", 0))
        status, body = call(
            base,
            "POST",
            f"/teacher/sessions/{session_id}/grade",
            {
                "grades": [
                    {
                        "question_id": short_answer["id"],
                        "marks_awarded": max_marks + 1,
                    }
                ]
            },
            token=teacher_token,
        )
        require_status(
            status,
            422,
            "manual grading above short_answer max returns 422",
            body,
        )

    print("\n" + "=" * 40)
    print(f"PASSED: {PASS}")
    print(f"FAILED: {FAIL}")
    print("=" * 40)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
