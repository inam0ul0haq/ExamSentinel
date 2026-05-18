"""
Verification script for exam_taking and exam_integrity_check screens.
Tests the full end-to-end flow against the Railway backend.
"""
import requests
import json
import sys

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
STUDENT_EMAIL = "ikramah.r.s001@pucit.edu.pk"
PASSWORD = "pass123"
TIMEOUT = 15

def main():
    ok_count = 0
    fail_count = 0

    def check(label, condition, detail=""):
        nonlocal ok_count, fail_count
        if condition:
            print(f"  [PASS] {label}")
            ok_count += 1
        else:
            print(f"  [FAIL] {label} — {detail}")
            fail_count += 1

    # ── 1. Login ──
    print("\n=== 1. Login as student ===")
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": STUDENT_EMAIL, "password": PASSWORD},
                      timeout=TIMEOUT)
    check("Login status 200", r.status_code == 200, f"got {r.status_code}")
    login_data = r.json()
    token = login_data.get("access_token", "")
    user = login_data.get("user", {})
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    check("Got token", bool(token))
    print(f"  Student: {user.get('full_name')} (id={user.get('id')})")

    # ── 2. List active exams ──
    print("\n=== 2. List active exams ===")
    r2 = requests.get(f"{BASE}/exams/active?page_size=100",
                      headers=headers, timeout=TIMEOUT)
    check("Active exams 200", r2.status_code == 200, f"got {r2.status_code}")
    exams = r2.json().get("items", [])
    print(f"  Found {len(exams)} active exam(s)")
    for e in exams:
        sid = e.get("session_id")
        ss = e.get("session_status")
        print(f"    Exam {e['id']}: '{e['title']}' | session_id={sid} status={ss}")

    if not exams:
        print("  No active exams — cannot test full flow. DONE.")
        return

    # Pick an exam that has no session or is in an appropriate state
    target_exam = None
    for e in exams:
        ss = e.get("session_status")
        if ss is None or ss in ("pre_check", "aborted_vm", "aborted_stealth_vm"):
            target_exam = e
            break
    if target_exam is None:
        # Try one that's in_progress (can resume)
        for e in exams:
            if e.get("session_status") == "in_progress":
                target_exam = e
                break
    if target_exam is None:
        # Try submitted (can view result)
        for e in exams:
            if e.get("session_status") == "submitted":
                target_exam = e
                break

    if target_exam is None:
        print("  No suitable exam found for testing. DONE.")
        return

    exam_id = target_exam["id"]
    existing_status = target_exam.get("session_status")
    existing_sid = target_exam.get("session_id")
    print(f"\n  Target: exam_id={exam_id} '{target_exam['title']}' "
          f"current_status={existing_status} session_id={existing_sid}")

    # ── 3. Create/get session ──
    print("\n=== 3. Create/get session (POST /sessions) ===")
    r3 = requests.post(f"{BASE}/sessions",
                       json={"exam_id": exam_id},
                       headers=headers, timeout=TIMEOUT)
    check("POST /sessions succeeds", r3.status_code in (200, 201),
          f"got {r3.status_code}: {r3.text[:200]}")
    if r3.status_code not in (200, 201):
        print("  Cannot proceed. DONE.")
        return

    sess = r3.json()
    session_id = sess["id"]
    status = sess["status"]
    questions = sess.get("questions", [])
    print(f"  session_id={session_id}, status={status}, questions={len(questions)}")
    check("Session has questions", len(questions) > 0)
    for q in questions[:3]:
        qt = q.get("question_type", "?")
        print(f"    Q{q.get('order_index',0)+1} (id={q['id']}, type={qt}): "
              f"{q.get('question_text','')[:60]}…")

    # ── 4. Transition pre_check → in_progress ──
    if status == "pre_check":
        print("\n=== 4. Transition pre_check → in_progress ===")
        r4 = requests.patch(f"{BASE}/sessions/{session_id}",
                            json={"status": "in_progress"},
                            headers=headers, timeout=TIMEOUT)
        check("PATCH transition 200", r4.status_code == 200,
              f"got {r4.status_code}: {r4.text[:200]}")
        if r4.status_code == 200:
            status = r4.json().get("status", status)
            print(f"  New status: {status}")
    else:
        print(f"\n=== 4. Skip transition (already {status}) ===")

    # ── 5. GET /sessions/<id>/time ──
    if status == "in_progress":
        print("\n=== 5. Check time remaining ===")
        r5 = requests.get(f"{BASE}/sessions/{session_id}/time",
                          headers=headers, timeout=TIMEOUT)
        check("GET /time 200", r5.status_code == 200, f"got {r5.status_code}")
        time_data = r5.json()
        tr = time_data.get("time_remaining_seconds", 0)
        expired = time_data.get("expired", False)
        print(f"  time_remaining={tr}s, expired={expired}")
        check("Time remaining > 0", tr > 0 or expired, f"tr={tr}")

    # ── 6. Save an answer ──
    if status == "in_progress" and questions:
        print("\n=== 6. Save answer (PUT /sessions/<id>/answers/<qid>) ===")
        q = questions[0]
        qid = q["id"]
        qt = q.get("question_type", "mcq")
        if qt == "mcq":
            opts = q.get("options", [])
            answer_text = opts[0] if opts else "A"
        else:
            answer_text = "Test answer from verification script"

        r6 = requests.put(f"{BASE}/sessions/{session_id}/answers/{qid}",
                          json={"answer_text": answer_text},
                          headers=headers, timeout=TIMEOUT)
        check("PUT answer 200", r6.status_code == 200,
              f"got {r6.status_code}: {r6.text[:200]}")
        if r6.status_code == 200:
            print(f"  Saved answer for Q{q.get('order_index',0)+1}: '{answer_text[:40]}'")

    # ── 7. Report a test violation (single incident) ──
    if status == "in_progress":
        print("\n=== 7. Report violation (POST /sessions/<id>/incident) ===")
        r7 = requests.post(f"{BASE}/sessions/{session_id}/incident",
                           json={
                               "type": "FOCUS_LOST",
                               "severity": "info",
                               "description": "Test violation from verify script",
                           },
                           headers=headers, timeout=TIMEOUT)
        check("POST incident 201", r7.status_code == 201,
              f"got {r7.status_code}: {r7.text[:200]}")

    # ── 8. Bulk incidents ──
    if status == "in_progress":
        print("\n=== 8. Bulk incidents (POST /sessions/<id>/incidents) ===")
        r8 = requests.post(f"{BASE}/sessions/{session_id}/incidents",
                           json={"incidents": [
                               {"type": "FOCUS_LOST", "severity": "info",
                                "description": "Bulk test 1"},
                               {"type": "CLIPBOARD_SCRUB", "severity": "warning",
                                "description": "Bulk test 2"},
                           ]},
                           headers=headers, timeout=TIMEOUT)
        check("POST bulk incidents 201", r8.status_code == 201,
              f"got {r8.status_code}: {r8.text[:200]}")

    # ── 9. Submit ──
    if status == "in_progress":
        print("\n=== 9. Submit exam (POST /sessions/<id>/submit) ===")
        r9 = requests.post(f"{BASE}/sessions/{session_id}/submit",
                           headers=headers, timeout=TIMEOUT)
        check("POST submit 200 or 409", r9.status_code in (200, 409),
              f"got {r9.status_code}: {r9.text[:200]}")
        if r9.status_code == 200:
            sub_data = r9.json()
            print(f"  score={sub_data.get('score')}, total={sub_data.get('total_marks')}")

    # ── 10. Get result ──
    print("\n=== 10. Get result (GET /sessions/<id>/result) ===")
    r10 = requests.get(f"{BASE}/sessions/{session_id}/result",
                       headers=headers, timeout=TIMEOUT)
    check("GET result 200", r10.status_code == 200,
          f"got {r10.status_code}: {r10.text[:200]}")
    if r10.status_code == 200:
        result = r10.json()
        print(f"  exam_title: {result.get('exam_title')}")
        print(f"  score: {result.get('score')} / {result.get('total_marks')}")
        breakdown = result.get("breakdown", [])
        print(f"  breakdown: {len(breakdown)} questions")
        for item in breakdown:
            ma = item.get("marks_awarded")
            m = item.get("marks", 0)
            ans = (item.get("answer_text") or "—")[:40]
            status_str = (f"{ma}/{m}" if ma is not None
                          else "pending review" if item.get("question_type") != "mcq"
                          else "—")
            print(f"    Q: {item.get('question_text','')[:50]}… "
                  f"ans='{ans}' → {status_str}")

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"PASS: {ok_count}  FAIL: {fail_count}")
    if fail_count:
        sys.exit(1)

if __name__ == "__main__":
    main()
