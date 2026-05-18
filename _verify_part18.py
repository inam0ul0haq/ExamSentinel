"""
Part 18 — end-to-end verification.

Flow:
  1. Teacher creates a fresh exam + activates
  2. Student login → create session → transition → answer → report incidents → submit
  3. Teacher login → list sessions → view detail → grade SA → verify analytics
  4. Check all client imports
"""

import sys
import requests
from datetime import datetime, timedelta, timezone

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
STUDENT_EMAIL = "ikramah.r.s001@pucit.edu.pk"
TEACHER_EMAIL = "baha.udeen.a.t1@pucit.edu.pk"
PASSWORD = "pass123"
TIMEOUT = 30

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> bool:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}  {detail}")
    return condition


# ═══════════════════════════════════════════════════════════════════
# 0. TEACHER: CREATE FRESH EXAM
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("0. TEACHER — CREATE FRESH EXAM")
print("=" * 60)

rt0 = requests.post(f"{BASE}/auth/login",
                    json={"email": TEACHER_EMAIL, "password": PASSWORD},
                    timeout=TIMEOUT)
check("Teacher login (seed)", rt0.status_code == 200, f"got {rt0.status_code}")
t_token = rt0.json().get("access_token", "")
TH = {"Authorization": f"Bearer {t_token}", "Content-Type": "application/json"}

rc = requests.get(f"{BASE}/courses/me?page_size=100", headers=TH, timeout=TIMEOUT)
courses = rc.json().get("items", [])
course_id = courses[0]["id"]

now = datetime.now(timezone.utc)
exam_body = {
    "title": f"Part18 Verify {now.strftime('%H%M%S')}",
    "description": "Auto-created for Part 18 e2e",
    "duration_minutes": 60,
    "start_window": (now - timedelta(hours=1)).isoformat(),
    "end_window": (now + timedelta(days=1)).isoformat(),
    "questions": [
        {"question_text": "What is Python?", "question_type": "mcq",
         "marks": 5, "order_index": 1,
         "options": ["A programming language", "A snake", "A database", "An OS"],
         "correct_answer": "A programming language"},
        {"question_text": "What is REST?", "question_type": "mcq",
         "marks": 5, "order_index": 2,
         "options": ["Representational State Transfer", "Rapid Exec", "Remote Server", "Runtime Env"],
         "correct_answer": "Representational State Transfer"},
        {"question_text": "What is Flask?", "question_type": "mcq",
         "marks": 5, "order_index": 3,
         "options": ["A Python web framework", "A Java lib", "A DB engine", "A test tool"],
         "correct_answer": "A Python web framework"},
        {"question_text": "Explain MVC.", "question_type": "short_answer",
         "marks": 10, "order_index": 4},
    ],
}
re0 = requests.post(f"{BASE}/courses/{course_id}/exams",
                    json=exam_body, headers=TH, timeout=TIMEOUT)
check("Create exam 201", re0.status_code == 201, f"got {re0.status_code}: {re0.text[:200]}")
exam_id = re0.json().get("id")
print(f"  exam_id={exam_id}")

ra0 = requests.post(f"{BASE}/exams/{exam_id}/activate", headers=TH, timeout=TIMEOUT)
check("Activate exam", ra0.status_code == 200, f"got {ra0.status_code}")


# ═══════════════════════════════════════════════════════════════════
# 1. STUDENT: LOGIN
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("1. STUDENT LOGIN")
print("=" * 60)

r = requests.post(f"{BASE}/auth/login",
                  json={"email": STUDENT_EMAIL, "password": PASSWORD},
                  timeout=TIMEOUT)
check("Student login 200", r.status_code == 200, f"got {r.status_code}")
s_token = r.json().get("access_token", "")
SH = {"Authorization": f"Bearer {s_token}", "Content-Type": "application/json"}
student_name = r.json().get("user", {}).get("full_name", "Unknown")
print(f"  Student: {student_name}")


# ═══════════════════════════════════════════════════════════════════
# 2. CREATE SESSION
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2. CREATE SESSION")
print("=" * 60)

r3 = requests.post(f"{BASE}/sessions",
                   json={"exam_id": exam_id}, headers=SH, timeout=TIMEOUT)
check("POST /sessions 2xx", r3.status_code in (200, 201),
      f"got {r3.status_code}: {r3.text[:200]}")

