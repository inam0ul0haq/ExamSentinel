"""
Exam editor screen — create or edit an exam with mixed question types.

Reused for both creating a new exam (course_id only) and editing an
existing one (course_id + exam_id).  Pure Tkinter, Windows-compatible.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from client.app.ui import theme
from client.app.ui.widgets import Toast


# ── option letters ────────────────────────────────────────────────────
_LETTERS = ("A", "B", "C", "D")


# ── scrollable frame helper ──────────────────────────────────────────
def _make_scrollable(parent: tk.Widget):
    """Return ``(canvas, scrollable_frame)`` packed inside *parent*."""
    canvas = tk.Canvas(parent, bg=theme.BG_PRIMARY, highlightthickness=0, bd=0)
    vsb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=theme.BG_PRIMARY)

    inner.bind(
        "<Configure>",
        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=inner, anchor="nw", tags=("inner",))
    canvas.configure(yscrollcommand=vsb.set)

    def _stretch(_e):
        canvas.itemconfigure("inner", width=canvas.winfo_width())
    canvas.bind("<Configure>", _stretch)

    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def _on_mousewheel(event):
        try:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    def _bind_wheel(_e):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(_e):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)

    return canvas, inner


# =====================================================================
# Tooltip helper (pure Tkinter)
# =====================================================================

class _ToolTip:
    """Show a tooltip on hover for a widget."""

    def __init__(self, widget: tk.Widget, text: str = "") -> None:
        self._widget = widget
        self.text = text
        self._tw: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event: tk.Event) -> None:
        if not self.text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tw = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            tw, text=self.text, justify="left",
            bg="#333340", fg="#FFFFFF",
            font=theme.FONT_SMALL,
            relief="solid", borderwidth=1,
            padx=6, pady=3,
        )
        lbl.pack()

    def _hide(self, _event: tk.Event) -> None:
        if self._tw:
            self._tw.destroy()
            self._tw = None


# =====================================================================
# Main screen
# =====================================================================

class ExamCreationScreen(tk.Frame):
    """Full exam creation / editing screen."""

    def __init__(
        self,
        parent: tk.Widget,
        router: Any,
        *,
        course_id: Any = None,
        exam_id: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api  # type: ignore[attr-defined]
        self._root = router.root
        self._course_id = int(course_id) if course_id else None
        self._exam_id = int(exam_id) if exam_id else None
        self._is_edit = self._exam_id is not None
        self._locked = False  # exam has sessions → read-only
        self._toast = Toast(self)

        # Course info (fetched async)
        self._course_code = ""
        self._course_title = ""

        # Question data  — each item is a dict:
        # {type, prompt_var, marks_var, options:[StringVar]*4, correct_var,
        #  prompt_err, marks_err, options_err:[StringVar]*4, correct_err}
        self._questions: List[Dict[str, Any]] = []

        # ── build static layout ──────────────────────────────────────
        self._build_ui()

        # ── async loads ──────────────────────────────────────────────
        if self._course_id:
            self._fetch_course()
        if self._is_edit:
            self._fetch_exam()

    # =================================================================
    # UI construction
    # =================================================================

    def _build_ui(self) -> None:
        # ----------- Banner (hidden by default) -----------------------
        self._banner_frame = tk.Frame(self, bg=theme.WARNING)
        self._banner_lbl = tk.Label(
            self._banner_frame,
            text="This exam has been attempted and cannot be modified. "
                 "To change it, create a new exam.",
            font=theme.FONT_BODY, bg=theme.WARNING, fg="#000000",
            wraplength=900, padx=12, pady=8,
        )
        self._banner_lbl.pack()
        # Not packed until we know it's locked

        # ----------- Top section: title / duration / course -----------
        top = tk.Frame(self, bg=theme.BG_PRIMARY)
        top.pack(fill="x", padx=24, pady=(16, 4))

        heading = "Edit Exam" if self._is_edit else "Create Exam"
        tk.Label(
            top, text=heading, font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).pack(anchor="w")

        form_row1 = tk.Frame(top, bg=theme.BG_PRIMARY)
        form_row1.pack(fill="x", pady=(8, 0))

        # Title
        lbl_frame_title = tk.Frame(form_row1, bg=theme.BG_PRIMARY)
        lbl_frame_title.pack(side="left", fill="x", expand=True, padx=(0, 12))
        tk.Label(lbl_frame_title, text="Title", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(anchor="w")
        self._title_var = tk.StringVar()
        self._title_entry = tk.Entry(
            lbl_frame_title, textvariable=self._title_var,
            font=theme.FONT_BODY, bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY, relief="flat",
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            highlightthickness=1, bd=4,
        )
        self._title_entry.pack(fill="x")
        self._title_err = tk.Label(
            lbl_frame_title, text="", font=("Segoe UI", 9),
            bg=theme.BG_PRIMARY, fg=theme.ERROR, anchor="w",
        )
        self._title_err.pack(anchor="w")
        self._title_var.trace_add("write", lambda *_a: self._validate())

        # Duration
        lbl_frame_dur = tk.Frame(form_row1, bg=theme.BG_PRIMARY)
        lbl_frame_dur.pack(side="left", padx=(0, 12))
        tk.Label(lbl_frame_dur, text="Duration (min)", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(anchor="w")
        self._dur_var = tk.StringVar()
        self._dur_entry = tk.Entry(
            lbl_frame_dur, textvariable=self._dur_var, width=10,
            font=theme.FONT_BODY, bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY, relief="flat",
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            highlightthickness=1, bd=4,
        )
        self._dur_entry.pack()
        self._dur_err = tk.Label(
            lbl_frame_dur, text="", font=("Segoe UI", 9),
            bg=theme.BG_PRIMARY, fg=theme.ERROR, anchor="w",
        )
        self._dur_err.pack(anchor="w")
        self._dur_var.trace_add("write", lambda *_a: self._validate())

        # Course display (read-only)
        lbl_frame_course = tk.Frame(form_row1, bg=theme.BG_PRIMARY)
        lbl_frame_course.pack(side="left")
        tk.Label(lbl_frame_course, text="Course", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(anchor="w")
        self._course_lbl = tk.Label(
            lbl_frame_course, text="Loading\u2026", font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        )
        self._course_lbl.pack(anchor="w")

        # Helper text
        tk.Label(
            top,
            text="Tip: Activation is done from the course detail Exams tab, not here.",
            font=("Segoe UI", 9, "italic"),
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 4))

        # ----------- Middle section: questions list -------------------
        mid_top = tk.Frame(self, bg=theme.BG_PRIMARY)
        mid_top.pack(fill="x", padx=24)

        self._add_mcq_btn = tk.Button(
            mid_top, text="+ Add MCQ", font=("Segoe UI", 10, "bold"),
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0, padx=10, pady=3,
            command=lambda: self._add_question("mcq"),
        )
        self._add_mcq_btn.pack(side="left", padx=(0, 8))

        self._add_sa_btn = tk.Button(
            mid_top, text="+ Add Short Answer", font=("Segoe UI", 10, "bold"),
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0, padx=10, pady=3,
            command=lambda: self._add_question("short_answer"),
        )
        self._add_sa_btn.pack(side="left")

        # Will be rebuilt whenever questions change
        self._canvas: Optional[tk.Canvas] = None
        self._inner: Optional[tk.Frame] = None

        # ----------- Bottom section: Cancel / Save / Total marks ------
        # Packed BEFORE the expanding questions container so Tk always
        # allocates space for the Save button (bottom-first priority).
        bot = tk.Frame(self, bg=theme.BG_PRIMARY)
        bot.pack(side="bottom", fill="x", padx=24, pady=(4, 12))

        # Questions container — fills remaining space
        self._questions_container = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._questions_container.pack(fill="both", expand=True, padx=24, pady=(4, 0))

        self._cancel_btn = tk.Button(
            bot, text="Cancel", font=theme.FONT_BUTTON,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0,
            highlightbackground=theme.BORDER, highlightthickness=1,
            padx=theme.PAD_MEDIUM, pady=theme.PAD_SMALL,
            command=self._go_back,
        )
        self._cancel_btn.pack(side="left")

        right_bot = tk.Frame(bot, bg=theme.BG_PRIMARY)
        right_bot.pack(side="right")

        self._total_marks_lbl = tk.Label(
            right_bot, text="Total marks: 0", font=theme.FONT_SMALL,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        )
        self._total_marks_lbl.pack(anchor="e", pady=(0, 2))

        self._save_btn = tk.Button(
            right_bot, text="Save", font=theme.FONT_BUTTON,
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=theme.PAD_MEDIUM, pady=theme.PAD_SMALL,
            command=self._save,
        )
        self._save_btn.pack(anchor="e")
        self._save_tooltip = _ToolTip(self._save_btn, "")

        # Initial validation pass
        self._validate()

    # =================================================================
    # Question data management
    # =================================================================

    def _make_question(self, qtype: str) -> Dict[str, Any]:
        """Create a blank question dict for the given type."""
        q: Dict[str, Any] = {
            "type": qtype,
            "prompt_var": tk.StringVar(),
            "marks_var": tk.StringVar(),
            "prompt_err": tk.StringVar(),
            "marks_err": tk.StringVar(),
        }
        if qtype == "mcq":
            q["options"] = [tk.StringVar() for _ in range(4)]
            q["correct_var"] = tk.StringVar()
            q["options_err"] = [tk.StringVar() for _ in range(4)]
            q["correct_err"] = tk.StringVar()
        # wire traces
        q["prompt_var"].trace_add("write", lambda *_a: self._validate())
        q["marks_var"].trace_add("write", lambda *_a: self._validate())
        if qtype == "mcq":
            for ov in q["options"]:
                ov.trace_add("write", lambda *_a: self._validate())
            q["correct_var"].trace_add("write", lambda *_a: self._validate())
        return q

    def _add_question(self, qtype: str) -> None:
        q = self._make_question(qtype)
        self._questions.append(q)
        self._rebuild_questions()
        self._validate()

    def _remove_question(self, idx: int) -> None:
        if 0 <= idx < len(self._questions):
            self._questions.pop(idx)
            self._rebuild_questions()
            self._validate()

    def _move_question(self, idx: int, direction: int) -> None:
        new_idx = idx + direction
        if 0 <= new_idx < len(self._questions):
            self._questions[idx], self._questions[new_idx] = (
                self._questions[new_idx],
                self._questions[idx],
            )
            self._rebuild_questions()

    # =================================================================
    # Rebuild question cards
    # =================================================================

    def _rebuild_questions(self) -> None:
        for w in self._questions_container.winfo_children():
            w.destroy()
        self._canvas = None
        self._inner = None

        if not self._questions:
            tk.Label(
                self._questions_container,
                text="No questions yet. Click \u201c+ Add MCQ\u201d or "
                     "\u201c+ Add Short Answer\u201d above.",
                font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(pady=30)
            return

        self._canvas, self._inner = _make_scrollable(self._questions_container)

        for idx, q in enumerate(self._questions):
            self._render_question_card(self._inner, idx, q)

    def _render_question_card(
        self, parent: tk.Widget, idx: int, q: Dict[str, Any]
    ) -> None:
        card = tk.Frame(
            parent, bg=theme.BG_SECONDARY,
            highlightbackground=theme.BORDER, highlightthickness=1,
        )
        card.pack(fill="x", pady=4, padx=2)

        # Header row: order indicator + type badge + arrows + remove
        hdr = tk.Frame(card, bg=theme.BG_SECONDARY)
        hdr.pack(fill="x", padx=10, pady=(8, 2))

        tk.Label(
            hdr, text=f"Q{idx + 1}", font=("Segoe UI", 11, "bold"),
            bg=theme.BG_SECONDARY, fg=theme.ACCENT,
        ).pack(side="left")

        type_text = "MCQ" if q["type"] == "mcq" else "Short Answer"
        tk.Label(
            hdr, text=f"  [{type_text}]", font=("Segoe UI", 10),
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        ).pack(side="left")

        # Remove button
        if not self._locked:
            tk.Button(
                hdr, text="\u2716", font=("Segoe UI", 9),
                bg=theme.BG_SECONDARY, fg=theme.ERROR,
                activebackground=theme.ERROR, activeforeground="#FFFFFF",
                relief="flat", cursor="hand2", bd=0, padx=4,
                command=lambda i=idx: self._remove_question(i),
            ).pack(side="right")

            # Down arrow
            if idx < len(self._questions) - 1:
                tk.Button(
                    hdr, text="\u25BC", font=("Segoe UI", 9),
                    bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                    activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
                    relief="flat", cursor="hand2", bd=0, padx=4,
                    command=lambda i=idx: self._move_question(i, 1),
                ).pack(side="right")

            # Up arrow
            if idx > 0:
                tk.Button(
                    hdr, text="\u25B2", font=("Segoe UI", 9),
                    bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                    activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
                    relief="flat", cursor="hand2", bd=0, padx=4,
                    command=lambda i=idx: self._move_question(i, -1),
                ).pack(side="right")

        # Body
        body = tk.Frame(card, bg=theme.BG_SECONDARY)
        body.pack(fill="x", padx=10, pady=(0, 8))

        # Prompt
        tk.Label(body, text="Prompt", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(anchor="w")
        prompt_txt = tk.Text(
            body, font=theme.FONT_BODY, bg=theme.BG_INPUT,
            fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat", height=3, wrap="word",
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            highlightthickness=1, bd=4,
        )
        prompt_txt.pack(fill="x")
        if self._locked:
            prompt_txt.configure(state="disabled")

        # Sync prompt text widget ↔ StringVar
        def _sync_prompt_to_var(_event=None, sv=q["prompt_var"], tw=prompt_txt):
            try:
                sv.set(tw.get("1.0", "end-1c"))
            except tk.TclError:
                pass

        prompt_txt.bind("<KeyRelease>", _sync_prompt_to_var)

        # If var already has content (loading), insert it
        existing_prompt = q["prompt_var"].get()
        if existing_prompt:
            prompt_txt.insert("1.0", existing_prompt)
        # Store reference so we can disable later
        q["_prompt_widget"] = prompt_txt

        err_lbl = tk.Label(body, textvariable=q["prompt_err"],
                           font=("Segoe UI", 9), bg=theme.BG_SECONDARY,
                           fg=theme.ERROR, anchor="w")
        err_lbl.pack(anchor="w")

        # Marks
        marks_row = tk.Frame(body, bg=theme.BG_SECONDARY)
        marks_row.pack(fill="x", pady=(2, 0))
        tk.Label(marks_row, text="Marks", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(side="left")
        marks_ent = tk.Entry(
            marks_row, textvariable=q["marks_var"], width=6,
            font=theme.FONT_BODY, bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
            insertbackground=theme.TEXT_PRIMARY, relief="flat",
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            highlightthickness=1, bd=4,
        )
        marks_ent.pack(side="left", padx=(6, 0))
        if self._locked:
            marks_ent.configure(state="disabled")
        tk.Label(marks_row, textvariable=q["marks_err"],
                 font=("Segoe UI", 9), bg=theme.BG_SECONDARY,
                 fg=theme.ERROR, anchor="w").pack(side="left", padx=(8, 0))

        # MCQ-specific fields
        if q["type"] == "mcq":
            opts_frame = tk.Frame(body, bg=theme.BG_SECONDARY)
            opts_frame.pack(fill="x", pady=(4, 0))

            for i, letter in enumerate(_LETTERS):
                opt_row = tk.Frame(opts_frame, bg=theme.BG_SECONDARY)
                opt_row.pack(fill="x", pady=1)
                tk.Label(opt_row, text=f"Option {letter}:",
                         font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                         fg=theme.TEXT_SECONDARY, width=10, anchor="w",
                         ).pack(side="left")
                opt_ent = tk.Entry(
                    opt_row, textvariable=q["options"][i],
                    font=theme.FONT_BODY, bg=theme.BG_INPUT,
                    fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
                    relief="flat",
                    highlightbackground=theme.BORDER,
                    highlightcolor=theme.ACCENT,
                    highlightthickness=1, bd=4,
                )
                opt_ent.pack(side="left", fill="x", expand=True)
                if self._locked:
                    opt_ent.configure(state="disabled")
                tk.Label(opt_row, textvariable=q["options_err"][i],
                         font=("Segoe UI", 9), bg=theme.BG_SECONDARY,
                         fg=theme.ERROR, anchor="w").pack(side="left", padx=(4, 0))

            # Correct option combobox
            correct_row = tk.Frame(body, bg=theme.BG_SECONDARY)
            correct_row.pack(fill="x", pady=(4, 0))
            tk.Label(correct_row, text="Correct Option:",
                     font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                     fg=theme.TEXT_SECONDARY).pack(side="left")
            style = ttk.Style(correct_row)
            style.theme_use("clam")
            style.configure(
                "ES.TCombobox",
                fieldbackground=theme.BG_INPUT,
                background=theme.BG_SECONDARY,
                foreground=theme.TEXT_PRIMARY,
                arrowcolor=theme.TEXT_SECONDARY,
                bordercolor=theme.BORDER,
                selectbackground=theme.ACCENT,
                selectforeground="#FFFFFF",
            )
            combo = ttk.Combobox(
                correct_row, textvariable=q["correct_var"],
                values=_LETTERS, width=5, style="ES.TCombobox",
                state="disabled" if self._locked else "readonly",
                font=theme.FONT_BODY,
            )
            combo.pack(side="left", padx=(6, 0))
            tk.Label(correct_row, textvariable=q["correct_err"],
                     font=("Segoe UI", 9), bg=theme.BG_SECONDARY,
                     fg=theme.ERROR, anchor="w").pack(side="left", padx=(8, 0))

    # =================================================================
    # Validation
    # =================================================================

    def _validate(self) -> None:
        """Run validation, update error labels, update Save button state."""
        issues: List[str] = []

        # Title
        title = self._title_var.get().strip()
        if not title:
            self._title_err.configure(text="Title is required.")
            issues.append("Title is required")
        else:
            self._title_err.configure(text="")

        # Duration
        dur_raw = self._dur_var.get().strip()
        dur_ok = False
        try:
            dur = int(dur_raw)
            if dur <= 0:
                raise ValueError
            dur_ok = True
        except (ValueError, TypeError):
            pass
        if not dur_ok:
            self._dur_err.configure(text="Must be a positive integer.")
            issues.append("Duration must be > 0")
        else:
            self._dur_err.configure(text="")

        # Questions
        if not self._questions:
            issues.append("At least one question required")

        total_marks = 0
        for idx, q in enumerate(self._questions):
            # Prompt
            prompt = q["prompt_var"].get().strip()
            if not prompt:
                q["prompt_err"].set("Prompt is required.")
                issues.append(f"Q{idx+1}: prompt missing")
            else:
                q["prompt_err"].set("")

            # Marks
            marks_raw = q["marks_var"].get().strip()
            m_ok = False
            try:
                m = int(marks_raw)
                if m <= 0:
                    raise ValueError
                m_ok = True
                total_marks += m
            except (ValueError, TypeError):
                pass
            if not m_ok:
                q["marks_err"].set("Must be > 0.")
                issues.append(f"Q{idx+1}: invalid marks")
            else:
                q["marks_err"].set("")

            # MCQ specifics
            if q["type"] == "mcq":
                for i, letter in enumerate(_LETTERS):
                    if not q["options"][i].get().strip():
                        q["options_err"][i].set("Required.")
                        issues.append(f"Q{idx+1}: option {letter} empty")
                    else:
                        q["options_err"][i].set("")
                if not q["correct_var"].get():
                    q["correct_err"].set("Select one.")
                    issues.append(f"Q{idx+1}: no correct option")
                else:
                    q["correct_err"].set("")

        self._total_marks_lbl.configure(text=f"Total marks: {total_marks}")

        if issues or self._locked:
            self._save_btn.configure(state="disabled", cursor="arrow")
            if self._locked:
                self._save_tooltip.text = "Exam is locked (has sessions)."
            else:
                self._save_tooltip.text = "Fix: " + "; ".join(issues[:5])
        else:
            self._save_btn.configure(state="normal", cursor="hand2")
            self._save_tooltip.text = ""

    # =================================================================
    # Async data loading
    # =================================================================

    def _fetch_course(self) -> None:
        cid = self._course_id

        def _work():
            ok, data, err = self._api.get(f"/courses/{cid}")
            if ok and data:
                code = data.get("code", "")
                title = data.get("title", "")
                self._root.after(0, lambda: self._set_course_info(code, title))
            else:
                self._root.after(
                    0, lambda: self._course_lbl.configure(text="(unknown)")
                )

        threading.Thread(target=_work, daemon=True).start()

    def _set_course_info(self, code: str, title: str) -> None:
        self._course_code = code
        self._course_title = title
        self._course_lbl.configure(text=f"{code} — {title}")

    def _fetch_exam(self) -> None:
        eid = self._exam_id

        def _work():
            ok, data, err = self._api.get(f"/exams/{eid}")
            if ok and data:
                self._root.after(0, lambda: self._populate_exam(data))
            else:
                msg = err.message if err else "Failed to load exam."
                # Check for 409 (conflict) indicating sessions exist
                if err and err.http_status == 409:
                    self._root.after(0, lambda: self._show_locked())
                else:
                    self._root.after(
                        0, lambda: self._toast.show(msg, "error")
                    )

        threading.Thread(target=_work, daemon=True).start()

    def _populate_exam(self, data: Dict[str, Any]) -> None:
        """Fill form fields from the fetched exam data."""
        self._title_var.set(data.get("title", ""))
        self._dur_var.set(str(data.get("duration_minutes", "")))

        questions = data.get("questions", [])
        # Sort by order_index
        questions.sort(key=lambda q: q.get("order_index", 0))

        self._questions.clear()
        for qd in questions:
            qtype = qd.get("question_type", "short_answer")
            q = self._make_question(qtype)
            q["prompt_var"].set(qd.get("question_text", ""))
            q["marks_var"].set(str(qd.get("marks", "")))

            if qtype == "mcq":
                options = qd.get("options", [])
                for i in range(4):
                    if i < len(options):
                        q["options"][i].set(options[i])
                # Map correct_answer text → letter
                correct_text = qd.get("correct_answer", "")
                if correct_text and correct_text in options:
                    letter_idx = options.index(correct_text)
                    if letter_idx < 4:
                        q["correct_var"].set(_LETTERS[letter_idx])

            self._questions.append(q)

        self._rebuild_questions()
        self._validate()

        # After populating, also check if this exam can be edited by
        # trying to detect sessions. We check the server for editability:
        self._check_editability()

    def _check_editability(self) -> None:
        """Hit a lightweight endpoint to see if the exam is editable."""
        eid = self._exam_id
        cid = self._course_id

        def _work():
            # Try a no-op PATCH to see if the server rejects it
            ok, data, err = self._api.patch(
                f"/exams/{eid}", body={"title": self._title_var.get().strip()}
            )
            if not ok and err and err.http_status == 409:
                self._root.after(0, self._show_locked)

        threading.Thread(target=_work, daemon=True).start()

    def _show_locked(self) -> None:
        if self._locked:
            return  # already locked
        self._locked = True
        # Insert banner at the very top of the screen
        children = self.pack_slaves()
        if children:
            self._banner_frame.pack(fill="x", before=children[0])
        else:
            self._banner_frame.pack(fill="x")
        # Disable top-level fields
        self._title_entry.configure(state="disabled")
        self._dur_entry.configure(state="disabled")
        # Disable add buttons
        self._add_mcq_btn.configure(state="disabled")
        self._add_sa_btn.configure(state="disabled")
        self._rebuild_questions()
        self._validate()

    # =================================================================
    # Save
    # =================================================================

    def _serialize_questions(self) -> List[Dict[str, Any]]:
        result = []
        for idx, q in enumerate(self._questions):
            qd: Dict[str, Any] = {
                "question_text": q["prompt_var"].get().strip(),
                "question_type": q["type"],
                "marks": int(q["marks_var"].get().strip()),
                "order_index": idx + 1,
            }
            if q["type"] == "mcq":
                opts = [q["options"][i].get().strip() for i in range(4)]
                qd["options"] = opts
                letter = q["correct_var"].get()
                if letter in _LETTERS:
                    qd["correct_answer"] = opts[_LETTERS.index(letter)]
            result.append(qd)
        return result

    def _save(self) -> None:
        self._save_btn.configure(state="disabled", text="Saving\u2026")
        questions = self._serialize_questions()

        if self._is_edit:
            self._save_edit(questions)
        else:
            self._save_create(questions)

    def _save_create(self, questions: List[Dict[str, Any]]) -> None:
        cid = self._course_id
        payload = {
            "title": self._title_var.get().strip(),
            "duration_minutes": int(self._dur_var.get().strip()),
            "questions": questions,
        }

        def _work():
            ok, data, err = self._api.post(
                f"/courses/{cid}/exams", body=payload
            )
            self._root.after(0, lambda: self._handle_save_result(ok, data, err))

        threading.Thread(target=_work, daemon=True).start()

    def _save_edit(self, questions: List[Dict[str, Any]]) -> None:
        eid = self._exam_id
        meta_payload = {
            "title": self._title_var.get().strip(),
            "duration_minutes": int(self._dur_var.get().strip()),
        }
        q_payload = {"questions": questions}

        def _work():
            # 1) Update metadata
            ok, data, err = self._api.patch(
                f"/exams/{eid}", body=meta_payload
            )
            if not ok:
                self._root.after(
                    0, lambda: self._handle_save_result(ok, data, err)
                )
                return
            # 2) Replace questions
            ok2, data2, err2 = self._api.put(
                f"/exams/{eid}/questions", body=q_payload
            )
            self._root.after(
                0, lambda: self._handle_save_result(ok2, data2, err2)
            )

        threading.Thread(target=_work, daemon=True).start()

    def _handle_save_result(
        self,
        ok: bool,
        data: Optional[Dict],
        err: Any,
    ) -> None:
        self._save_btn.configure(text="Save")
        self._validate()  # re-enable if valid

        if ok:
            self._toast.show("Exam saved", "success")
            # Navigate back to teacher dashboard after short delay
            self._root.after(
                800,
                lambda: self._router.show("teacher_dashboard", push=False),
            )
        else:
            # Server-side errors
            if err:
                # Field errors
                if err.field_errors:
                    self._apply_server_errors(err.field_errors)
                self._toast.show(err.message, "error")
            else:
                self._toast.show("Save failed.", "error")

    def _apply_server_errors(self, field_errors: Dict[str, List[str]]) -> None:
        """Map server field error keys back to form labels."""
        for key, msgs in field_errors.items():
            msg = msgs[0] if msgs else ""
            if key == "title":
                self._title_err.configure(text=msg)
            elif key == "duration_minutes":
                self._dur_err.configure(text=msg)
            elif key.startswith("questions["):
                # e.g. questions[0].question_text
                try:
                    rest = key.split("]", 1)
                    idx = int(rest[0].split("[")[1])
                    field = rest[1].lstrip(".")
                    if idx < len(self._questions):
                        q = self._questions[idx]
                        if "question_text" in field:
                            q["prompt_err"].set(msg)
                        elif "marks" in field:
                            q["marks_err"].set(msg)
                        elif "options" in field and q["type"] == "mcq":
                            # options[0], options[1], etc.
                            try:
                                oi = int(field.split("[")[1].split("]")[0])
                                if oi < 4:
                                    q["options_err"][oi].set(msg)
                            except (ValueError, IndexError):
                                pass
                        elif "correct_answer" in field and q["type"] == "mcq":
                            q["correct_err"].set(msg)
                except (ValueError, IndexError):
                    pass

    # =================================================================
    # Navigation
    # =================================================================

    def _go_back(self) -> None:
        self._router.show("teacher_dashboard", push=False)
