"""Seed the Railway DB with the exact demo data requested."""
import psycopg2
from datetime import datetime, timezone
import hashlib
import os

DB = dict(
    host="shinkansen.proxy.rlwy.net",
    port=58351,
    dbname="railway",
    user="postgres",
    password="JOKekKUODjPqlFriwMHLNNZcpePEkwKj",
    sslmode="require",
)

# Werkzeug-compatible password hash (pbkdf2:sha256)
def _hash_password(pw: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 600000)
    return f"pbkdf2:sha256:600000${salt}${dk.hex()}"

PASS = _hash_password("pass123")
NOW = datetime.now(timezone.utc).isoformat()

conn = psycopg2.connect(**DB)
cur = conn.cursor()

# 1. Department
cur.execute(
    "INSERT INTO departments (name, code, campus_location) "
    "VALUES (%s, %s, %s) RETURNING id",
    ("Information Technology", "IT", "PUCIT, Lahore"),
)
dept_id = cur.fetchone()[0]
print(f"Department IT created (id={dept_id})")

# 2. Teachers
teachers = [
    ("nadeem.akhtar", "nadeem.akhtar@pucit.edu.pk", "Nadeem Akhtar", "PUCIT-T-001"),
    ("waqar.ul.qonain", "waqar.ul.qonain@pucit.edu.pk", "Waqar Ul Qonain", "PUCIT-T-002"),
]
teacher_ids = []
for uname, email, full_name, emp_code in teachers:
    cur.execute(
        "INSERT INTO users (username, email, full_name, role, password_hash, created_at) "
        "VALUES (%s, %s, %s, 'teacher', %s, %s) RETURNING id",
        (uname, email, full_name, PASS, NOW),
    )
    uid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO teachers (id, employee_code, designation, department_id) "
        "VALUES (%s, %s, %s, %s)",
        (uid, emp_code, "Assistant Professor", dept_id),
    )
    teacher_ids.append(uid)
    print(f"Teacher: {full_name} (id={uid}, email={email})")

# 3. Courses
courses = [
    ("SQA-401", "Software Quality Assurance", "Testing, QA processes, automation.", teacher_ids[0]),
    ("DSA-301", "Data Structures and Algorithms", "Arrays, trees, graphs, sorting.", teacher_ids[1]),
]
course_ids = []
for code, title, desc, tid in courses:
    cur.execute(
        "INSERT INTO courses (code, title, description, teacher_id, created_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (code, title, desc, tid, NOW),
    )
    cid = cur.fetchone()[0]
    course_ids.append(cid)
    print(f"Course: {code} - {title} (id={cid})")

# 4. Students
students = [
    ("inam.ul.haq", "inam.ul.haq@pucit.edu.pk", "Inam Ul Haq", "BITF22M017"),
    ("ahmad.ali", "ahmad.ali@pucit.edu.pk", "Ahmad Ali", "BITF22M038"),
    ("nouman.ashraf", "nouman.ashraf@pucit.edu.pk", "Nouman Ashraf", "BITF22M041"),
]
student_ids = []
for uname, email, full_name, roll in students:
    cur.execute(
        "INSERT INTO users (username, email, full_name, role, password_hash, created_at) "
        "VALUES (%s, %s, %s, 'student', %s, %s) RETURNING id",
        (uname, email, full_name, PASS, NOW),
    )
    uid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO students (id, roll_number, department_id, semester, is_eligible) "
        "VALUES (%s, %s, %s, %s, %s)",
        (uid, roll, dept_id, 7, True),
    )
    student_ids.append(uid)
    print(f"Student: {full_name} ({roll}, id={uid})")

# 5. Enrollments — all 3 students in both courses
for sid in student_ids:
    for cid in course_ids:
        cur.execute(
            "INSERT INTO enrollments (student_id, course_id, status, enrolled_at) "
            "VALUES (%s, %s, 'active', %s)",
            (sid, cid, NOW),
        )
print(f"Enrolled all 3 students in both courses")

