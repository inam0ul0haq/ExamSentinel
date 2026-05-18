"""
Teacher Session Detail screen.

Fetches GET /teacher/sessions/<id>/detail and renders three regions:

Top:    Student profile + exam metadata + status + score summary.
Middle: Tabbed view — "Answers" and "Incidents".
        Answers: per-question breakdown with student's answer, correct
                 answer (teacher view), marks awarded.  For short-answer
                 questions an editable marks_awarded + "Save Grade" button
                 that calls POST /teacher/sessions/<id>/grade.
        Incidents: chronological list with timestamp, type, severity
                   (color-coded), description, and optional forensic
                   columns.  Filter bar for type/severity.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from client.app.ui import theme


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_COLORS: Dict[str, str] = {
    "pre_check": theme.TEXT_SECONDARY,
    "in_progress": theme.ACCENT,
    "submitted": theme.SUCCESS,
    "expired": theme.WARNING,
    "aborted_vm": theme.ERROR,
    "aborted_stealth_vm": theme.ERROR,
}

_SEVERITY_COLORS: Dict[str, str] = {
    "info": theme.TEXT_SECONDARY,
    "warning": theme.WARNING,
    "critical": theme.ERROR,
}


def _fmt_dt(iso: Optional[str]) -> str:
    if not iso:
        return "\u2014"
    try:
        return iso[:16].replace("T", " ")
    except Exception:
        return iso


# ===================================================================
# Main screen
# ===================================================================

class TeacherSessionDetailScreen(tk.Frame):
    """Detail view for a single exam session."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 session_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api
        self._root: tk.Tk = router.root
        self._session_id = session_id

        self._data: Dict[str, Any] = {}
        self._active_tab: Optional[str] = None
        self._tab_buttons: Dict[str, tk.Label] = {}

        # Score label kept for live update after grading
        self._score_lbl: Optional[tk.Label] = None

        self._build_back_header()
        self._body = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._body.pack(fill="both", expand=True, padx=24)

        self._show_loading()
        self._fetch()

    # ---- back header ----

    def _build_back_header(self) -> None:
        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", padx=24, pady=(16, 4))
        back = tk.Label(hdr, text="\u2190 Back to Sessions",
                        font=theme.FONT_BODY,
                        bg=theme.BG_PRIMARY, fg=theme.ACCENT, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda _: self._go_back())

    # ---- data loading ----

    def _show_loading(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        tk.Label(self._body, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=40)

    def _fetch(self) -> None:
        sid = self._session_id
        def _work():
            ok, payload, err = self._api.get(
                f"/teacher/sessions/{sid}/detail")
            if ok:
                self._root.after(0, lambda: self._on_ok(payload))
            else:
                msg = err.message if err else "Failed to load session."
                self._root.after(0, lambda: self._on_err(msg))
        threading.Thread(target=_work, daemon=True).start()

    def _on_ok(self, data: dict) -> None:
        self._data = data
        for w in self._body.winfo_children():
            w.destroy()
        self._build_top(data)
        self._build_tabs(data)

    def _on_err(self, msg: str) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        tk.Label(self._body, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=40)

    # ================================================================
    # Top region — student + exam + score
    # ================================================================

    def _build_top(self, data: dict) -> None:
        top = tk.Frame(self._body, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        top.pack(fill="x", pady=(0, 8))
        inner = tk.Frame(top, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=16, pady=12)

        # Student info
        student = data.get("student") or {}
        exam_info = data.get("exam") or {}
        status = data.get("status", "unknown")
        score = data.get("score")
        total = data.get("total_marks")

        left = tk.Frame(inner, bg=theme.BG_SECONDARY)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text=student.get("name", "\u2014"),
                 font=theme.FONT_SUBHEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(anchor="w")

        meta_row = tk.Frame(left, bg=theme.BG_SECONDARY)
        meta_row.pack(anchor="w", pady=(2, 0))
        dash = "\u2014"
        roll = student.get('roll_number') or dash
        email = student.get('email') or dash
        for txt in [
            f"Roll: {roll}",
            f"Email: {email}",
        ]:
            tk.Label(meta_row, text=txt, font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                side="left", padx=(0, 16))

        # Exam info
        tk.Label(left,
                 text=f"{exam_info.get('course_code', '')} — {exam_info.get('title', '')}",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.ACCENT).pack(
            anchor="w", pady=(4, 0))

        meta2 = tk.Frame(left, bg=theme.BG_SECONDARY)
        meta2.pack(anchor="w", pady=(2, 0))
        tk.Label(meta2,
                 text=f"Started: {_fmt_dt(data.get('started_at'))}",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 16))
        tk.Label(meta2,
                 text=f"Ended: {_fmt_dt(data.get('ended_at'))}",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="left")

        # Right: status + score
        right = tk.Frame(inner, bg=theme.BG_SECONDARY)
        right.pack(side="right")

        s_color = _STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
        tk.Label(right, text=status.replace("_", " ").title(),
                 font=("Segoe UI", 11, "bold"),
                 bg=theme.BG_SECONDARY, fg=s_color).pack(anchor="e")

        score_txt = f"{score:.1f}" if score is not None else "\u2014"
        total_txt = str(total) if total else "?"
        self._score_lbl = tk.Label(
            right,
            text=f"Score: {score_txt} / {total_txt}",
            font=("Segoe UI", 16, "bold"),
            bg=theme.BG_SECONDARY, fg=theme.ACCENT,
        )
        self._score_lbl.pack(anchor="e", pady=(4, 0))

        # Incident summary
        ic = data.get("incident_counts", {})
        total_inc = ic.get("total", 0)
        if total_inc > 0:
            tk.Label(right,
                     text=f"{total_inc} incident(s)",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.WARNING).pack(anchor="e")

    # ================================================================
    # Tabs — Answers / Incidents
    # ================================================================

    def _build_tabs(self, data: dict) -> None:
        tab_bar = tk.Frame(self._body, bg=theme.BG_PRIMARY)
        tab_bar.pack(fill="x", pady=(4, 0))

        for name in ("Answers", "Incidents"):
            lbl = tk.Label(tab_bar, text=name, font=theme.FONT_BODY,
                           bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
                           padx=16, pady=6, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _e, n=name: self._select_tab(n))
            self._tab_buttons[name] = lbl

        tk.Frame(self._body, bg=theme.BORDER, height=1).pack(fill="x")
        self._tab_body = tk.Frame(self._body, bg=theme.BG_PRIMARY)
        self._tab_body.pack(fill="both", expand=True, pady=(4, 0))

        self._select_tab("Answers")

    def _select_tab(self, name: str) -> None:
        if name == self._active_tab:
            return
        self._active_tab = name
        for n, btn in self._tab_buttons.items():
            if n == name:
                btn.configure(fg=theme.ACCENT, font=("Segoe UI", 12, "bold"))
            else:
                btn.configure(fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        for w in self._tab_body.winfo_children():
            w.destroy()
        if name == "Answers":
            self._render_answers()
        else:
            self._render_incidents()

    # ================================================================
    # Answers tab
    # ================================================================

    def _render_answers(self) -> None:
        questions = self._data.get("questions", [])

        canvas = tk.Canvas(self._tab_body, bg=theme.BG_PRIMARY,
                           highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(self._tab_body, orient="vertical",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=theme.BG_PRIMARY)
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", tags=("inner",))
        canvas.configure(yscrollcommand=vsb.set)

        def _stretch(_e):
            canvas.itemconfigure("inner", width=canvas.winfo_width())
        canvas.bind("<Configure>", _stretch)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        canvas.bind("<Enter>",
                    lambda _: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>",
                    lambda _: canvas.unbind_all("<MouseWheel>"))

        if not questions:
            tk.Label(inner, text="No questions.", font=theme.FONT_BODY,
                     bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=20)
            return

        for idx, q in enumerate(questions):
            self._answer_card(inner, idx, q)

    def _answer_card(self, parent: tk.Widget, idx: int, q: dict) -> None:
        card = tk.Frame(parent, bg=theme.BG_SECONDARY,
                        highlightbackground=theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=3)
        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=14, pady=10)

        qtype = q.get("question_type", "mcq")
        marks = q.get("marks", 0)
        marks_awarded = q.get("marks_awarded")
        answer = q.get("answer_text") or ""
        prompt = q.get("question_text", "")

        # Header
        hdr = tk.Frame(inner, bg=theme.BG_SECONDARY)
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text=f"Q{idx + 1}. {prompt}",
                 font=("Segoe UI", 11, "bold"),
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 wraplength=600, justify="left", anchor="nw").pack(
            side="left", fill="x", expand=True)

        type_lbl = "MCQ" if qtype == "mcq" else "Short Answer"
        tk.Label(hdr, text=f"[{type_lbl}] {marks} marks",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="right")

        # Student's answer
        if answer:
            tk.Label(inner,
                     text=f"Student's answer: {answer}",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                     wraplength=600, justify="left", anchor="nw").pack(
                fill="x", pady=(6, 0))
        else:
            tk.Label(inner, text="No answer provided",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                fill="x", pady=(6, 0))

        # Correct answer (MCQ only)
        if qtype == "mcq":
            correct = q.get("correct_option", "")
            options = q.get("options", [])
            opt_map = {0: "A", 1: "B", 2: "C", 3: "D"}
            correct_text = ""
            if correct and options:
                letter_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(correct)
                if letter_idx is not None and letter_idx < len(options):
                    correct_text = f"{correct}) {options[letter_idx]}"
                else:
                    correct_text = correct
            tk.Label(inner,
                     text=f"Correct answer: {correct_text}",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.SUCCESS).pack(
                fill="x", pady=(2, 0))

        # Marks awarded
        if qtype == "mcq":
            # Auto-graded — just show
            color = theme.SUCCESS if marks_awarded and marks_awarded > 0 else theme.ERROR
            ma_txt = f"{marks_awarded}" if marks_awarded is not None else "0"
            tk.Label(inner,
                     text=f"Marks awarded: {ma_txt}/{marks} (auto-graded)",
                     font=("Segoe UI", 10, "bold"),
                     bg=theme.BG_SECONDARY, fg=color).pack(
                fill="x", pady=(4, 0))
        else:
            # Short answer — editable
            grade_row = tk.Frame(inner, bg=theme.BG_SECONDARY)
            grade_row.pack(fill="x", pady=(6, 0))

            if marks_awarded is not None:
                tk.Label(grade_row,
                         text=f"Current: {marks_awarded}/{marks}",
                         font=theme.FONT_SMALL,
                         bg=theme.BG_SECONDARY, fg=theme.SUCCESS).pack(
                    side="left", padx=(0, 12))
            else:
                tk.Label(grade_row,
                         text="Not graded yet",
                         font=theme.FONT_SMALL,
                         bg=theme.BG_SECONDARY, fg=theme.WARNING).pack(
                    side="left", padx=(0, 12))

            tk.Label(grade_row, text="Award marks:",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                side="left", padx=(0, 4))

            marks_var = tk.StringVar(
                value=str(marks_awarded) if marks_awarded is not None else "")
            entry = tk.Entry(grade_row, textvariable=marks_var,
                             font=theme.FONT_SMALL,
                             bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
                             insertbackground=theme.TEXT_PRIMARY,
                             relief="flat", bd=0, width=6)
            entry.pack(side="left", ipady=3, padx=(0, 4))

            tk.Label(grade_row, text=f"/ {marks}",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                side="left", padx=(0, 8))

            grade_msg = tk.Label(grade_row, text="", font=theme.FONT_SMALL,
                                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY)
            grade_msg.pack(side="left", padx=(4, 0))

            qid = q.get("id")
            tk.Button(grade_row, text="Save Grade",
                      font=("Segoe UI", 9, "bold"),
                      bg=theme.ACCENT, fg="#FFFFFF",
                      activebackground=theme.ACCENT_HOVER,
                      activeforeground="#FFFFFF",
                      relief="flat", cursor="hand2", bd=0,
                      padx=8, pady=2,
                      command=lambda mv=marks_var, qi=qid, m=marks,
                      gm=grade_msg: self._save_grade(qi, mv, m, gm)).pack(
                side="left")

    def _save_grade(self, qid: int, marks_var: tk.StringVar,
                    max_marks: int, msg_lbl: tk.Label) -> None:
        raw = marks_var.get().strip()
        try:
            val = float(raw)
        except (ValueError, TypeError):
            msg_lbl.configure(text="Enter a valid number.", fg=theme.ERROR)
            return
        if val < 0 or val > max_marks:
            msg_lbl.configure(text=f"Must be 0\u2013{max_marks}.",
                              fg=theme.ERROR)
            return

        msg_lbl.configure(text="Saving\u2026", fg=theme.TEXT_SECONDARY)
        sid = self._session_id

        def _work():
            ok, payload, err = self._api.post(
                f"/teacher/sessions/{sid}/grade",
                body={"grades": [{"question_id": qid,
                                  "marks_awarded": val}]})
            if ok:
                self._root.after(0, lambda: self._on_grade_ok(payload, msg_lbl))
            else:
                msg = err.message if err else "Grade save failed."
                self._root.after(
                    0, lambda: msg_lbl.configure(text=msg, fg=theme.ERROR))
        threading.Thread(target=_work, daemon=True).start()

    def _on_grade_ok(self, payload: dict, msg_lbl: tk.Label) -> None:
        msg_lbl.configure(text="Saved!", fg=theme.SUCCESS)
        # Update score in top region
        new_score = payload.get("score")
        total = payload.get("total_marks")
        if self._score_lbl and new_score is not None:
            self._score_lbl.configure(
                text=f"Score: {new_score:.1f} / {total or '?'}")
        # Update internal data too
        self._data["score"] = new_score

    # ================================================================
    # Incidents tab
    # ================================================================

    def _render_incidents(self) -> None:
        incidents = self._data.get("incidents", [])

        # Filter bar
        filter_bar = tk.Frame(self._tab_body, bg=theme.BG_PRIMARY)
        filter_bar.pack(fill="x", pady=(0, 6))

        tk.Label(filter_bar, text="Filter:", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 6))

        self._inc_type_var = tk.StringVar(value="All Types")
        self._inc_sev_var = tk.StringVar(value="All Severities")

        # Collect unique types and severities
        types = sorted({i.get("type", "") for i in incidents})
        sevs = sorted({i.get("severity", "") for i in incidents})

        type_menu = tk.OptionMenu(
            filter_bar, self._inc_type_var, "All Types", *types,
            command=lambda _: self._apply_incident_filter())
        type_menu.configure(font=theme.FONT_SMALL, bg=theme.BG_INPUT,
                            fg=theme.TEXT_PRIMARY, relief="flat",
                            highlightthickness=0, bd=0)
        type_menu.pack(side="left", padx=(0, 8))

        sev_menu = tk.OptionMenu(
            filter_bar, self._inc_sev_var, "All Severities", *sevs,
            command=lambda _: self._apply_incident_filter())
        sev_menu.configure(font=theme.FONT_SMALL, bg=theme.BG_INPUT,
                           fg=theme.TEXT_PRIMARY, relief="flat",
                           highlightthickness=0, bd=0)
        sev_menu.pack(side="left")

        tk.Label(filter_bar, text=f"{len(incidents)} total",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(
            side="right")

        # List frame
        self._inc_list = tk.Frame(self._tab_body, bg=theme.BG_PRIMARY)
        self._inc_list.pack(fill="both", expand=True)

        self._all_incidents = incidents
        self._render_incident_list(incidents)

    def _apply_incident_filter(self) -> None:
        t = self._inc_type_var.get()
        s = self._inc_sev_var.get()
        filtered = self._all_incidents
        if t != "All Types":
            filtered = [i for i in filtered if i.get("type") == t]
        if s != "All Severities":
            filtered = [i for i in filtered if i.get("severity") == s]
        self._render_incident_list(filtered)

    def _render_incident_list(self, incidents: List[dict]) -> None:
        for w in self._inc_list.winfo_children():
            w.destroy()

        if not incidents:
            tk.Label(self._inc_list, text="No incidents match the filter.",
                     font=theme.FONT_BODY,
                     bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=20)
            return

        canvas = tk.Canvas(self._inc_list, bg=theme.BG_PRIMARY,
                           highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(self._inc_list, orient="vertical",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=theme.BG_PRIMARY)
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", tags=("inner",))
        canvas.configure(yscrollcommand=vsb.set)

        def _stretch(_e):
            canvas.itemconfigure("inner", width=canvas.winfo_width())
        canvas.bind("<Configure>", _stretch)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        canvas.bind("<Enter>",
                    lambda _: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>",
                    lambda _: canvas.unbind_all("<MouseWheel>"))

        for inc in incidents:
            self._incident_row(inner, inc)

    def _incident_row(self, parent: tk.Widget, inc: dict) -> None:
        sev = inc.get("severity", "info")
        sev_color = _SEVERITY_COLORS.get(sev, theme.TEXT_SECONDARY)

        card = tk.Frame(parent, bg=theme.BG_SECONDARY,
                        highlightbackground=sev_color, highlightthickness=1)
        card.pack(fill="x", pady=2)
        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=12, pady=8)

        # Top row: timestamp | type | severity
        top = tk.Frame(inner, bg=theme.BG_SECONDARY)
        top.pack(fill="x")

        tk.Label(top, text=_fmt_dt(inc.get("occurred_at")),
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 12))
        tk.Label(top, text=inc.get("type", ""),
                 font=("Segoe UI", 10, "bold"),
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
            side="left", padx=(0, 12))
        tk.Label(top, text=sev.upper(),
                 font=("Segoe UI", 9, "bold"),
                 bg=theme.BG_SECONDARY, fg=sev_color).pack(side="left")

        # Description
        desc = inc.get("description")
        if desc:
            tk.Label(inner, text=desc, font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                     wraplength=700, justify="left", anchor="nw").pack(
                fill="x", pady=(4, 0))

        # Forensic fields (shown only when present)
        forensics = []
        cpu = inc.get("cpu_thermal_value")
        if cpu is not None:
            forensics.append(f"CPU Thermal: {cpu}")
        latency = inc.get("timing_latency_ms")
        if latency is not None:
            forensics.append(f"Latency: {latency}ms")
        evidence = inc.get("evidence_path")
        if evidence:
            forensics.append(f"Evidence: {evidence}")

        if forensics:
            ff = tk.Frame(inner, bg=theme.BG_SECONDARY)
            ff.pack(fill="x", pady=(4, 0))
            for ft in forensics:
                tk.Label(ff, text=ft, font=("Segoe UI", 9),
                         bg=theme.BG_SECONDARY, fg=theme.ACCENT).pack(
                    side="left", padx=(0, 16))

    # ---- navigation ----

    def _go_back(self) -> None:
        self._router.back()
