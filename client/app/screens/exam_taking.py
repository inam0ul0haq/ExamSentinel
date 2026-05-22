"""
Exam-taking screen.

Full exam UI with:
- Header bar (exam title, student name, countdown timer, save indicator)
- Left question navigator panel (180px, color-coded buttons)
- Right question pane (MCQ radio buttons or short-answer text area)
- Previous / Next / Submit Exam buttons
- Auto-save with debounced PUT
- Submit with confirmation modal
- Auto-submit on timer expiry
- Post-submit result view with per-question breakdown
- Offline incident queue with background flusher
- start_lockdown / stop_lockdown stubs for future lockdown subsystem
- Cleanup via threading.Event on all exit paths
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem
from client.app.lockdown.keyboard import KeyboardLockdown
from client.app.lockdown.manager import LockdownManager
from client.app.lockdown.process_kill import ProcessKillSubsystem
from client.app.lockdown.right_click_suppress import RightClickSuppressSubsystem
from client.app.ui import theme


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NAV_WIDTH = 180
_POLL_INTERVAL_S = 5
_AUTOSAVE_DELAY_MS = 1000
_FLUSH_INTERVAL_S = 10


class ExamTakingScreen(tk.Frame):
    """Full exam-taking screen with timer, navigator, and question pane."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 session_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api            # type: ignore[attr-defined]
        self._session_state = router.session  # type: ignore[attr-defined]
        self._root: tk.Tk = router.root
        self._session_id = int(session_id) if session_id else None

        # Shutdown signal for background threads
        self._shutdown = threading.Event()

        # Exam data (populated by _fetch_session)
        self._exam_title = ""
        self._questions: List[Dict[str, Any]] = []
        self._answers: Dict[int, str] = {}  # question_id -> answer_text
        self._current_q_idx = 0

        # Timer state
        self._time_remaining = 0  # seconds
        self._timer_lock = threading.Lock()

        # Auto-save state
        self._save_timer_id: Optional[str] = None
        self._save_state = "idle"  # idle | saving | saved | failed

        # Submission state
        self._submitted = False

        # Incident offline queue
        self._incident_queue: List[Dict[str, Any]] = []
        self._incident_lock = threading.Lock()

        # Lockdown callback (set by start_lockdown)
        self._on_violation_cb: Optional[Callable] = None

        # Track if we are destroyed
        self._destroyed = False

        # Build loading screen first, fetch data
        self._build_loading()
        threading.Thread(target=self._fetch_session, daemon=True).start()

    # ==================================================================
    # Lockdown (Part 23+)
    # ==================================================================

    def start_lockdown(self, on_violation: Callable) -> None:
        """Instantiate and start the LockdownManager.

        Passes the root Tk window and a bound report_violation method.
        Subsystems registered inside the manager are started in order.
        """
        self._on_violation_cb = on_violation
        self._lockdown_manager = LockdownManager(
            window=self._root,
            report_violation=self.report_violation,
            shutdown_event=self._shutdown,
        )
        # Register lockdown subsystems
        self._lockdown_manager.register(
            KeyboardLockdown(self._lockdown_manager, self._shutdown)
        )
        self._lockdown_manager.register(
            ProcessKillSubsystem(self._lockdown_manager, self._shutdown)
        )
        self._lockdown_manager.register(
            ClipboardScrubSubsystem(self._lockdown_manager, self._shutdown)
        )
        self._right_click_sub = RightClickSuppressSubsystem(
            self._lockdown_manager, self._root
        )
        self._lockdown_manager.register(self._right_click_sub)
        self._lockdown_manager.start()

    def stop_lockdown(self) -> None:
        """Stop the lockdown manager. Idempotent — safe to call multiple times."""
        if hasattr(self, '_lockdown_manager') and self._lockdown_manager is not None:
            self._lockdown_manager.stop()

    # ==================================================================
    # Incident reporting & offline queue
    # ==================================================================

    def report_violation(self, type: str, severity: str,
                         description: str = "", **forensics: Any) -> None:
        """Post an incident to the backend with offline queuing fallback."""
        body: Dict[str, Any] = {
            "type": type,
            "severity": severity,
            "description": description,
        }
        body.update(forensics)

        # Try immediate POST
        ok, _payload, err = self._api.post(
            f"/sessions/{self._session_id}/incident",
            body=body,
        )
        if not ok and err and err.code in ("TRANSPORT", "TIMEOUT"):
            with self._incident_lock:
                self._incident_queue.append(body)

    def _flush_incidents(self) -> bool:
        """Attempt to flush the offline queue via bulk endpoint.
        Returns True if queue is empty after flush."""
        with self._incident_lock:
            if not self._incident_queue:
                return True
            items = list(self._incident_queue)

        ok, _payload, _err = self._api.post(
            f"/sessions/{self._session_id}/incidents",
            body={"incidents": items},
        )
        if ok:
            with self._incident_lock:
                # Remove only the items we flushed
                self._incident_queue = self._incident_queue[len(items):]
            return True
        return False

    def _incident_flusher_loop(self) -> None:
        """Background loop: flush incident queue every 10 seconds."""
        while not self._shutdown.wait(_FLUSH_INTERVAL_S):
            self._flush_incidents()

    # ==================================================================
    # Data loading
    # ==================================================================

    def _build_loading(self) -> None:
        self._loading_label = tk.Label(
            self, text="Loading exam…",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        )
        self._loading_label.place(relx=0.5, rely=0.5, anchor="center")

    def _fetch_session(self) -> None:
        """Fetch session data including questions and time remaining."""
        # 1. Check time / status
        ok_t, time_data, _ = self._api.get(
            f"/sessions/{self._session_id}/time")
        if ok_t and time_data and time_data.get("expired", False):
            self._root.after(0, self._on_already_finished)
            return

        tr = (time_data.get("time_remaining_seconds", 0)
              if ok_t and time_data else 0)

        # 2. Find exam_id via active-exams list
        ok_e, exams_payload, _ = self._api.get(
            "/exams/active?page_size=100")
        if not ok_e:
            self._root.after(0, lambda: self._show_load_error(
                "Failed to load exam data."))
            return

        exam_id = None
        for ex in exams_payload.get("items", []):
            if ex.get("session_id") == self._session_id:
                exam_id = ex.get("id")
                self._exam_title = ex.get("title", "Exam")
                break

        if exam_id is None:
            self._root.after(0, lambda: self._show_load_error(
                "Could not find exam for this session."))
            return

        # 3. POST /sessions to get questions (get_or_create returns existing)
        ok_s, sess_payload, err_s = self._api.post(
            "/sessions", body={"exam_id": exam_id})
        if not ok_s:
            msg = err_s.message if err_s else "Failed to load session."
            self._root.after(0, lambda: self._show_load_error(msg))
            return

        questions = sess_payload.get("questions", [])
        questions.sort(key=lambda q: q.get("order_index", 0))

        self._root.after(0, lambda: self._on_session_loaded(
            questions, tr, sess_payload))

    def _show_load_error(self, msg: str) -> None:
        try:
            self._loading_label.configure(text=msg, fg=theme.ERROR)
        except tk.TclError:
            pass

    def _on_already_finished(self) -> None:
        """Session is already submitted or expired — show results."""
        if self._destroyed:
            return
        try:
            self._loading_label.destroy()
        except tk.TclError:
            pass
        self._show_result_view()

    def _on_session_loaded(self, questions: List[Dict],
                           time_remaining: int,
                           session_data: Dict) -> None:
        if self._destroyed:
            return
        self._questions = questions
        with self._timer_lock:
            self._time_remaining = max(0, time_remaining)

        # Check if already submitted/expired
        status = session_data.get("status", "")
        if status in ("submitted", "expired"):
            self._loading_label.destroy()
            self._show_result_view()
            return

        self._loading_label.destroy()
        self._build_exam_ui()

        # Start background threads
        self.start_lockdown(self._on_violation_cb or (lambda *a, **k: None))
        threading.Thread(target=self._timer_poll_loop, daemon=True).start()
        threading.Thread(target=self._timer_tick_loop, daemon=True).start()
        threading.Thread(target=self._incident_flusher_loop, daemon=True).start()

    # ==================================================================
    # Exam UI layout
    # ==================================================================

    def _build_exam_ui(self) -> None:
        user = self._session_state.user or {}
        student_name = user.get("full_name", "Student")

        # --- Header bar ---
        header = tk.Frame(self, bg=theme.BG_SECONDARY, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text=self._exam_title,
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
        ).pack(side="left", padx=16)

        tk.Label(
            header, text=student_name,
            font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        ).pack(side="left", padx=(8, 0))

        # Timer on the right
        timer_frame = tk.Frame(header, bg=theme.BG_SECONDARY)
        timer_frame.pack(side="right", padx=16)

        self._save_indicator = tk.Label(
            timer_frame, text="",
            font=("Segoe UI", 9),
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        )
        self._save_indicator.pack(side="left", padx=(0, 12))

        self._timer_label = tk.Label(
            timer_frame, text="--:--",
            font=("Segoe UI", 16, "bold"),
            bg=theme.BG_SECONDARY, fg=theme.WARNING,
        )
        self._timer_label.pack(side="left")

        # Update timer display now
        self._update_timer_display()

        # --- Main area ---
        main_area = tk.Frame(self, bg=theme.BG_PRIMARY)
        main_area.pack(fill="both", expand=True)

        # --- Left navigator ---
        nav_frame = tk.Frame(main_area, bg=theme.BG_SECONDARY, width=_NAV_WIDTH)
        nav_frame.pack(side="left", fill="y")
        nav_frame.pack_propagate(False)

        tk.Label(
            nav_frame, text="Questions",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
        ).pack(pady=(12, 8))

        # Scrollable question buttons
        nav_canvas = tk.Canvas(
            nav_frame, bg=theme.BG_SECONDARY,
            highlightthickness=0, bd=0,
        )
        nav_scrollbar = tk.Scrollbar(
            nav_frame, orient="vertical", command=nav_canvas.yview)
        self._nav_inner = tk.Frame(nav_canvas, bg=theme.BG_SECONDARY)

        self._nav_inner.bind(
            "<Configure>",
            lambda e: nav_canvas.configure(scrollregion=nav_canvas.bbox("all")),
        )
        nav_canvas.create_window((0, 0), window=self._nav_inner, anchor="nw")
        nav_canvas.configure(yscrollcommand=nav_scrollbar.set)

        nav_canvas.pack(side="left", fill="both", expand=True, padx=8)
        nav_scrollbar.pack(side="right", fill="y")

        self._nav_buttons: List[tk.Button] = []
        # Layout buttons in a grid (4 per row)
        for i, q in enumerate(self._questions):
            row_frame = None
            if i % 4 == 0:
                row_frame = tk.Frame(self._nav_inner, bg=theme.BG_SECONDARY)
                row_frame.pack(fill="x", pady=2)
            else:
                # Get the last row frame
                children = self._nav_inner.winfo_children()
                row_frame = children[-1] if children else self._nav_inner

            btn = tk.Button(
                row_frame,
                text=str(i + 1),
                font=("Segoe UI", 10, "bold"),
                width=3, height=1,
                relief="flat", bd=0, cursor="hand2",
                command=lambda idx=i: self._jump_to_question(idx),
            )
            btn.pack(side="left", padx=2, pady=2)
            self._nav_buttons.append(btn)

        # --- Right question pane ---
        self._question_pane = tk.Frame(main_area, bg=theme.BG_PRIMARY)
        self._question_pane.pack(side="right", fill="both", expand=True)

        # Question content area (will be rebuilt on navigation)
        self._q_content = tk.Frame(self._question_pane, bg=theme.BG_PRIMARY)
        self._q_content.pack(fill="both", expand=True, padx=20, pady=12)

        # Bottom bar with Previous / Next / Submit
        bottom = tk.Frame(self._question_pane, bg=theme.BG_PRIMARY)
        bottom.pack(fill="x", padx=20, pady=(0, 12))

        self._prev_btn = tk.Button(
            bottom, text="← Previous",
            font=theme.FONT_BUTTON,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            activebackground=theme.BORDER,
            activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            padx=12, pady=6,
            command=self._prev_question,
        )
        self._prev_btn.pack(side="left")

        self._next_btn = tk.Button(
            bottom, text="Next →",
            font=theme.FONT_BUTTON,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            activebackground=theme.BORDER,
            activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            padx=12, pady=6,
            command=self._next_question,
        )
        self._next_btn.pack(side="left", padx=(8, 0))

        self._submit_btn = tk.Button(
            bottom, text="Submit Exam",
            font=theme.FONT_BUTTON,
            bg="#E53E3E", fg="#FFFFFF",
            activebackground="#C53030",
            activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=16, pady=6,
            command=self._on_submit_click,
        )
        self._submit_btn.pack(side="right")

        # Show first question
        self._show_question(0)

    # ==================================================================
    # Question display
    # ==================================================================

    def _show_question(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._questions):
            return

        # Save current answer before navigating
        if hasattr(self, '_q_content'):
            self._save_current_answer_immediate()

        self._current_q_idx = idx

        # Clear content
        for w in self._q_content.winfo_children():
            w.destroy()

        q = self._questions[idx]
        qid = q["id"]
        qtype = q.get("question_type", "mcq")

        # Question number and marks
        header = tk.Frame(self._q_content, bg=theme.BG_PRIMARY)
        header.pack(fill="x", pady=(0, 12))

        tk.Label(
            header,
            text=f"Question {idx + 1} of {len(self._questions)}",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).pack(side="left")

        tk.Label(
            header,
            text=f"[{q.get('marks', 0)} marks]",
            font=theme.FONT_SMALL,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        ).pack(side="right")

        # Question prompt
        prompt_label = tk.Label(
            self._q_content,
            text=q.get("question_text", ""),
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
            wraplength=600, justify="left", anchor="nw",
        )
        prompt_label.pack(fill="x", pady=(0, 16))

        # Answer area
        existing_answer = self._answers.get(qid, "")

        if qtype == "mcq":
            self._answer_var = tk.StringVar(value=existing_answer)
            options = q.get("options", [])
            labels = ["A", "B", "C", "D"]
            for i, opt in enumerate(options):
                label = labels[i] if i < len(labels) else str(i + 1)
                opt_text = f"{label}. {opt}"

                rb = tk.Radiobutton(
                    self._q_content,
                    text=opt_text,
                    variable=self._answer_var,
                    value=opt,
                    font=theme.FONT_BODY,
                    bg=theme.BG_PRIMARY,
                    fg=theme.TEXT_PRIMARY,
                    selectcolor=theme.BG_INPUT,
                    activebackground=theme.BG_PRIMARY,
                    activeforeground=theme.ACCENT,
                    indicatoron=1,
                    anchor="w",
                    padx=8, pady=6,
                    command=self._on_answer_changed,
                )
                rb.pack(fill="x", pady=2)
        else:
            # Short answer
            self._answer_text = tk.Text(
                self._q_content,
                font=theme.FONT_BODY,
                bg=theme.BG_INPUT,
                fg=theme.TEXT_PRIMARY,
                insertbackground=theme.TEXT_PRIMARY,
                relief="flat",
                height=8,
                wrap="word",
                highlightbackground=theme.BORDER,
                highlightcolor=theme.ACCENT,
                highlightthickness=1,
                bd=4,
            )
            self._answer_text.pack(fill="x", pady=(0, 8))
            if existing_answer:
                self._answer_text.insert("1.0", existing_answer)
            self._answer_text.bind("<KeyRelease>", lambda e: self._on_answer_changed())

        # Update nav button colors
        self._update_nav_colors()

        # Update prev/next button states
        self._prev_btn.configure(
            state="normal" if idx > 0 else "disabled")
        self._next_btn.configure(
            state="normal" if idx < len(self._questions) - 1 else "disabled")

    def _jump_to_question(self, idx: int) -> None:
        if idx == self._current_q_idx:
            return
        self._show_question(idx)

    def _prev_question(self) -> None:
        if self._current_q_idx > 0:
            self._show_question(self._current_q_idx - 1)

    def _next_question(self) -> None:
        if self._current_q_idx < len(self._questions) - 1:
            self._show_question(self._current_q_idx + 1)

    def _get_current_answer(self) -> str:
        """Get the current answer text from the active answer widget."""
        q = self._questions[self._current_q_idx]
        qtype = q.get("question_type", "mcq")
        if qtype == "mcq":
            return getattr(self, "_answer_var", tk.StringVar()).get()
        else:
            try:
                return self._answer_text.get("1.0", "end-1c").strip()
            except (tk.TclError, AttributeError):
                return ""

    def _update_nav_colors(self) -> None:
        """Color-code navigator buttons: answered=accent fill,
        current=highlighted, unanswered=outline."""
        for i, btn in enumerate(self._nav_buttons):
            qid = self._questions[i]["id"]
            is_answered = bool(self._answers.get(qid, "").strip())
            is_current = (i == self._current_q_idx)

            if is_current:
                btn.configure(bg=theme.ACCENT, fg="#FFFFFF")
            elif is_answered:
                btn.configure(bg="#2D5A27", fg="#FFFFFF")
            else:
                btn.configure(
                    bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY)

    # ==================================================================
    # Auto-save
    # ==================================================================

    def _on_answer_changed(self) -> None:
        """Schedule a debounced save after 1 second of inactivity."""
        q = self._questions[self._current_q_idx]
        qid = q["id"]
        answer = self._get_current_answer()
        self._answers[qid] = answer
        self._update_nav_colors()

        # Cancel existing timer
        if self._save_timer_id is not None:
            try:
                self.after_cancel(self._save_timer_id)
            except (tk.TclError, ValueError):
                pass

        # Schedule save — capture qid/answer now so navigation won't
        # invalidate them.
        self._save_timer_id = self.after(
            _AUTOSAVE_DELAY_MS,
            lambda: self._do_save(qid, answer))

    def _save_current_answer_immediate(self) -> None:
        """Save the current answer immediately (on question navigation)."""
        if self._submitted or self._destroyed or not self._questions:
            return
        # Cancel any pending debounce timer
        if self._save_timer_id is not None:
            try:
                self.after_cancel(self._save_timer_id)
            except (tk.TclError, ValueError):
                pass
            self._save_timer_id = None

        q = self._questions[self._current_q_idx]
        qid = q["id"]
        answer = self._get_current_answer()
        self._answers[qid] = answer
        if answer.strip():
            self._do_save(qid, answer)

    def _do_save(self, qid: int, answer: str) -> None:
        """Push an answer to the server in the background."""
        self._save_timer_id = None
        if self._submitted or self._destroyed or not answer.strip():
            return
        self._set_save_state("saving")
        threading.Thread(
            target=self._save_answer_bg, args=(qid, answer), daemon=True
        ).start()

    def _save_answer_bg(self, question_id: int, answer_text: str) -> None:
        ok, _payload, _err = self._api.put(
            f"/sessions/{self._session_id}/answers/{question_id}",
            body={"answer_text": answer_text},
        )
        if self._destroyed:
            return
        if ok:
            self._root.after(0, lambda: self._set_save_state("saved"))
        else:
            self._root.after(0, lambda: self._set_save_state("failed"))

    def _set_save_state(self, state: str) -> None:
        self._save_state = state
        try:
            if state == "saving":
                self._save_indicator.configure(
                    text="Saving…", fg=theme.WARNING)
            elif state == "saved":
                self._save_indicator.configure(
                    text="Saved", fg=theme.SUCCESS)
            elif state == "failed":
                self._save_indicator.configure(
                    text="Save failed — will retry", fg=theme.ERROR)
            else:
                self._save_indicator.configure(text="")
        except tk.TclError:
            pass

    # ==================================================================
    # Timer
    # ==================================================================

    def _timer_poll_loop(self) -> None:
        """Poll server for authoritative time every 5 seconds."""
        while not self._shutdown.wait(_POLL_INTERVAL_S):
            if self._submitted:
                break
            ok, payload, _err = self._api.get(
                f"/sessions/{self._session_id}/time")
            if ok and payload:
                server_remaining = payload.get("time_remaining_seconds", 0)
                expired = payload.get("expired", False)
                with self._timer_lock:
                    self._time_remaining = max(0, int(server_remaining))
                if expired:
                    self._root.after(0, self._auto_submit)
                    break

    def _timer_tick_loop(self) -> None:
        """Decrement timer locally every second for smooth display."""
        while not self._shutdown.wait(1.0):
            if self._submitted:
                break
            with self._timer_lock:
                if self._time_remaining > 0:
                    self._time_remaining -= 1
                remaining = self._time_remaining
            self._root.after(0, self._update_timer_display)
            if remaining <= 0:
                self._root.after(0, self._auto_submit)
                break

    def _update_timer_display(self) -> None:
        with self._timer_lock:
            remaining = self._time_remaining
        mins = remaining // 60
        secs = remaining % 60
        text = f"{mins:02d}:{secs:02d}"
        try:
            color = theme.ERROR if remaining < 60 else theme.WARNING
            self._timer_label.configure(text=text, fg=color)
        except tk.TclError:
            pass

    # ==================================================================
    # Submit
    # ==================================================================

    def _on_submit_click(self) -> None:
        """Show confirmation modal before submitting."""
        answered = sum(1 for q in self._questions
                       if self._answers.get(q["id"], "").strip())
        unanswered = len(self._questions) - answered

        # Build modal overlay
        self._modal = tk.Frame(self, bg="")
        self._modal.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Semi-transparent backdrop (simulate with a dark frame)
        backdrop = tk.Frame(self._modal, bg="#000000")
        backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
        backdrop.configure(bg="#0A0E1A")

        # Modal card
        card = tk.Frame(
            self._modal, bg=theme.BG_SECONDARY,
            highlightbackground=theme.BORDER, highlightthickness=1,
        )
        card.place(relx=0.5, rely=0.45, anchor="center",
                   width=420, height=260)

        tk.Label(
            card, text="Submit Exam?",
            font=theme.FONT_HEADING,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
        ).pack(pady=(20, 12))

        tk.Label(
            card, text=f"Answered: {answered}  |  Unanswered: {unanswered}",
            font=theme.FONT_BODY,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        ).pack(pady=(0, 8))

        tk.Label(
            card,
            text="⚠ This action is irreversible. You cannot\n"
                 "return to the exam after submitting.",
            font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.WARNING,
            justify="center",
        ).pack(pady=(0, 16))

        btn_row = tk.Frame(card, bg=theme.BG_SECONDARY)
        btn_row.pack(pady=(0, 12))

        tk.Button(
            btn_row, text="Cancel",
            font=theme.FONT_BUTTON,
            bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
            activebackground=theme.BORDER,
            activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0,
            padx=16, pady=6,
            command=self._close_modal,
        ).pack(side="left", padx=(0, 12))

        tk.Button(
            btn_row, text="Confirm Submit",
            font=theme.FONT_BUTTON,
            bg="#E53E3E", fg="#FFFFFF",
            activebackground="#C53030",
            activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=16, pady=6,
            command=self._do_submit,
        ).pack(side="left")

    def _close_modal(self) -> None:
        if hasattr(self, "_modal"):
            try:
                self._modal.destroy()
            except tk.TclError:
                pass

    def _auto_submit(self) -> None:
        """Auto-submit when timer hits zero."""
        if self._submitted:
            return
        self._submitted = True

        # Disable all inputs
        try:
            self._submit_btn.configure(state="disabled",
                                       text="Time's up — Submitting…")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
        except tk.TclError:
            pass

        # Save current answer first
        self._save_current_answer_immediate()

        threading.Thread(target=self._submit_bg, daemon=True).start()

    def _do_submit(self) -> None:
        """Confirmed submit by user."""
        if self._submitted:
            return
        self._submitted = True
        self._close_modal()

        try:
            self._submit_btn.configure(state="disabled",
                                       text="Submitting…")
        except tk.TclError:
            pass

        # Save current answer first
        self._save_current_answer_immediate()

        threading.Thread(target=self._submit_bg, daemon=True).start()

    def _submit_bg(self) -> None:
        """Background submit: flush incidents, then POST submit."""
        # Flush incidents synchronously before submit
        self._flush_incidents()

        ok, payload, err = self._api.post(
            f"/sessions/{self._session_id}/submit")

        if ok:
            self._root.after(0, self._on_submit_success)
        else:
            # Handle 409 gracefully (already submitted/expired)
            http_status = err.http_status if err else 0
            if http_status == 409:
                self._root.after(0, self._on_submit_success)
            else:
                msg = err.message if err else "Submit failed."
                self._root.after(0, lambda: self._on_submit_failure(msg))

    def _on_submit_success(self) -> None:
        self._cleanup()
        self._show_result_view()

    def _on_submit_failure(self, msg: str) -> None:
        self._submitted = False
        try:
            self._submit_btn.configure(
                state="normal", text="Submit Exam")
        except tk.TclError:
            pass
        # Show error in save indicator area
        try:
            self._save_indicator.configure(text=msg, fg=theme.ERROR)
        except tk.TclError:
            pass

    # ==================================================================
    # Result view
    # ==================================================================

    def _show_result_view(self) -> None:
        """Replace screen contents with result / breakdown."""
        # Clear all children
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

        # Loading
        loading = tk.Label(
            self, text="Loading results…",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        )
        loading.place(relx=0.5, rely=0.5, anchor="center")

        threading.Thread(target=self._fetch_result, daemon=True).start()

    def _fetch_result(self) -> None:
        ok, payload, err = self._api.get(
            f"/sessions/{self._session_id}/result")
        if ok:
            self._root.after(0, lambda: self._render_result(payload))
        else:
            msg = err.message if err else "Failed to load results."
            self._root.after(0, lambda: self._render_result_error(msg))

    def _render_result_error(self, msg: str) -> None:
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

        tk.Label(
            self, text=msg,
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY, fg=theme.ERROR,
        ).place(relx=0.5, rely=0.45, anchor="center")

        tk.Button(
            self, text="Back to Dashboard",
            font=theme.FONT_BUTTON,
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=16, pady=8,
            command=self._go_dashboard,
        ).place(relx=0.5, rely=0.55, anchor="center")

    def _render_result(self, data: Dict) -> None:
        for w in self.winfo_children():
            try:
                w.destroy()
            except tk.TclError:
                pass

        # Scrollable result view
        canvas = tk.Canvas(self, bg=theme.BG_PRIMARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        container = tk.Frame(canvas, bg=theme.BG_PRIMARY)

        container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Result header ---
        header = tk.Frame(container, bg=theme.BG_PRIMARY)
        header.pack(fill="x", padx=30, pady=(20, 0))

        tk.Label(
            header,
            text=data.get("exam_title", "Exam Results"),
            font=("Segoe UI", 22, "bold"),
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Status: {data.get('status', 'submitted').replace('_', ' ').title()}",
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY, fg=theme.SUCCESS,
        ).pack(anchor="w", pady=(4, 0))

        # --- Score summary ---
        score_frame = tk.Frame(container, bg=theme.BG_SECONDARY,
                               highlightbackground=theme.BORDER,
                               highlightthickness=1)
        score_frame.pack(fill="x", padx=30, pady=16)

        score_inner = tk.Frame(score_frame, bg=theme.BG_SECONDARY)
        score_inner.pack(padx=20, pady=16)

        score = data.get("score", 0) or 0
        total = data.get("total_marks", 0) or 0
        pct = (score / total * 100) if total > 0 else 0

        tk.Label(
            score_inner,
            text=f"Score: {score:.1f} / {total}",
            font=("Segoe UI", 18, "bold"),
            bg=theme.BG_SECONDARY, fg=theme.ACCENT,
        ).pack(side="left", padx=(0, 24))

        tk.Label(
            score_inner,
            text=f"{pct:.1f}%",
            font=("Segoe UI", 18, "bold"),
            bg=theme.BG_SECONDARY,
            fg=theme.SUCCESS if pct >= 50 else theme.ERROR,
        ).pack(side="left", padx=(0, 24))

        pending = data.get("pending_manual_marks", 0)
        if pending:
            tk.Label(
                score_inner,
                text=f"Pending review: {pending} marks",
                font=theme.FONT_SMALL,
                bg=theme.BG_SECONDARY, fg=theme.WARNING,
            ).pack(side="left")

        # --- Per-question breakdown ---
        tk.Label(
            container,
            text="Question Breakdown",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).pack(anchor="w", padx=30, pady=(8, 8))

        breakdown = data.get("breakdown", [])
        for i, item in enumerate(breakdown):
            self._render_result_question(container, i, item)

        # --- Back button ---
        tk.Button(
            container,
            text="Back to Dashboard",
            font=theme.FONT_BUTTON,
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=20, pady=8,
            command=self._go_dashboard,
        ).pack(pady=(16, 30))

    def _render_result_question(self, parent: tk.Widget,
                                idx: int, item: Dict) -> None:
        card = tk.Frame(parent, bg=theme.BG_SECONDARY,
                        highlightbackground=theme.BORDER,
                        highlightthickness=1)
        card.pack(fill="x", padx=30, pady=4)
        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=16, pady=10)

        # Header row
        hdr = tk.Frame(inner, bg=theme.BG_SECONDARY)
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text=f"Q{idx + 1}. {item.get('question_text', '')}",
            font=("Segoe UI", 11, "bold"),
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            wraplength=600, justify="left", anchor="nw",
        ).pack(side="left", fill="x", expand=True)

        marks_awarded = item.get("marks_awarded")
        marks = item.get("marks", 0)
        qtype = item.get("question_type", "mcq")

        if marks_awarded is not None:
            color = theme.SUCCESS if marks_awarded > 0 else theme.ERROR
            tk.Label(
                hdr,
                text=f"{marks_awarded}/{marks}",
                font=("Segoe UI", 11, "bold"),
                bg=theme.BG_SECONDARY, fg=color,
            ).pack(side="right")
        elif qtype != "mcq":
            tk.Label(
                hdr,
                text="Pending teacher review",
                font=theme.FONT_SMALL,
                bg=theme.BG_SECONDARY, fg=theme.WARNING,
            ).pack(side="right")
        else:
            tk.Label(
                hdr,
                text=f"—/{marks}",
                font=("Segoe UI", 11),
                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
            ).pack(side="right")

        # Student's answer
        answer = item.get("answer_text", "")
        if answer:
            tk.Label(
                inner,
                text=f"Your answer: {answer}",
                font=theme.FONT_SMALL,
                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                wraplength=600, justify="left", anchor="nw",
            ).pack(fill="x", pady=(6, 0))
        else:
            tk.Label(
                inner,
                text="No answer provided",
                font=theme.FONT_SMALL,
                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
            ).pack(fill="x", pady=(6, 0))

    # ==================================================================
    # Navigation & cleanup
    # ==================================================================

    def _go_dashboard(self) -> None:
        self._cleanup()
        self._router.show("student_dashboard", push=False)

    def _cleanup(self) -> None:
        """Signal all background threads to stop, call stop_lockdown."""
        self._shutdown.set()
        self.stop_lockdown()

    def destroy(self) -> None:
        """Override destroy to ensure cleanup runs."""
        self._destroyed = True
        self._cleanup()
        super().destroy()