session_data = r3.json()
session_id = session_data.get("id") or session_data.get("session_id")
questions = session_data.get("questions", [])
check("Got session_id", session_id is not None)
check("Got questions", len(questions) >= 4, f"got {len(questions)}")
print(f"  session_id={session_id}  status={session_data.get('status')}  questions={len(questions)}")


# ═══════════════════════════════════════════════════════════════════
# 3. TRANSITION pre_check → in_progress
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3. TRANSITION TO in_progress")
print("=" * 60)

r4 = requests.patch(f"{BASE}/sessions/{session_id}",
                    json={"status": "in_progress"},
                    headers=SH, timeout=TIMEOUT)
check("PATCH transition 200", r4.status_code == 200,
      f"got {r4.status_code}: {r4.text[:200]}")


# ═══════════════════════════════════════════════════════════════════
# 4. SAVE ANSWERS
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4. SAVE ANSWERS")
print("=" * 60)

mcq_answered = False
sa_answered = False
for q in questions:
    qid = q.get("id")
    qtype = q.get("question_type")
    if qtype == "mcq" and not mcq_answered:
        options = q.get("options", [])
        if options:
            ra = requests.put(
                f"{BASE}/sessions/{session_id}/answers/{qid}",
                json={"answer_text": options[0]},
                headers=SH, timeout=TIMEOUT)
            check("Save MCQ answer", ra.status_code == 200,
                  f"got {ra.status_code}: {ra.text[:150]}")
            mcq_answered = True
    elif qtype == "short_answer" and not sa_answered:
        ra = requests.put(
            f"{BASE}/sessions/{session_id}/answers/{qid}",
            json={"answer_text": "MVC separates concerns into Model, View, and Controller."},
            headers=SH, timeout=TIMEOUT)
        check("Save SA answer", ra.status_code == 200,
              f"got {ra.status_code}: {ra.text[:150]}")
        sa_answered = True


# ═══════════════════════════════════════════════════════════════════
# 5. REPORT VIOLATIONS
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("5. REPORT VIOLATIONS")
print("=" * 60)

rv1 = requests.post(
    f"{BASE}/sessions/{session_id}/incident",
    json={"type": "FOCUS_LOST", "severity": "warning",
          "description": "Tab switch detected"},
    headers=SH, timeout=TIMEOUT)
check("Single incident 201", rv1.status_code == 201,
      f"got {rv1.status_code}: {rv1.text[:150]}")

rv2 = requests.post(
    f"{BASE}/sessions/{session_id}/incidents",
    json={"incidents": [
        {"type": "CLIPBOARD_SCRUB", "severity": "info",
         "description": "Clipboard cleared"},
        {"type": "KEYBOARD_BLOCKED", "severity": "critical",
         "description": "Blocked Alt+Tab"},
    ]},
    headers=SH, timeout=TIMEOUT)
check("Bulk incidents 201", rv2.status_code == 201,
      f"got {rv2.status_code}: {rv2.text[:150]}")


# ═══════════════════════════════════════════════════════════════════
# 6. SUBMIT EXAM
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("6. SUBMIT EXAM")
print("=" * 60)

rs = requests.post(f"{BASE}/sessions/{session_id}/submit",
                   headers=SH, timeout=TIMEOUT)
check("Submit 200", rs.status_code == 200,
      f"got {rs.status_code}: {rs.text[:200]}")
if rs.status_code == 200:
    sub = rs.json()
    print(f"  score={sub.get('score')} total={sub.get('total_marks')} status={sub.get('status')}")

print(f"\n  session_id={session_id} ready for teacher review")


# ═══════════════════════════════════════════════════════════════════
# 7. TEACHER: REUSE TOKEN FROM STEP 0
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("7. TEACHER — REUSE TOKEN")
print("=" * 60)
print("  Using teacher token from step 0")


# ═══════════════════════════════════════════════════════════════════
# 5. LIST SESSIONS (GET /teacher/exams/<id>/sessions)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("8. LIST SESSIONS FOR EXAM")
print("=" * 60)

r5 = requests.get(f"{BASE}/teacher/exams/{exam_id}/sessions?page=1&page_size=20",
                  headers=TH, timeout=TIMEOUT)
check("GET sessions list 200", r5.status_code == 200,
      f"got {r5.status_code}: {r5.text[:200]}")

