"""Dummy data generator for demos and integration testing.

Shape (per Part 12 of the build plan):

* 2 departments (CS + IT, both at "PUCIT, Lahore")
* 3 teachers with Pakistani names and unique employee codes
* 6 courses (2 per teacher), distributed across 3 teachers
* 30 students with PUCIT-style roll numbers (BSIT-F22-001..030)
* Each student enrolled in 2-4 random courses (not the same ones)
* 2 exams per course (12 total), each with 10 questions (7 mcq + 3
  short_answer)
* ``is_active`` alternates true/false so demos always have both kinds

All passwords are the literal string ``pass123``. The shared password is
returned in the API response so the human can log in immediately.

Names are produced by Faker with ``en_PK`` locale; course and exam
titles are hand-picked Pakistani-context strings so demos always look
the same.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from faker import Faker

from app.extensions import db
from app.models import (
    Answer,
    Course,
    Department,
    Enrollment,
    Exam,
    ExamSession,
    IncidentLog,
    Question,
    Student,
    Teacher,
    User,
)
from app.models.enums import (
    CORRECT_OPTION_A,
    CORRECT_OPTION_B,
    CORRECT_OPTION_C,
    CORRECT_OPTION_D,
    ENROLLMENT_STATUS_ACTIVE,
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_SHORT_ANSWER,
)


SHARED_PASSWORD = "pass123"

# Stable, demoable Pakistani-context content -------------------------------

DEPARTMENTS = [
    {
        "name": "Computer Science",
        "code": "CS",
        "campus_location": "PUCIT, Lahore",
    },
    {
        "name": "Information Technology",
        "code": "IT",
        "campus_location": "PUCIT, Lahore",
    },
]

# Six courses split 2 per teacher. ``dept_code`` is the department the
# course belongs to via its owning teacher; we use it only to drive
# course-code prefixes like ``CS-301``.
COURSES: List[Dict[str, Any]] = [
    {"code": "CS-301", "title": "Database Systems",
     "description": "Relational model, SQL, normalisation, indexing."},
    {"code": "CS-302", "title": "Operating Systems",
     "description": "Processes, scheduling, memory, file systems."},
    {"code": "CS-401", "title": "Software Engineering",
     "description": "Requirements, design, agile, testing."},
    {"code": "CS-402", "title": "Computer Networks",
     "description": "TCP/IP, routing, sockets, security."},
    {"code": "IT-301", "title": "Web Engineering",
     "description": "HTTP, REST, modern web stacks."},
    {"code": "IT-402", "title": "Information Security",
     "description": "Cryptography, threats, secure coding."},
]

# Two exam titles per course, in order; iterated by index.
EXAM_TITLES: Dict[str, List[str]] = {
    "CS-301": ["Midterm: SQL & Normalisation", "Final: Indexing & Transactions"],
    "CS-302": ["Midterm: Processes & Scheduling", "Final: Memory & File Systems"],
    "CS-401": ["Midterm: Requirements & Design", "Final: Testing & Deployment"],
    "CS-402": ["Midterm: TCP/IP Fundamentals", "Final: Routing & Security"],
    "IT-301": ["Midterm: HTTP & REST APIs", "Final: Modern Frontend Stacks"],
    "IT-402": ["Midterm: Symmetric Cryptography", "Final: Threat Modeling"],
}

# MCQ pool — each entry: (prompt, options A..D, correct letter).
_MCQ_POOL: List[Dict[str, Any]] = [
    {
        "prompt": "Which SQL clause filters rows after grouping?",
        "options": ["WHERE", "HAVING", "ORDER BY", "GROUP BY"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "Default port for HTTPS?",
        "options": ["80", "21", "443", "22"],
        "correct": CORRECT_OPTION_C,
    },
    {
        "prompt": "Which OSI layer does TCP operate at?",
        "options": ["Network", "Transport", "Session", "Application"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "B-tree index is typically used for…",
        "options": ["Range queries", "Bitmap ops", "Bloom filters", "Hashing"],
        "correct": CORRECT_OPTION_A,
    },
    {
        "prompt": "First normal form (1NF) forbids…",
        "options": ["Foreign keys", "Repeating groups", "Null values", "Joins"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "Which sorting algorithm runs in O(n log n) worst case?",
        "options": ["Quicksort", "Bubble sort", "Mergesort", "Insertion sort"],
        "correct": CORRECT_OPTION_C,
    },
    {
        "prompt": "HTTP status 201 means…",
        "options": ["Accepted", "Created", "No Content", "Moved"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "AES is a…",
        "options": ["Hash function", "Symmetric cipher",
                    "Asymmetric cipher", "Stream codec"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "What does CAP theorem stand for?",
        "options": [
            "Consistency, Availability, Partition tolerance",
            "Cache, API, Performance",
            "Cluster, Atomicity, Persistence",
            "Concurrency, Atomicity, Permissions",
        ],
        "correct": CORRECT_OPTION_A,
    },
    {
        "prompt": "TCP three-way handshake order?",
        "options": ["SYN, ACK, FIN", "SYN, SYN-ACK, ACK",
                    "ACK, SYN, FIN", "FIN, ACK, SYN"],
        "correct": CORRECT_OPTION_B,
    },
    {
        "prompt": "Which is NOT a process state?",
        "options": ["Running", "Waiting", "Compiled", "Ready"],
        "correct": CORRECT_OPTION_C,
    },
    {
        "prompt": "Page replacement algorithm with optimal theoretical perf?",
        "options": ["FIFO", "LRU", "Belady's OPT", "Clock"],
        "correct": CORRECT_OPTION_C,
    },
    {
        "prompt": "REST stands for…",
        "options": [
            "Representational State Transfer",
            "Remote Endpoint Service Token",
            "Reactive Event Stream Transport",
            "Resource Encoding STandard",
        ],
        "correct": CORRECT_OPTION_A,
    },
    {
        "prompt": "JWT signature algorithm HS256 uses…",
        "options": ["RSA", "ECDSA", "HMAC-SHA256", "MD5"],
        "correct": CORRECT_OPTION_C,
    },
]

_SHORT_POOL: List[str] = [
    "Explain the difference between primary key and unique constraint.",
    "Describe the producer-consumer problem and one common solution.",
    "Compare symmetric and asymmetric cryptography with one example each.",
    "Define eventual consistency and give a real-world example.",
    "List three differences between TCP and UDP.",
    "What is denormalisation and when is it justified?",
    "Outline the steps of a TLS handshake at a high level.",
    "Explain dependency injection in your own words.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user_fields(faker: Faker, full_name: str, suffix: str,
                      role: str) -> Dict[str, Any]:
    """Build username/email from a name. ``suffix`` ensures uniqueness."""
    base = (
        "".join(ch for ch in full_name.lower() if ch.isalnum() or ch == " ")
        .strip().replace(" ", ".")
    )
    if not base:
        base = role
    username = f"{base}.{suffix}"[:32]
    email = f"{base}.{suffix}@pucit.edu.pk"[:254]
    return {"username": username, "email": email, "full_name": full_name}


def _wipe_database() -> None:
    """Delete rows in FK dependency order (children first)."""
    db.session.query(Answer).delete(synchronize_session=False)
    db.session.query(IncidentLog).delete(synchronize_session=False)
    db.session.query(ExamSession).delete(synchronize_session=False)
    db.session.query(Question).delete(synchronize_session=False)
    db.session.query(Exam).delete(synchronize_session=False)
    db.session.query(Enrollment).delete(synchronize_session=False)
    db.session.query(Course).delete(synchronize_session=False)
    db.session.query(Student).delete(synchronize_session=False)
    db.session.query(Teacher).delete(synchronize_session=False)
    # Now base User rows can be removed.
    db.session.query(User).delete(synchronize_session=False)
    db.session.query(Department).delete(synchronize_session=False)
    db.session.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def regenerate_demo_data(rng_seed: int = 20250517) -> Dict[str, Any]:
    """Wipe and regenerate the demo dataset. Returns a summary block."""
    random.seed(rng_seed)
    faker = Faker("en_PK")
    Faker.seed(rng_seed)

    _wipe_database()

    # --- Departments --------------------------------------------------
    departments: List[Department] = []
    for spec in DEPARTMENTS:
        dept = Department(
            name=spec["name"],
            code=spec["code"],
            campus_location=spec["campus_location"],
        )
        db.session.add(dept)
        departments.append(dept)
    db.session.flush()

    cs_dept = next(d for d in departments if d.code == "CS")
    it_dept = next(d for d in departments if d.code == "IT")

    # --- Teachers -----------------------------------------------------
    teachers: List[Teacher] = []
    teacher_emp_codes = ["PUCIT-T-001", "PUCIT-T-002", "PUCIT-T-003"]
    # Two CS teachers, one IT teacher.
    teacher_dept_ids = [cs_dept.id, cs_dept.id, it_dept.id]
    for i, emp in enumerate(teacher_emp_codes):
        full_name = faker.name()
        fields = _make_user_fields(faker, full_name, f"t{i+1}", "teacher")
        teacher = Teacher(
            username=fields["username"],
            email=fields["email"],
            full_name=full_name,
            role="teacher",
            employee_code=emp,
            designation="Assistant Professor",
            department_id=teacher_dept_ids[i],
        )
        teacher.set_password(SHARED_PASSWORD)
        db.session.add(teacher)
        teachers.append(teacher)
    db.session.flush()

    # --- Courses (2 per teacher) -------------------------------------
    courses: List[Course] = []
    for idx, spec in enumerate(COURSES):
        teacher = teachers[idx // 2]
        course = Course(
            code=spec["code"],
            title=spec["title"],
            description=spec["description"],
            teacher_id=teacher.id,
        )
        db.session.add(course)
        courses.append(course)
    db.session.flush()

    # --- Students -----------------------------------------------------
    students: List[Student] = []
    for i in range(1, 31):
        roll = f"BSIT-F22-{i:03d}"
        full_name = faker.name()
        fields = _make_user_fields(faker, full_name, f"s{i:03d}", "student")
        dept_id = cs_dept.id if i % 2 == 0 else it_dept.id
        student = Student(
            username=fields["username"],
            email=fields["email"],
            full_name=full_name,
            role="student",
            roll_number=roll,
            department_id=dept_id,
            semester=random.randint(3, 7),
            is_eligible=True,
        )
        student.set_password(SHARED_PASSWORD)
        db.session.add(student)
        students.append(student)
    db.session.flush()

    # --- Enrollments (each student in 2..4 random courses) -----------
    for student in students:
        num = random.randint(2, 4)
        picks = random.sample(courses, num)
        for course in picks:
            db.session.add(Enrollment(
                student_id=student.id,
                course_id=course.id,
                status=ENROLLMENT_STATUS_ACTIVE,
            ))
    db.session.flush()

    # --- Exams + Questions -------------------------------------------
    now = datetime.now(timezone.utc)
    exam_index = 0  # global toggle for is_active
    for course in courses:
        titles = EXAM_TITLES[course.code]
        for slot, title in enumerate(titles):
            is_active = (exam_index % 2 == 0)
            exam = Exam(
                course_id=course.id,
                title=title,
                description=f"{course.title} — {title}",
                duration_minutes=60,
                start_window=now - timedelta(days=1),
                end_window=now + timedelta(days=30),
                is_active=is_active,
                total_marks=0,
            )
            db.session.add(exam)
            db.session.flush()

            # Build 10 questions: 7 mcq + 3 short_answer.
            total_marks = 0
            mcq_picks = random.sample(_MCQ_POOL, 7)
            short_picks = random.sample(_SHORT_POOL, 3)
            order = 1
            for m in mcq_picks:
                marks = 5
                total_marks += marks
                q = Question(
                    exam_id=exam.id,
                    prompt=m["prompt"],
                    question_type=QUESTION_TYPE_MCQ,
                    marks=marks,
                    option_a=m["options"][0],
                    option_b=m["options"][1],
                    option_c=m["options"][2],
                    option_d=m["options"][3],
                    correct_option=m["correct"],
                    order_index=order,
                )
                db.session.add(q)
                order += 1
            for prompt in short_picks:
                marks = 10
                total_marks += marks
                q = Question(
                    exam_id=exam.id,
                    prompt=prompt,
                    question_type=QUESTION_TYPE_SHORT_ANSWER,
                    marks=marks,
                    order_index=order,
                )
                db.session.add(q)
                order += 1

            exam.total_marks = total_marks
            exam_index += 1

    db.session.commit()

    # --- Summary block ------------------------------------------------
    demo_teacher = teachers[0]
    demo_student = students[0]
    return {
        "ok": True,
        "counts": {
            "departments": len(departments),
            "teachers": len(teachers),
            "courses": len(courses),
            "students": len(students),
            "exams": exam_index,
            "questions": exam_index * 10,
        },
        "credentials": {
            "password": SHARED_PASSWORD,
            "demo_teacher_email": demo_teacher.email,
            "demo_student_email": demo_student.email,
        },
        "notes": [
            "Every account uses the same password: 'pass123'.",
            "Exams alternate is_active so demos have both states.",
            "Roll numbers follow BSIT-F22-001..030.",
        ],
    }


__all__ = ["regenerate_demo_data", "SHARED_PASSWORD"]