# 6. Exams — one per course, INACTIVE (teacher activates via GUI)
exams = [
    (course_ids[0], "SQA Midterm", "Midterm covering testing fundamentals", 30),
    (course_ids[1], "DSA Midterm", "Midterm covering arrays, linked lists, trees", 30),
]
exam_ids = []
for cid, title, desc, dur in exams:
    cur.execute(
        "INSERT INTO exams (course_id, title, description, duration_minutes, "
        "total_marks, is_active, created_at) "
        "VALUES (%s, %s, %s, %s, 0, false, %s) RETURNING id",
        (cid, title, desc, dur, NOW),
    )
    eid = cur.fetchone()[0]
    exam_ids.append(eid)
    print(f"Exam: {title} (id={eid}, is_active=FALSE, duration={dur}min)")

# 7. Questions — 5 MCQs per exam
sqa_mcqs = [
    ("What does SQA stand for?", ["Software Quality Assurance", "System Query Analysis", "Standard Quality Assessment", "Software Queue Architecture"], "A", 5),
    ("Which is NOT a testing level?", ["Unit", "Integration", "Compilation", "System"], "C", 5),
    ("Black-box testing focuses on?", ["Internal code structure", "Input-output behavior", "Memory management", "CPU usage"], "B", 5),
    ("What is regression testing?", ["Testing new features only", "Re-testing after changes to catch regressions", "Load testing under stress", "Testing UI layout"], "B", 5),
    ("V-Model maps each dev phase to a?", ["Document", "Testing phase", "Release", "Sprint"], "B", 5),
]

dsa_mcqs = [
    ("Time complexity of binary search?", ["O(n)", "O(log n)", "O(n²)", "O(1)"], "B", 5),
    ("Which data structure uses LIFO?", ["Queue", "Stack", "Array", "Graph"], "B", 5),
    ("Worst-case of quicksort?", ["O(n log n)", "O(n)", "O(n²)", "O(log n)"], "C", 5),
    ("A balanced BST has height?", ["O(n)", "O(log n)", "O(n²)", "O(1)"], "B", 5),
    ("BFS uses which data structure?", ["Stack", "Queue", "Heap", "Array"], "B", 5),
]

letter_map = {"A": "option_a_val", "B": "option_b_val", "C": "option_c_val", "D": "option_d_val"}
correct_letters = {"A": "A", "B": "B", "C": "C", "D": "D"}

total_per_exam = 0
for exam_id, mcqs in [(exam_ids[0], sqa_mcqs), (exam_ids[1], dsa_mcqs)]:
    total_marks = 0
    for order, (prompt, opts, correct, marks) in enumerate(mcqs, 1):
        cur.execute(
            "INSERT INTO questions (exam_id, prompt, question_type, marks, "
            "option_a, option_b, option_c, option_d, correct_option, order_index) "
            "VALUES (%s, %s, 'mcq', %s, %s, %s, %s, %s, %s, %s)",
            (exam_id, prompt, marks, opts[0], opts[1], opts[2], opts[3], correct, order),
        )
        total_marks += marks
    # Update total_marks on exam
    cur.execute("UPDATE exams SET total_marks = %s WHERE id = %s", (total_marks, exam_id))
    print(f"  Exam {exam_id}: {len(mcqs)} MCQs, total_marks={total_marks}")

conn.commit()
conn.close()

print("\n" + "=" * 60)
print("SEED COMPLETE!")
print("=" * 60)
print(f"\nAll passwords: pass123")
print(f"\nTeachers:")
print(f"  nadeem.akhtar@pucit.edu.pk  (SQA-401)")
print(f"  waqar.ul.qonain@pucit.edu.pk  (DSA-301)")
print(f"\nStudents (enrolled in BOTH courses):")
print(f"  inam.ul.haq@pucit.edu.pk  (BITF22M017)")
print(f"  ahmad.ali@pucit.edu.pk  (BITF22M038)")
print(f"  nouman.ashraf@pucit.edu.pk  (BITF22M041)")
print(f"\nExams: INACTIVE — teacher must activate from GUI")
print(f"  SQA Midterm (5 MCQs, 25 marks, 30 min)")
print(f"  DSA Midterm (5 MCQs, 25 marks, 30 min)")
print(f"\nWorkflow: Teacher login → My Courses → course → Exams → Activate")
print(f"          Student login → Active Exams → exam appears immediately")