if r5.status_code == 200:
    data5 = r5.json()
    items = data5.get("items", [])
    pag = data5.get("pagination", {})
    check("Has items array", isinstance(items, list))
    check("Has pagination", isinstance(pag, dict))
    print(f"  Total sessions: {pag.get('total_items', len(items))}")

    if items:
        s0 = items[0]
        check("Session has student object", "student" in s0,
              f"keys={list(s0.keys())}")
        check("Session has status", "status" in s0)
        check("Session has score", "score" in s0)
        check("Session has incident_count", "incident_count" in s0)
        check("Session has highest_incident_severity",
              "highest_incident_severity" in s0)
        st = s0.get("student") or {}
        check("Student has name", "name" in st)
        check("Student has roll_number", "roll_number" in st)
        print(f"  First session: #{s0['id']} student={st.get('name')} "
              f"status={s0.get('status')} score={s0.get('score')} "
              f"incidents={s0.get('incident_count')}")

        # Find our target session
        target_session = None
        for item in items:
            if item.get("id") == session_id:
                target_session = item
                break
        if target_session:
            check("Target session found in list", True)
            check("Target session has incidents",
                  target_session.get("incident_count", 0) >= 3,
                  f"got {target_session.get('incident_count')}")
        else:
            check("Target session found in list", False,
                  f"session {session_id} not in items")


# ═══════════════════════════════════════════════════════════════════
# 6. SESSION DETAIL (GET /teacher/sessions/<id>/detail)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("9. SESSION DETAIL")
print("=" * 60)

r6 = requests.get(f"{BASE}/teacher/sessions/{session_id}/detail",
                  headers=TH, timeout=TIMEOUT)
check("GET session detail 200", r6.status_code == 200,
      f"got {r6.status_code}: {r6.text[:200]}")

sa_question_id = None
detail = {}

if r6.status_code == 200:
    detail = r6.json()
    check("Detail has student", "student" in detail)
    check("Detail has exam", "exam" in detail)
    check("Detail has questions", "questions" in detail and
          isinstance(detail["questions"], list))
    check("Detail has incidents", "incidents" in detail and
          isinstance(detail["incidents"], list))
    check("Detail has incident_counts", "incident_counts" in detail)
    check("Detail has score", "score" in detail)
    check("Detail has total_marks", "total_marks" in detail)

    student = detail.get("student", {})
    exam = detail.get("exam", {})
    print(f"  Student: {student.get('name')} ({student.get('roll_number')})")
    print(f"  Exam: {exam.get('title')} ({exam.get('course_code')})")
    print(f"  Score: {detail.get('score')} / {detail.get('total_marks')}")
    print(f"  Incidents: {detail.get('incident_counts', {}).get('total', 0)}")

    # Check questions have expected fields
    questions = detail.get("questions", [])
    if questions:
        q0 = questions[0]
        check("Question has question_text", "question_text" in q0)
        check("Question has question_type", "question_type" in q0)
        check("Question has marks", "marks" in q0)
        check("Question has answer_text", "answer_text" in q0)
        check("Question has marks_awarded", "marks_awarded" in q0)

        for q in questions:
            if q.get("question_type") == "mcq":
                check("MCQ has correct_option",
                      "correct_option" in q,
                      f"keys={list(q.keys())}")
                break

        # Find a short-answer question for grading
        for q in questions:
            if q.get("question_type") == "short_answer":
                sa_question_id = q.get("id")
                print(f"  SA question for grading: #{sa_question_id}")
                break

    # Check incidents
    incidents = detail.get("incidents", [])
    if incidents:
        i0 = incidents[0]
        check("Incident has type", "type" in i0)
        check("Incident has severity", "severity" in i0)
        check("Incident has occurred_at", "occurred_at" in i0)
        check("Incident has description", "description" in i0)

        types_found = {i.get("type") for i in incidents}
        print(f"  Incident types: {types_found}")
        check("FOCUS_LOST in incidents", "FOCUS_LOST" in types_found)


# ═══════════════════════════════════════════════════════════════════
# 7. GRADE SHORT-ANSWER (POST /teacher/sessions/<id>/grade)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("10. GRADE SHORT-ANSWER QUESTION")
print("=" * 60)

