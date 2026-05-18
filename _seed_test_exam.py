"""Create a fresh test exam via teacher API for Part 17 verification."""
import requests
from datetime import datetime, timedelta, timezone

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
TEACHER_EMAIL = "baha.udeen.a.t1@pucit.edu.pk"
PASSWORD = "pass123"

# Login as teacher
r = requests.post(f"{BASE}/auth/login",
    json={"email": TEACHER_EMAIL, "password": PASSWORD}, timeout=15)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Find teacher's courses
r2 = requests.get(f"{BASE}/courses/me", headers=H, timeout=15)
courses = r2.json().get("items", r2.json() if isinstance(r2.json(), list) else [])
print(f"Teacher courses: {len(courses)}")
for c in courses:
    print(f"  #{c['id']} {c.get('code','')} - {c.get('name', c.get('title',''))}")

if not courses:
    print("No courses found!")
    exit(1)

course_id = courses[0]["id"]
print(f"\nUsing course #{course_id}")

# Create exam
now = datetime.now(timezone.utc)
exam_body = {
    "title": "Part 17 Verification Exam",
    "description": "Auto-created for Part 17 testing",
    "duration_minutes": 60,
    "start_window": (now - timedelta(hours=1)).isoformat(),
    "end_window": (now + timedelta(days=1)).isoformat(),
    "is_active": True,
    "questions": [
        {
            "question_text": "What does HTTP stand for?",
            "question_type": "mcq",
            "marks": 5,
            "order_index": 1,
            "options": [
                "HyperText Transfer Protocol",
                "High Transfer Text Protocol",
                "HyperText Transmission Protocol",
                "Home Tool Transfer Protocol",
            ],
            "correct_answer": "HyperText Transfer Protocol",
        },
        {
            "question_text": "Which HTTP method is idempotent?",
            "question_type": "mcq",
            "marks": 5,
            "order_index": 2,
            "options": ["POST", "PUT", "PATCH", "CONNECT"],
            "correct_answer": "PUT",
        },
        {
            "question_text": "SQL stands for?",
            "question_type": "mcq",
            "marks": 5,
            "order_index": 3,
            "options": [
                "Structured Query Language",
                "Simple Query Language",
                "Standard Query Logic",
                "Server Query Language",
            ],
            "correct_answer": "Structured Query Language",
        },
        {
            "question_text": "Explain the difference between GET and POST.",
            "question_type": "short_answer",
            "marks": 10,
            "order_index": 4,
        },
    ],
}

r3 = requests.post(f"{BASE}/courses/{course_id}/exams", json=exam_body, headers=H, timeout=15)
print(f"\nCreate exam: {r3.status_code}")
if r3.status_code in (200, 201):
    exam = r3.json()
    print(f"  exam_id={exam.get('id')}  title='{exam.get('title')}'")
    print(f"  questions={len(exam.get('questions', []))}")
else:
    print(f"  Error: {r3.text[:300]}")
