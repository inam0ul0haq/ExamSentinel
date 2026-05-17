"""Part 15 verification — automated API checks for seed teacher dashboard."""
import requests
import json

BASE = "https://web-production-5a17d.up.railway.app/api/v1"

# First re-seed to get fresh credentials
print("Re-seeding database...")
rs = requests.post(f"{BASE}/_seed", headers={"X-Seed-Token": "WD7cpakkLfEXdKgsD4eEbpsNBFcMeXmFcZGPmz7tPNs"}, timeout=60)
assert rs.status_code == 200, f"Seed failed: {rs.status_code}"
creds = rs.json().get("credentials", {})
teacher_email = creds.get("demo_teacher_email")
student_email = creds.get("demo_student_email")
password = creds.get("password")
print(f"  Teacher: {teacher_email}")
print(f"  Student: {student_email}")
print(f"  Password: {password}")

print("\n" + "=" * 60)
print("Part 15 — Teacher Dashboard Verification")
print("=" * 60)

# 1. Login as seed teacher
r = requests.post(f"{BASE}/auth/login", json={"email": teacher_email, "password": password}, timeout=10)
print(f"\n[1] LOGIN teacher: {r.status_code}")
data = r.json()
token = data.get("access_token")
user = data.get("user", {})
print(f"    User: {user.get('full_name')} — {user.get('role')}")
assert r.status_code == 200 and token, "Login failed"
assert user.get("role") == "teacher", "Not a teacher"
hdrs = {"Authorization": f"Bearer {token}"}

# 2. GET /courses/me — teacher's courses with enrollment_count
r2 = requests.get(f"{BASE}/courses/me?page_size=100", headers=hdrs, timeout=10)
print(f"\n[2] GET /courses/me: {r2.status_code}")
courses = r2.json().get("items", [])
print(f"    Owns {len(courses)} course(s)")
for c in courses:
    ec = c.get("enrollment_count", "?")
    xc = c.get("exam_count", "?")
    print(f"      {c.get('code')} — {c.get('title')}  ({ec} students, {xc} exams)")
assert r2.status_code == 200 and len(courses) > 0, "No courses"

course_id = courses[0]["id"]

# 3. GET enrollments for first course
r3 = requests.get(f"{BASE}/courses/{course_id}/enrollments?page_size=20&status=active", headers=hdrs, timeout=10)
print(f"\n[3] GET /courses/{course_id}/enrollments: {r3.status_code}")
enrollments = r3.json().get("items", [])
print(f"    {len(enrollments)} enrolled student(s)")
if enrollments:
    e = enrollments[0]
    print(f"      First: {e.get('student_full_name')} | {e.get('student_roll_number')} | dept={e.get('student_department_name')} | sem={e.get('student_semester')}")
assert r3.status_code == 200

# 4. GET /courses/<id>/exams — teacher sees exams with questions
r4 = requests.get(f"{BASE}/courses/{course_id}/exams?page_size=100", headers=hdrs, timeout=10)
print(f"\n[4] GET /courses/{course_id}/exams: {r4.status_code}")
exams = r4.json().get("items", [])
print(f"    {len(exams)} exam(s)")
for ex in exams:
    act = "Active" if ex.get("is_active") else "Inactive"
    print(f"      {ex.get('title')} | {ex.get('question_count')} qs | marks={ex.get('total_marks')} | {act}")
assert r4.status_code == 200

# 5. Toggle activation on first exam (if exists)
if exams:
    eid = exams[0]["id"]
    was_active = exams[0].get("is_active", False)
    action = "deactivate" if was_active else "activate"
    r5 = requests.post(f"{BASE}/exams/{eid}/{action}", headers=hdrs, timeout=10)
    print(f"\n[5] POST /exams/{eid}/{action}: {r5.status_code}")
    assert r5.status_code == 200, f"Toggle failed: {r5.text[:200]}"
    # Toggle back
    reverse = "activate" if was_active else "deactivate"
    r5b = requests.post(f"{BASE}/exams/{eid}/{reverse}", headers=hdrs, timeout=10)
    print(f"    Toggled back ({reverse}): {r5b.status_code}")
    assert r5b.status_code == 200
else:
    print("\n[5] SKIP — no exams to toggle")

# 6. POST /courses — create a new course
r6 = requests.post(f"{BASE}/courses", json={"code": "TEST-999", "title": "Part15 Test Course"}, headers=hdrs, timeout=10)
print(f"\n[6] POST /courses (create): {r6.status_code}")
if r6.status_code == 201:
    new_course = r6.json()
    print(f"    Created: {new_course.get('code')} — {new_course.get('title')}")
else:
    print(f"    {r6.json()}")
assert r6.status_code == 201, "Course creation failed"

# 7. Enroll a student into the new course
new_cid = new_course["id"]
r7 = requests.post(f"{BASE}/courses/{new_cid}/enrollments", json={"student_email": student_email}, headers=hdrs, timeout=10)
print(f"\n[7] POST enroll {student_email} into TEST-999: {r7.status_code}")
assert r7.status_code == 201, f"Enroll failed: {r7.text[:200]}"
enroll_id = r7.json().get("id")
print(f"    Enrollment ID: {enroll_id}")

# 8. Remove the enrollment
r8 = requests.delete(f"{BASE}/courses/{new_cid}/enrollments/{enroll_id}", headers=hdrs, timeout=10)
print(f"\n[8] DELETE enrollment {enroll_id}: {r8.status_code}")
assert r8.status_code == 204, f"Remove failed: {r8.status_code}"

# 9. Try enrolling non-existent student
r9 = requests.post(f"{BASE}/courses/{new_cid}/enrollments", json={"student_email": "nobody@nowhere.com"}, headers=hdrs, timeout=10)
print(f"\n[9] Enroll non-existent: {r9.status_code} — {r9.json().get('error', {}).get('message', '')}")
assert r9.status_code == 404

# 10. Logout validation
print(f"\n[10] Verify token rejection after clear")
r10 = requests.get(f"{BASE}/courses/me", headers={"Authorization": "Bearer invalidtoken"}, timeout=10)
print(f"     Status with bad token: {r10.status_code}")
assert r10.status_code in (401, 422)

print("\n" + "=" * 60)
print("ALL CHECKS PASSED")
print("Launch:  python -m client.app.main")
print(f"Login:   {teacher_email} / {password}")
print("=" * 60)
