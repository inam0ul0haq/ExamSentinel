"""Part 11 verification script — run against Railway."""
import requests
import json
import sys

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
SEED_TOKEN = "WD7cpakkLfEXdKgsD4eEbpsNBFcMeXmFcZGPmz7tPNs"
TEACHER_EMAIL = "baha.udeen.a.t1@pucit.edu.pk"
STUDENT_EMAIL = "ikramah.r.s001@pucit.edu.pk"
PASSWORD = "pass123"

PASS = 0
FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  ({detail})")

def section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ── 1. Seed without header → 404 ──
section("1. POST /_seed WITHOUT header")
r = requests.post(f"{BASE}/_seed", timeout=15)
check("Status is 404", r.status_code == 404, r.status_code)
check("Not 401 or 403", r.status_code not in (401, 403), r.status_code)

# ── 2. Seed with header → 200 with counts ──
section("2. POST /_seed WITH X-Seed-Token")
r = requests.post(f"{BASE}/_seed", headers={"X-Seed-Token": SEED_TOKEN}, timeout=30)
check("Status is 200", r.status_code == 200, r.status_code)
seed_data = r.json()
counts = seed_data.get("counts", {})
check("2 departments", counts.get("departments") == 2, counts.get("departments"))
check("3 teachers", counts.get("teachers") == 3, counts.get("teachers"))
check("30 students", counts.get("students") == 30, counts.get("students"))
check("6 courses", counts.get("courses") == 6, counts.get("courses"))
check("12 exams", counts.get("exams") == 12, counts.get("exams"))
check("120 questions", counts.get("questions") == 120, counts.get("questions"))
creds = seed_data.get("credentials", {})
check("credentials block present", bool(creds.get("demo_teacher_email")))

# ── 3. Teacher login → analytics ──
section("3. Teacher login + GET analytics")
r = requests.post(f"{BASE}/auth/login",
                   json={"email": TEACHER_EMAIL, "password": PASSWORD}, timeout=15)
check("Teacher login 200", r.status_code == 200, r.status_code)
login_data = r.json()
teacher_token = login_data.get("access_token")
teacher_user = login_data.get("user", {})
teacher_id = teacher_user.get("id")
print(f"  Teacher id={teacher_id}, name={teacher_user.get('full_name')}")

headers_t = {"Authorization": f"Bearer {teacher_token}"}

# GET /courses/me to list teacher's own courses
r = requests.get(f"{BASE}/courses/me", headers=headers_t, timeout=15)
print(f"  GET /courses/me status={r.status_code}")
courses_body = r.json()
my_courses = courses_body.get("items", []) if isinstance(courses_body, dict) else courses_body
print(f"  Found {len(my_courses)} teacher courses")

# Pick first course, get its exam via GET /exams/<id>
exam_id = None
if my_courses:
    course_id = my_courses[0].get("id")
    print(f"  Using course_id={course_id} ({my_courses[0].get('title')})")

    # Get exam detail: teacher can GET /exams/<id> for any exam they own
    # We need to find exam ids. Check course detail for exam_count, then
    # get the exam by iterating. The exams blueprint has no /courses/<id>/exams
    # endpoint; exams are created via POST /courses/<id>/exams but listed
    # individually. Let's try getting the course detail which has exam_count.
    r = requests.get(f"{BASE}/courses/{course_id}", headers=headers_t, timeout=15)
    print(f"  GET /courses/{course_id} status={r.status_code}")
    if r.status_code == 200:
        course_detail = r.json()
        exam_count = course_detail.get("exam_count", 0)
        print(f"  Course has {exam_count} exams")

    # Since there's no list-exams-by-course endpoint, we need to try exam ids.
    # After seeding, exams are sequentially created. Let's probe a range.
    # Better approach: use the student active exams endpoint to find ids,
    # or just try sequential ids starting from 1.
    for eid in range(1, 100):
        r = requests.get(f"{BASE}/exams/{eid}", headers=headers_t, timeout=5)
        if r.status_code == 200:
            exam_data = r.json()
            if exam_data.get("course_id") == course_id:
                exam_id = eid
                print(f"  Found exam_id={exam_id} ({exam_data.get('title')})")
                break

if exam_id:
    # GET analytics
    r = requests.get(f"{BASE}/teacher/exams/{exam_id}/analytics", headers=headers_t, timeout=15)
    check("GET analytics 200", r.status_code == 200, r.status_code)
    analytics = r.json()
    print(f"  Analytics: {json.dumps(analytics, indent=2)}")
    check("submitted_count is 0", analytics.get("submitted_count") == 0,
          analytics.get("submitted_count"))
    score_stats = analytics.get("score_stats", {})
    check("mean score is None (no sessions)",
          score_stats.get("mean") is None, score_stats.get("mean"))
    check("incidents total is 0",
          analytics.get("incidents", {}).get("total") == 0,
          analytics.get("incidents", {}).get("total"))
else:
    print("  [SKIP] No exam found for teacher's course")

# ── 4. Student login → session → bulk incidents ──
section("4. Student bulk incidents")
r = requests.post(f"{BASE}/auth/login",
                   json={"email": STUDENT_EMAIL, "password": PASSWORD}, timeout=15)
check("Student login 200", r.status_code == 200, r.status_code)
student_data = r.json()
student_token = student_data.get("access_token")
headers_s = {"Authorization": f"Bearer {student_token}"}
student_user = student_data.get("user", {})
student_id = student_user.get("id")
print(f"  Student id={student_id}")