if sa_question_id:
    # Find the max marks for this question
    max_marks = 10
    for q in detail.get("questions", []):
        if q.get("id") == sa_question_id:
            max_marks = q.get("marks", 10)
            break

    grade_val = min(7.5, max_marks)  # give 7.5 or max if lower
    r7 = requests.post(
        f"{BASE}/teacher/sessions/{session_id}/grade",
        json={"grades": [{"question_id": sa_question_id,
                          "marks_awarded": grade_val}]},
        headers=TH, timeout=TIMEOUT)
    check("POST grade 200", r7.status_code == 200,
          f"got {r7.status_code}: {r7.text[:200]}")

    if r7.status_code == 200:
        g = r7.json()
        check("Grade response has score", "score" in g)
        check("Grade response has total_marks", "total_marks" in g)
        check("Grade response has graded_count", "graded_count" in g)
        check("graded_count == 1", g.get("graded_count") == 1,
              f"got {g.get('graded_count')}")
        new_score = g.get("score")
        print(f"  New score: {new_score} / {g.get('total_marks')}")
        check("Score updated (> 0)", new_score is not None and new_score > 0,
              f"score={new_score}")

    # Verify score updated in detail
    r7b = requests.get(f"{BASE}/teacher/sessions/{session_id}/detail",
                       headers=TH, timeout=TIMEOUT)
    if r7b.status_code == 200:
        new_detail = r7b.json()
        check("Detail score matches graded",
              new_detail.get("score") == g.get("score") if r7.status_code == 200 else True,
              f"detail={new_detail.get('score')} graded={g.get('score') if r7.status_code == 200 else 'N/A'}")
else:
    print("  No SA question found — skipping grading test")


# ═══════════════════════════════════════════════════════════════════
# 8. ANALYTICS (GET /teacher/exams/<id>/analytics)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("11. EXAM ANALYTICS")
print("=" * 60)

r8 = requests.get(f"{BASE}/teacher/exams/{exam_id}/analytics",
                  headers=TH, timeout=TIMEOUT)
check("GET analytics 200", r8.status_code == 200,
      f"got {r8.status_code}: {r8.text[:200]}")

if r8.status_code == 200:
    a = r8.json()
    check("Analytics has exam_id", "exam_id" in a)
    check("Analytics has sessions_by_status", "sessions_by_status" in a)
    check("Analytics has score_stats", "score_stats" in a)
    check("Analytics has incidents", "incidents" in a)
    check("Analytics has submitted_count", "submitted_count" in a)

    stats = a.get("score_stats", {})
    print(f"  Sessions by status: {a.get('sessions_by_status')}")
    print(f"  Score stats: mean={stats.get('mean')}, "
          f"median={stats.get('median')}, "
          f"min={stats.get('min')}, max={stats.get('max')}")

    inc = a.get("incidents", {})
    print(f"  Total incidents: {inc.get('total')}")
    print(f"  Top types: {inc.get('top_types')}")
    check("Analytics incident total >= 3",
          inc.get("total", 0) >= 3,
          f"got {inc.get('total')}")


# ═══════════════════════════════════════════════════════════════════
# 9. CLIENT CODE IMPORT CHECKS
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("12. CLIENT CODE IMPORT CHECKS")
print("=" * 60)

try:
    from client.app.screens.teacher_sessions_list import TeacherSessionsListScreen
    check("TeacherSessionsListScreen imports", True)
except Exception as e:
    check("TeacherSessionsListScreen imports", False, str(e))

try:
    from client.app.screens.teacher_session_detail import TeacherSessionDetailScreen
    check("TeacherSessionDetailScreen imports", True)
except Exception as e:
    check("TeacherSessionDetailScreen imports", False, str(e))

# Check main.py registers both
try:
    import importlib
    main_src = open("client/app/main.py").read()
    check("main.py has teacher_sessions_list", "teacher_sessions_list" in main_src)
    check("main.py has teacher_session_detail", "teacher_session_detail" in main_src)
except Exception as e:
    check("main.py checks", False, str(e))

# Check teacher_dashboard wiring
try:
    dash_src = open("client/app/screens/teacher_dashboard.py").read()
    check("Dashboard wires to teacher_sessions_list",
          "teacher_sessions_list" in dash_src)
    check("Reports view has Review Sessions button",
          "Review Sessions" in dash_src)
except Exception as e:
    check("Dashboard wiring", False, str(e))


# ═══════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"TOTAL — PASS: {passed}   FAIL: {failed}")
print("=" * 60)
if failed == 0:
    print("\n  All automated checks passed!")
else:
    print(f"\n  {failed} check(s) failed — review above.")
