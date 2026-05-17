"""Part 14 verification — automated API checks for seed student."""
import requests
import json

BASE = "https://web-production-5a17d.up.railway.app/api/v1"

print("=" * 60)
print("Part 14 — Student Dashboard Verification")
print("=" * 60)

# 1. Login as seed student
r = requests.post(
    f"{BASE}/auth/login",
    json={"email": "ikramah.r.s001@pucit.edu.pk", "password": "pass123"},
    timeout=10,
)
print(f"\n[1] LOGIN: {r.status_code}")
data = r.json()
token = data.get("access_token") or data.get("token")
user = data.get("user", {})
print(f"    Token present: {bool(token)}")
print(f"    User: {user.get('full_name')} — {user.get('role')}")
assert r.status_code == 200 and token, "Login failed"

hdrs = {"Authorization": f"Bearer {token}"}

# 2. Courses
r2 = requests.get(f"{BASE}/courses/me?page_size=100", headers=hdrs, timeout=10)
print(f"\n[2] GET /courses/me: {r2.status_code}")
courses = r2.json().get("items", [])
print(f"    Enrolled in {len(courses)} course(s)")
for c in courses:
    print(f"      {c.get('code')} — {c.get('title')}  (teacher: {c.get('teacher_name', '?')})")
assert r2.status_code == 200 and len(courses) > 0, "No courses returned"

# 3. Active exams
r3 = requests.get(f"{BASE}/exams/active?page_size=100", headers=hdrs, timeout=10)
print(f"\n[3] GET /exams/active: {r3.status_code}")
exams = r3.json().get("items", [])
print(f"    {len(exams)} active exam(s)")
for e in exams:
    ss = e.get("session_status", "n/a (field missing)")
    print(f"      {e.get('title')}  [{e.get('course_code')}]  {e.get('duration_minutes')}min  session_status={ss}")
assert r3.status_code == 200 and len(exams) > 0, "No active exams"

# 4. Start Exam — POST /sessions for the first active exam
exam_id = exams[0]["id"]
print(f"\n[4] POST /sessions (exam_id={exam_id})")
r4 = requests.post(f"{BASE}/sessions", json={"exam_id": exam_id}, headers=hdrs, timeout=10)
print(f"    Status: {r4.status_code}")
sess = r4.json()
session_id = sess.get("id")
print(f"    Session ID: {session_id}")
print(f"    Session status: {sess.get('status')}")
assert r4.status_code == 201 and session_id, "Session creation failed"

# 5. History (sessions/me) — not yet deployed, expect 404 or error
print(f"\n[5] GET /sessions/me (may 404 on current production)")
r5 = requests.get(f"{BASE}/sessions/me?page_size=20", headers=hdrs, timeout=10)
print(f"    Status: {r5.status_code}")
if r5.status_code == 200:
    hist = r5.json()
    print(f"    Items: {len(hist.get('items', []))}")
else:
    print(f"    (Endpoint not yet deployed — History will show error gracefully)")

# 6. Verify logout clears token (client-side only, just confirm API rejects bad token)
print(f"\n[6] Verify token rejection after clear")
r6 = requests.get(f"{BASE}/courses/me", headers={"Authorization": "Bearer invalidtoken"}, timeout=10)
print(f"    Status with bad token: {r6.status_code}")
assert r6.status_code in (401, 422), "Server should reject invalid tokens"

print("\n" + "=" * 60)
print("ALL CHECKS PASSED — launch the app to verify visually:")
print("  python -m client.app.main")
print("  Login: student_01@exam.pk / ExamSentinel2025!")
print("=" * 60)