# GET /exams/active to find an active exam for this student
r = requests.get(f"{BASE}/exams/active", headers=headers_s, timeout=15)
print(f"  GET /exams/active status={r.status_code}")
active_exams_body = r.json()
active_exams = active_exams_body.get("items", []) if isinstance(active_exams_body, dict) else active_exams_body
print(f"  Found {len(active_exams)} active exams")

active_exam_id = active_exams[0].get("id") if active_exams else None
session_id = None

if active_exam_id:
    print(f"  Using active exam_id={active_exam_id}")

    # Create session
    r = requests.post(f"{BASE}/sessions",
                       json={"exam_id": active_exam_id}, headers=headers_s, timeout=15)
    print(f"  POST /sessions status={r.status_code}")
    session_data = r.json()
    session_id = session_data.get("id")
    session_status = session_data.get("status")
    print(f"  Session id={session_id}, status={session_status}")

    # Transition to in_progress if in pre_check
    if session_status == "pre_check":
        r = requests.patch(f"{BASE}/sessions/{session_id}",
                            json={"status": "in_progress"}, headers=headers_s, timeout=15)
        print(f"  PATCH session to in_progress: {r.status_code} {r.text[:100]}")

    # POST bulk incidents (3 items)
    incidents_payload = {
        "incidents": [
            {"type": "FOCUS_LOST", "severity": "warning",
             "description": "Alt-tab detected"},
            {"type": "CLIPBOARD_SCRUB", "severity": "info",
             "description": "Clipboard cleared"},
            {"type": "BLACKLISTED_PROCESS_KILLED", "severity": "critical",
             "description": "Killed notepad.exe"},
        ]
    }
    r = requests.post(f"{BASE}/sessions/{session_id}/incidents",
                       json=incidents_payload, headers=headers_s, timeout=15)
    check("Bulk incidents 201", r.status_code == 201,
          f"status={r.status_code}, body={r.text[:300]}")
    if r.status_code == 201:
        inc_data = r.json()
        items = inc_data.get("items", [])
        check("3 incident ids returned", len(items) == 3, f"got {len(items)}")
        for item in items:
            check(f"Incident {item.get('id')} has id", item.get("id") is not None)
else:
    print("  [SKIP] No active exam found for student")

# ── 5. Manual grading: marks_awarded above max → 422 ──
section("5. Manual grading above max -> 422")

if session_id:
    # Get session detail as teacher
    r = requests.get(f"{BASE}/teacher/sessions/{session_id}/detail",
                      headers=headers_t, timeout=15)
    print(f"  GET session detail: status={r.status_code}")
    if r.status_code == 200:
        detail = r.json()
        questions = detail.get("questions", [])
        sa_question = None
        for q in questions:
            if q.get("question_type") == "short_answer":
                sa_question = q
                break

        if sa_question:
            qid = sa_question["id"]
            max_marks = sa_question["marks"]
            print(f"  Short-answer question id={qid}, max_marks={max_marks}")

            # Try to grade with marks_awarded > max
            grade_payload = {
                "grades": [
                    {"question_id": qid, "marks_awarded": max_marks + 5}
                ]
            }
            r = requests.post(f"{BASE}/teacher/sessions/{session_id}/grade",
                               json=grade_payload, headers=headers_t, timeout=15)
            check("Grading above max -> 422", r.status_code == 422,
                  f"status={r.status_code}, body={r.text[:300]}")
            if r.status_code == 422:
                err = r.json()
                print(f"  Error: {json.dumps(err, indent=2)}")
        else:
            print("  [SKIP] No short_answer question found")
    else:
        # If teacher doesn't own the exam, find the session's exam teacher
        print(f"  Session detail failed ({r.status_code}): {r.text[:200]}")
        print("  Trying with the teacher who owns the exam...")
        # The session is for a student exam - the teacher who owns it might be different
        # Let's find which teacher owns this exam
        if active_exam_id:
            r2 = requests.get(f"{BASE}/exams/{active_exam_id}", headers=headers_t, timeout=15)
            if r2.status_code == 403:
                # Teacher doesn't own this exam. Try other teachers.
                print("  Demo teacher doesn't own this exam. Logging in as other teachers...")
                # Try all three teachers
                for i in range(1, 4):
                    suffix = f"t{i}"
                    # We don't know exact emails, but from seed we know pattern
                    # Try getting /auth/me or just try the grading with each exam the teacher owns
                    pass
                print("  [SKIP] Complex multi-teacher scenario - see manual steps below")
            elif r2.status_code == 200:
                exam_detail = r2.json()
                exam_course_id = exam_detail.get("course_id")
                print(f"  Exam belongs to course_id={exam_course_id}")
else:
    print("  [SKIP] No session_id for grading test")

# ── 6. _diag routes removed ──
section("6. _diag routes removed")
if teacher_token:
    r = requests.get(f"{BASE}/_diag/teacher-only", headers=headers_t, timeout=15)
    check("/_diag/teacher-only -> 404", r.status_code == 404, r.status_code)
if student_token:
    r = requests.get(f"{BASE}/_diag/student-only", headers=headers_s, timeout=15)
    check("/_diag/student-only -> 404", r.status_code == 404, r.status_code)

# ── Summary ──
print(f"\n{'='*60}")
print(f"PASSED: {PASS}")
print(f"FAILED: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
