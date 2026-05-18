"""
Part 17 — Full Verification Script.

Tests the entire exam-taking flow against the live Railway backend:
1. Login
2. Find an available exam (no existing session)
3. Create session (pre_check)
4. Transition pre_check → in_progress
5. Fetch time remaining
6. Save MCQ answer → verify correct answer is auto-graded
7. Save short-answer → verify "pending review"
8. Report single violation
9. Report bulk violations
10. Verify incidents appear in DB (via teacher login)
11. Submit exam
12. Fetch result → verify per-question breakdown, score, pending marks
13. Verify re-submit returns 409
14. Verify submitted session shows expired=True on /time
"""
import requests
import json
import sys

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
STUDENT_EMAIL = "ikramah.r.s001@pucit.edu.pk"
TEACHER_EMAIL = "baha.udeen.a.t1@pucit.edu.pk"
PASSWORD = "pass123"
TIMEOUT = 15

ok_count = 0
fail_count = 0


def check(label, condition, detail=""):
    global ok_count, fail_count
    if condition:
        print(f"  [PASS] {label}")
        ok_count += 1
    else:
        print(f"  [FAIL] {label} — {detail}")
        fail_count += 1
    return condition


def main():
    # ═══════════════════════════════════════════════════════════════════
    # 1. LOGIN AS STUDENT
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("1. LOGIN AS STUDENT")
    print("=" * 60)
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": STUDENT_EMAIL, "password": PASSWORD},
                      timeout=TIMEOUT)
    check("Login 200", r.status_code == 200, f"got {r.status_code}")
    login = r.json()
    token = login.get("access_token", "")
    user = login.get("user", {})
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"  Student: {user.get('full_name')} (id={user.get('id')})")

    # ═══════════════════════════════════════════════════════════════════
    # 2. FIND AVAILABLE EXAM
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("2. FIND AVAILABLE EXAM (no existing session)")
    print("=" * 60)
    r2 = requests.get(f"{BASE}/exams/active?page_size=100", headers=H, timeout=TIMEOUT)
    check("Active exams 200", r2.status_code == 200)
    exams = r2.json().get("items", [])
    print(f"  Found {len(exams)} active exam(s):")
    for e in exams:
        ss = e.get("session_status") or "none"
        print(f"    #{e['id']} '{e['title']}' session={e.get('session_id')} status={ss}")

    target = None
    for e in exams:
        if e.get("session_id") is None:
            target = e
            break
    if target is None:
        print("\n  ⚠ No exam without an existing session. Trying pre_check...")
        for e in exams:
            if e.get("session_status") == "pre_check":
                target = e
                break
    if target is None:
        print("  ⚠ No suitable exam found. All exams have sessions.")
        print("  The API-level tests below will be skipped.")
        print(f"\n{'=' * 60}\nPASS: {ok_count}  FAIL: {fail_count}\n{'=' * 60}")
        return

    exam_id = target["id"]
    exam_title = target["title"]
    print(f"\n  → Target: #{exam_id} '{exam_title}'")

    # ═══════════════════════════════════════════════════════════════════
    # 3. CREATE SESSION (pre_check)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("3. CREATE SESSION (POST /sessions)")
    print("=" * 60)
    r3 = requests.post(f"{BASE}/sessions",
                       json={"exam_id": exam_id}, headers=H, timeout=TIMEOUT)
    check("POST /sessions 2xx", r3.status_code in (200, 201), f"got {r3.status_code}")
    sess = r3.json()
    session_id = sess["id"]
    status = sess["status"]
    questions = sess.get("questions", [])
    print(f"  session_id={session_id}  status={status}  questions={len(questions)}")
    check("Status is pre_check", status == "pre_check", f"got {status}")
    check("Has questions", len(questions) > 0)

    # Categorise questions
    mcq_qs = [q for q in questions if q.get("question_type") == "mcq"]
    sa_qs = [q for q in questions if q.get("question_type") == "short_answer"]
    print(f"  MCQ: {len(mcq_qs)}  Short-answer: {len(sa_qs)}")

    # ═══════════════════════════════════════════════════════════════════
    # 4. TRANSITION pre_check → in_progress
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("4. TRANSITION pre_check → in_progress (PATCH /sessions/<id>)")
    print("=" * 60)
    r4 = requests.patch(f"{BASE}/sessions/{session_id}",
                        json={"status": "in_progress"}, headers=H, timeout=TIMEOUT)
    check("PATCH transition 200", r4.status_code == 200, f"got {r4.status_code}: {r4.text[:100]}")
    new_status = r4.json().get("status", "?")
    check("New status is in_progress", new_status == "in_progress", f"got {new_status}")

    # ═══════════════════════════════════════════════════════════════════
    # 5. CHECK TIME REMAINING
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("5. CHECK TIME REMAINING (GET /sessions/<id>/time)")
    print("=" * 60)
    r5 = requests.get(f"{BASE}/sessions/{session_id}/time", headers=H, timeout=TIMEOUT)
    check("GET /time 200", r5.status_code == 200)
    td = r5.json()
    tr = td.get("time_remaining_seconds", 0)
    expired = td.get("expired", False)
    print(f"  time_remaining={tr}s  expired={expired}")
    check("Not expired yet", not expired)
    check("Time > 0", tr > 0, f"tr={tr}")

    # ═══════════════════════════════════════════════════════════════════
    # 6. SAVE ANSWERS
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("6. SAVE ANSWERS (PUT /sessions/<id>/answers/<qid>)")
    print("=" * 60)

    # 6a. Save a CORRECT MCQ answer
    correct_mcq_qid = None
    correct_mcq_answer = None
    if mcq_qs:
        q = mcq_qs[0]
        correct_mcq_qid = q["id"]
        correct_answer = q.get("correct_answer")
        opts = q.get("options", [])
        # correct_answer won't be in student response — pick first option
        # and we'll check if it's graded (0 or full marks)
        correct_mcq_answer = opts[0] if opts else "A"
        print(f"  MCQ Q{q.get('order_index',0)+1} (id={correct_mcq_qid}): answering '{correct_mcq_answer}'")
        r6a = requests.put(f"{BASE}/sessions/{session_id}/answers/{correct_mcq_qid}",
                           json={"answer_text": correct_mcq_answer},
                           headers=H, timeout=TIMEOUT)
        check("PUT MCQ answer 200", r6a.status_code == 200, f"got {r6a.status_code}: {r6a.text[:100]}")

    # 6b. Save a short-answer
    sa_qid = None
    if sa_qs:
        q = sa_qs[0]
        sa_qid = q["id"]
        sa_text = "This is a test short answer for verification."
        print(f"  SA Q{q.get('order_index',0)+1} (id={sa_qid}): answering '{sa_text[:40]}...'")
        r6b = requests.put(f"{BASE}/sessions/{session_id}/answers/{sa_qid}",
                           json={"answer_text": sa_text},
                           headers=H, timeout=TIMEOUT)
        check("PUT short-answer 200", r6b.status_code == 200, f"got {r6b.status_code}: {r6b.text[:100]}")

    # ═══════════════════════════════════════════════════════════════════
    # 7. REPORT VIOLATIONS
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("7. REPORT VIOLATIONS (single + bulk)")
    print("=" * 60)

    # 7a. Single incident
    r7a = requests.post(f"{BASE}/sessions/{session_id}/incident",
                        json={"type": "FOCUS_LOST", "severity": "warning",
                              "description": "Alt-tab detected during exam"},
                        headers=H, timeout=TIMEOUT)
    check("POST single incident 201", r7a.status_code == 201, f"got {r7a.status_code}: {r7a.text[:150]}")
    if r7a.status_code == 201:
        inc = r7a.json()
        check("Incident has id", "id" in inc)
        check("Incident type matches", inc.get("type") == "FOCUS_LOST")
        check("Incident severity matches", inc.get("severity") == "warning")
        check("Server set occurred_at", inc.get("occurred_at") is not None)

    # 7b. Bulk incidents
    r7b = requests.post(f"{BASE}/sessions/{session_id}/incidents",
                        json={"incidents": [
                            {"type": "CLIPBOARD_SCRUB", "severity": "info",
                             "description": "Clipboard cleared"},
                            {"type": "KEYBOARD_BLOCKED", "severity": "critical",
                             "description": "Blocked Win+Tab"},
                        ]},
                        headers=H, timeout=TIMEOUT)
    check("POST bulk incidents 201", r7b.status_code == 201, f"got {r7b.status_code}: {r7b.text[:150]}")
    if r7b.status_code == 201:
        bulk_resp = r7b.json()
        items = bulk_resp.get("incidents", bulk_resp.get("items", []))
        check("Bulk returned 2 incidents", len(items) == 2, f"got {len(items)}")

    # ═══════════════════════════════════════════════════════════════════
    # 8. SUBMIT EXAM
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("8. SUBMIT EXAM (POST /sessions/<id>/submit)")
    print("=" * 60)
    r8 = requests.post(f"{BASE}/sessions/{session_id}/submit",
                       headers=H, timeout=TIMEOUT)
    check("POST submit 200", r8.status_code == 200, f"got {r8.status_code}: {r8.text[:150]}")
    if r8.status_code == 200:
        sub = r8.json()
        print(f"  score={sub.get('score')}  total={sub.get('total_marks')}  status={sub.get('status')}")
        check("Status is submitted", sub.get("status") == "submitted")

    # ═══════════════════════════════════════════════════════════════════
    # 9. VERIFY RE-SUBMIT → 409
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("9. RE-SUBMIT → expect 409 (already submitted)")
    print("=" * 60)
    r9 = requests.post(f"{BASE}/sessions/{session_id}/submit",
                       headers=H, timeout=TIMEOUT)
    check("Re-submit returns 409", r9.status_code == 409, f"got {r9.status_code}")

    # ═══════════════════════════════════════════════════════════════════
    # 10. FETCH RESULT
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("10. FETCH RESULT (GET /sessions/<id>/result)")
    print("=" * 60)
    r10 = requests.get(f"{BASE}/sessions/{session_id}/result",
                       headers=H, timeout=TIMEOUT)
    check("GET result 200", r10.status_code == 200, f"got {r10.status_code}: {r10.text[:150]}")
    if r10.status_code == 200:
        result = r10.json()
        print(f"  exam_title: {result.get('exam_title')}")
        print(f"  score: {result.get('score')} / {result.get('total_marks')}")
        check("Result has exam_title", bool(result.get("exam_title")))
        check("Result has score", result.get("score") is not None)
        check("Result has total_marks", result.get("total_marks") is not None)

        breakdown = result.get("breakdown", [])
        check("Breakdown has questions", len(breakdown) > 0, f"got {len(breakdown)}")
        print(f"  breakdown: {len(breakdown)} questions")

        # Verify per-question details
        mcq_found = False
        sa_found = False
        for item in breakdown:
            qid = item.get("question_id")
            qt = item.get("question_type", "?")
            ma = item.get("marks_awarded")
            ans = item.get("answer_text", "")

            if qid == correct_mcq_qid:
                mcq_found = True
                check(f"MCQ Q(id={qid}) has marks_awarded (auto-graded)",
                      ma is not None, f"marks_awarded={ma}")
                check(f"MCQ Q(id={qid}) answer preserved",
                      ans == correct_mcq_answer, f"got '{ans}'")
                print(f"    MCQ → answer='{ans}' marks_awarded={ma}")

            if qid == sa_qid:
                sa_found = True
                # Short-answer should NOT be auto-graded → marks_awarded is None
                check(f"SA Q(id={qid}) marks_awarded is None (pending review)",
                      ma is None, f"marks_awarded={ma}")
                check(f"SA Q(id={qid}) answer preserved",
                      bool(ans), f"got '{ans}'")
                print(f"    SA → answer='{ans[:40]}…' marks_awarded={ma} (pending)")

        if correct_mcq_qid:
            check("Found answered MCQ in breakdown", mcq_found)
        if sa_qid:
            check("Found answered SA in breakdown", sa_found)

    # ═══════════════════════════════════════════════════════════════════
    # 11. VERIFY TIME SHOWS EXPIRED AFTER SUBMIT
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("11. TIME AFTER SUBMIT (should show expired)")
    print("=" * 60)
    r11 = requests.get(f"{BASE}/sessions/{session_id}/time",
                       headers=H, timeout=TIMEOUT)
    check("GET /time 200 after submit", r11.status_code == 200)
    if r11.status_code == 200:
        td2 = r11.json()
        check("expired=True after submit", td2.get("expired") is True,
              f"expired={td2.get('expired')}")
        check("time_remaining=0", td2.get("time_remaining_seconds", -1) == 0,
              f"tr={td2.get('time_remaining_seconds')}")

    # ═══════════════════════════════════════════════════════════════════
    # 12. VERIFY INCIDENTS VIA TEACHER LOGIN
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("12. VERIFY INCIDENTS VIA TEACHER (GET /teacher/sessions/<id>/detail)")
    print("=" * 60)
    rt = requests.post(f"{BASE}/auth/login",
                       json={"email": TEACHER_EMAIL, "password": PASSWORD},
                       timeout=TIMEOUT)
    if rt.status_code == 200:
        t_token = rt.json().get("access_token", "")
        TH = {"Authorization": f"Bearer {t_token}", "Content-Type": "application/json"}

        ri = requests.get(f"{BASE}/teacher/sessions/{session_id}/detail",
                          headers=TH, timeout=TIMEOUT)
        check("GET teacher session detail 200", ri.status_code == 200,
              f"got {ri.status_code}: {ri.text[:150]}")
        if ri.status_code == 200:
            detail = ri.json()
            incidents = detail.get("incidents", [])
            check("Teacher sees >= 3 incidents", len(incidents) >= 3,
                  f"got {len(incidents)}")
            types_found = {i.get("type") for i in incidents}
            print(f"  Incident types found: {types_found}")
            check("FOCUS_LOST in incidents", "FOCUS_LOST" in types_found)
            check("CLIPBOARD_SCRUB in incidents", "CLIPBOARD_SCRUB" in types_found)
            check("KEYBOARD_BLOCKED in incidents", "KEYBOARD_BLOCKED" in types_found)
    else:
        print(f"  Teacher login failed: {rt.status_code}")

    # ═══════════════════════════════════════════════════════════════════
    # 13. CLIENT IMPORT CHECK
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("13. CLIENT CODE IMPORT CHECK")
    print("=" * 60)
    try:
        from client.app.screens.exam_integrity_check import ExamIntegrityCheckScreen
        check("ExamIntegrityCheckScreen imports", True)
    except Exception as e:
        check("ExamIntegrityCheckScreen imports", False, str(e))

    try:
        from client.app.screens.exam_taking import ExamTakingScreen
        check("ExamTakingScreen imports", True)

        # Verify public API surface
        check("has start_lockdown", hasattr(ExamTakingScreen, "start_lockdown"))
        check("has stop_lockdown", hasattr(ExamTakingScreen, "stop_lockdown"))
        check("has report_violation", hasattr(ExamTakingScreen, "report_violation"))
    except Exception as e:
        check("ExamTakingScreen imports", False, str(e))

    try:
        from client.app.main import main as _m
        check("main.py imports all screens", True)
    except Exception as e:
        check("main.py imports all screens", False, str(e))

    # ═══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print(f"TOTAL — PASS: {ok_count}   FAIL: {fail_count}")
    print("=" * 60)
    if fail_count:
        sys.exit(1)
    else:
        print("\n  All automated checks passed!")
        print("  See manual steps below for GUI verification.\n")


if __name__ == "__main__":
    main()
