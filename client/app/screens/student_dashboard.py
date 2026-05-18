"""
Student dashboard — sidebar navigation + switchable content area.

Sub-views: Courses, Available Exams, History.
All network calls run in background threads; results are marshalled back
to the main thread via ``root.after``.  Sub-view data is cached in
``SessionState`` transient storage so tab-switching does not re-fetch.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from client.app.ui import theme


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_SIDEBAR_WIDTH = 240
_NAV_ITEMS = ("Courses", "Available Exams", "History")

_STATUS_COLORS: Dict[str, str] = {
    "active": theme.SUCCESS,
    "inactive": theme.TEXT_SECONDARY,
    "pre_check": theme.WARNING,
    "not_started": theme.TEXT_SECONDARY,
    "in_progress": theme.WARNING,
    "submitted": theme.SUCCESS,
    "expired": theme.ERROR,
    "aborted_vm": theme.ERROR,
    "aborted_stealth_vm": theme.ERROR,
}


# ===================================================================
# Helper: scrollable frame factory
# ===================================================================

def _make_scrollable(parent: tk.Widget):
    """Return ``(canvas, scrollable_frame)`` packed inside *parent*."""
    canvas = tk.Canvas(parent, bg=theme.BG_PRIMARY, highlightthickness=0, bd=0)
    vsb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=theme.BG_PRIMARY)

    inner.bind(
        "<Configure>",
        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=inner, anchor="nw",
                         tags=("inner",))
    canvas.configure(yscrollcommand=vsb.set)

    # Make the inner frame stretch to the canvas width.
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


# ===================================================================
# Main screen
# ===================================================================

class StudentDashboardScreen(tk.Frame):
    """Full student dashboard with left sidebar and three sub-views."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api           # type: ignore[attr-defined]
        self._session = router.session   # type: ignore[attr-defined]
        self._root: tk.Tk = router.root

        # Use session-state transient storage for cache persistence
        existing = self._session.get("_dashboard_cache")
        if existing is None:
            existing = {}
            self._session.set("_dashboard_cache", existing)
        self._cache: Dict[str, Any] = existing
        self._active_nav: Optional[str] = None
        self._nav_buttons: Dict[str, tk.Label] = {}
        self._current_subview: Optional[tk.Frame] = None

        self._build_sidebar()
        self._build_content_area()
        self._select_nav("Courses")

    # ---- sidebar ----------------------------------------------------------

    def _build_sidebar(self) -> None:
        sb = tk.Frame(self, bg=theme.BG_SECONDARY, width=_SIDEBAR_WIDTH)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        user = self._session.user or {}
        name = user.get("full_name", "Student")
        role = user.get("role", "student").title()

        info = tk.Frame(sb, bg=theme.BG_SECONDARY)
        info.pack(fill="x", padx=16, pady=(20, 20))
        tk.Label(info, text=name, font=theme.FONT_SUBHEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 anchor="w", wraplength=200).pack(fill="x")
        tk.Label(info, text=role, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                 anchor="w").pack(fill="x")

        tk.Frame(sb, bg=theme.BORDER, height=1).pack(fill="x", padx=16)

        nav = tk.Frame(sb, bg=theme.BG_SECONDARY)
        nav.pack(fill="x", padx=8, pady=12)
        for item in _NAV_ITEMS:
            btn = tk.Label(
                nav, text=item, font=theme.FONT_BODY,
                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                anchor="w", padx=12, pady=8, cursor="hand2",
            )
            btn.pack(fill="x", pady=1)
            btn.bind("<Button-1>", lambda _e, n=item: self._select_nav(n))
            self._nav_buttons[item] = btn

        tk.Frame(sb, bg=theme.BG_SECONDARY).pack(fill="both", expand=True)

        logout = tk.Button(
            sb, text="Logout", font=theme.FONT_BUTTON,
            bg=theme.BG_SECONDARY, fg=theme.ERROR,
            activebackground=theme.BG_INPUT, activeforeground=theme.ERROR,
            relief="flat", cursor="hand2", bd=0,
            command=self._on_logout,
        )
        logout.pack(fill="x", padx=16, pady=(0, 20), ipady=6)

    # ---- content ----------------------------------------------------------

    def _build_content_area(self) -> None:
        self._content = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._content.pack(side="right", fill="both", expand=True)

    # ---- navigation -------------------------------------------------------

    def _select_nav(self, name: str) -> None:
        if name == self._active_nav:
            return
        self._active_nav = name
        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(bg=theme.ACCENT, fg="#FFFFFF")
            else:
                btn.configure(bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY)
        self._swap_subview(name)

    def _swap_subview(self, name: str) -> None:
        if self._current_subview:
            self._current_subview.destroy()
            self._current_subview = None

        factory = {
            "Courses": _CoursesView,
            "Available Exams": _AvailableExamsView,
            "History": _HistoryView,
        }.get(name)
        if factory is None:
            return
        sv = factory(self._content, self)
        sv.pack(fill="both", expand=True)
        self._current_subview = sv

    # ---- logout -----------------------------------------------------------

    def _on_logout(self) -> None:
        self._api.clear_token()
        self._session.logout()
        self._router.show("login", push=False)


# ===================================================================
# Base class shared by all sub-views
# ===================================================================

class _SubViewBase(tk.Frame):
    """Header + refresh + body container."""

    def __init__(self, parent: tk.Widget, dashboard: StudentDashboardScreen,
                 title: str) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self.dashboard = dashboard
        self.api = dashboard._api
        self.sess = dashboard._session
        self.root = dashboard._root
        self.cache = dashboard._cache

        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", padx=24, pady=(20, 10))
        tk.Label(hdr, text=title, font=theme.FONT_HEADING,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY).pack(side="left")

        ref = tk.Button(
            hdr, text="\u21bb Refresh", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
            activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0, padx=8, pady=2,
            command=self._on_refresh,
        )
        ref.pack(side="right")

        self.body = tk.Frame(self, bg=theme.BG_PRIMARY)
        self.body.pack(fill="both", expand=True, padx=24)

    # Subclasses override
    def _on_refresh(self) -> None:
        pass

    # helpers
    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    def _show_loading(self) -> None:
        tk.Label(self.body, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=40)

    def _show_error(self, msg: str) -> None:
        self._clear_body()
        tk.Label(self.body, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=40)

    def _bg_fetch(self, getter: Callable, on_ok: Callable, on_err: Callable) -> None:
        """Run *getter* in a daemon thread, marshal result back via after."""
        def _work():
            ok, payload, err = getter()
            if ok:
                self.root.after(0, lambda: on_ok(payload))
            else:
                msg = err.message if err else "Request failed."
                self.root.after(0, lambda: on_err(msg))
        threading.Thread(target=_work, daemon=True).start()


# ===================================================================
# Courses sub-view
# ===================================================================

class _CoursesView(_SubViewBase):
    def __init__(self, parent: tk.Widget, dashboard: StudentDashboardScreen) -> None:
        super().__init__(parent, dashboard, "My Courses")
        cached = self.cache.get("courses")
        if cached is not None:
            self._render(cached)
        else:
            self._show_loading()
            self._fetch()

    def _on_refresh(self) -> None:
        self.cache.pop("courses", None)
        self._clear_body()
        self._show_loading()
        self._fetch()

    def _fetch(self) -> None:
        self._bg_fetch(
            lambda: self.api.get("/courses/me?page_size=100"),
            self._on_ok,
            self._show_error,
        )

    def _on_ok(self, payload: dict) -> None:
        items = payload.get("items", [])
        self.cache["courses"] = items
        self._clear_body()
        self._render(items)

    def _render(self, items: List[dict]) -> None:
        if not items:
            tk.Label(
                self.body,
                text="You are not enrolled in any courses yet",
                font=theme.FONT_BODY,
                bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(pady=60)
            return

        _canvas, scrollable = _make_scrollable(self.body)
        for c in items:
            self._card(scrollable, c)

    def _card(self, parent: tk.Widget, course: dict) -> None:
        card = tk.Frame(parent, bg=theme.BG_SECONDARY,
                        highlightbackground=theme.BORDER,
                        highlightthickness=1, cursor="hand2")
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=16, pady=12)

        tk.Label(inner, text=course.get("code", ""), font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.ACCENT).pack(anchor="w")
        tk.Label(inner, text=course.get("title", ""),
                 font=theme.FONT_SUBHEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(anchor="w")
        tk.Label(inner, text=f"Teacher: {course.get('teacher_name', '')}",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(anchor="w")

        def _click(_e, c=course):
            self._show_detail(c)
        for w in (card, inner, *inner.winfo_children()):
            w.bind("<Button-1>", _click)

    # ---- course-detail mini-view ----

    def _show_detail(self, course: dict) -> None:
        self._clear_body()
        _CourseDetailMini(self.body, self, course).pack(fill="both", expand=True)


class _CourseDetailMini(tk.Frame):
    """In-place detail showing the exams in a course."""

    def __init__(self, parent: tk.Widget, courses_view: _CoursesView,
                 course: dict) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._cv = courses_view
        self._api = courses_view.api
        self._root = courses_view.root

        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", pady=(0, 10))
        back = tk.Label(hdr, text="\u2190 Back", font=theme.FONT_BODY,
                        bg=theme.BG_PRIMARY, fg=theme.ACCENT, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda _e: self._go_back())
        tk.Label(hdr, text=f"{course.get('code', '')} \u2014 {course.get('title', '')}",
                 font=theme.FONT_SUBHEADING, bg=theme.BG_PRIMARY,
                 fg=theme.TEXT_PRIMARY).pack(side="left", padx=12)

        self._inner = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._inner.pack(fill="both", expand=True)
        tk.Label(self._inner, text="Loading exams\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=20)

        cid = course.get("id")
        threading.Thread(target=self._fetch, args=(cid,), daemon=True).start()

    def _fetch(self, course_id: int) -> None:
        ok, payload, err = self._api.get(
            f"/courses/{course_id}/exams?page_size=100")
        if ok:
            items = payload.get("items", [])
            self._root.after(0, lambda: self._render(items))
        else:
            msg = err.message if err else "Failed to load exams."
            self._root.after(0, lambda: self._err(msg))

    def _err(self, msg: str) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        tk.Label(self._inner, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=20)

    def _render(self, items: list) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        if not items:
            tk.Label(self._inner, text="No exams in this course yet.",
                     font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(pady=20)
            return

        _canvas, scrollable = _make_scrollable(self._inner)
        for ex in items:
            row = tk.Frame(scrollable, bg=theme.BG_SECONDARY,
                           highlightbackground=theme.BORDER,
                           highlightthickness=1)
            row.pack(fill="x", pady=3)
            ri = tk.Frame(row, bg=theme.BG_SECONDARY)
            ri.pack(fill="x", padx=16, pady=10)

            tk.Label(ri, text=ex.get("title", ""), font=theme.FONT_BODY,
                     bg=theme.BG_SECONDARY,
                     fg=theme.TEXT_PRIMARY).pack(anchor="w")

            badges = tk.Frame(ri, bg=theme.BG_SECONDARY)
            badges.pack(anchor="w")
            active = ex.get("is_active", False)
            a_txt = "Active" if active else "Inactive"
            a_clr = theme.SUCCESS if active else theme.TEXT_SECONDARY
            tk.Label(badges, text=a_txt, font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=a_clr).pack(side="left",
                                                            padx=(0, 12))
            ss = ex.get("session_status")
            if ss:
                clr = _STATUS_COLORS.get(ss, theme.TEXT_SECONDARY)
                tk.Label(badges, text=f"Session: {ss}",
                         font=theme.FONT_SMALL,
                         bg=theme.BG_SECONDARY, fg=clr).pack(side="left")

    def _go_back(self) -> None:
        self._cv._clear_body()
        self._cv._render(self._cv.cache.get("courses", []))


# ===================================================================
# Available Exams sub-view
# ===================================================================

class _AvailableExamsView(_SubViewBase):
    def __init__(self, parent: tk.Widget,
                 dashboard: StudentDashboardScreen) -> None:
        super().__init__(parent, dashboard, "Available Exams")
        cached = self.cache.get("active_exams")
        if cached is not None:
            self._render(cached)
        else:
            self._show_loading()
            self._fetch()

    def _on_refresh(self) -> None:
        self.cache.pop("active_exams", None)
        self._clear_body()
        self._show_loading()
        self._fetch()

    def _fetch(self) -> None:
        self._bg_fetch(
            lambda: self.api.get("/exams/active?page_size=100"),
            self._on_ok,
            self._show_error,
        )

    def _on_ok(self, payload: dict) -> None:
        items = payload.get("items", [])
        self.cache["active_exams"] = items
        self._clear_body()
        self._render(items)

    def _render(self, items: List[dict]) -> None:
        if not items:
            tk.Label(
                self.body,
                text="No active exams available right now.",
                font=theme.FONT_BODY,
                bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(pady=60)
            return

        _canvas, scrollable = _make_scrollable(self.body)
        for ex in items:
            self._row(scrollable, ex)

    def _row(self, parent: tk.Widget, exam: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=4)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=16, pady=10)

        left = tk.Frame(inner, bg=theme.BG_SECONDARY)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text=exam.get("title", ""), font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(anchor="w")
        course_str = f"{exam.get('course_code', '')} \u2014 {exam.get('course_title', '')}"
        tk.Label(left, text=course_str, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY).pack(anchor="w")
        tk.Label(left, text=f"{exam.get('duration_minutes', 0)} min",
                 font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY).pack(anchor="w")

        right = tk.Frame(inner, bg=theme.BG_SECONDARY)
        right.pack(side="right")

        ss = exam.get("session_status")
        sid = exam.get("session_id")
        eid = exam.get("id")

        if ss:
            clr = _STATUS_COLORS.get(ss, theme.TEXT_SECONDARY)
            tk.Label(right, text=ss, font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=clr).pack(pady=(0, 4))

        btn_text, btn_cmd = self._action(eid, ss, sid)
        if btn_text:
            b = tk.Button(
                right, text=btn_text, font=("Segoe UI", 10, "bold"),
                bg=theme.ACCENT, fg="#FFFFFF",
                activebackground=theme.ACCENT_HOVER,
                activeforeground="#FFFFFF",
                relief="flat", cursor="hand2", bd=0,
                padx=12, pady=4, command=btn_cmd,
            )
            b.pack()

    def _action(self, exam_id, ss, sid):
        if ss == "submitted":
            return ("View Result",
                    lambda: self.dashboard._router.show(
                        "exam_taking", session_id=sid))
        if ss == "in_progress":
            return ("Resume",
                    lambda: self.dashboard._router.show(
                        "exam_taking", session_id=sid))
        if ss in ("aborted_vm", "aborted_stealth_vm"):
            return ("Retry Exam", lambda: self._start(exam_id))
        return ("Start Exam", lambda: self._start(exam_id))

    def _start(self, exam_id: int) -> None:
        self._clear_body()
        self._show_loading()

        def _work():
            ok, payload, err = self.api.post(
                "/sessions", body={"exam_id": exam_id})
            if ok:
                sid = payload.get("id")
                self.root.after(
                    0, lambda: self.dashboard._router.show(
                        "exam_integrity_check", session_id=sid))
            else:
                msg = err.message if err else "Failed to start exam."
                self.root.after(0, lambda: self._show_error(msg))
        threading.Thread(target=_work, daemon=True).start()


# ===================================================================
# History sub-view
# ===================================================================

class _HistoryView(_SubViewBase):
    def __init__(self, parent: tk.Widget,
                 dashboard: StudentDashboardScreen) -> None:
        super().__init__(parent, dashboard, "Exam History")
        self._page = 1
        cached = self.cache.get("history")
        if cached is not None:
            self._render(cached)
        else:
            self._show_loading()
            self._fetch()

    def _on_refresh(self) -> None:
        self.cache.pop("history", None)
        self._page = 1
        self._clear_body()
        self._show_loading()
        self._fetch()

    def _fetch(self) -> None:
        self._bg_fetch(
            lambda: self.api.get(
                f"/sessions/me?page={self._page}&page_size=20"),
            self._on_ok,
            self._show_error,
        )

    def _on_ok(self, payload: dict) -> None:
        self.cache["history"] = payload
        self._clear_body()
        self._render(payload)

    def _render(self, payload: dict) -> None:
        items = payload.get("items", [])
        pagination = payload.get("pagination", {})

        if not items:
            tk.Label(
                self.body,
                text="No exam history yet.",
                font=theme.FONT_BODY,
                bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(pady=60)
            return

        _canvas, scrollable = _make_scrollable(self.body)

        # column header
        hdr = tk.Frame(scrollable, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in (("Date", 14), ("Exam", 30), ("Status", 18), ("Score", 10)):
            tk.Label(hdr, text=txt, font=theme.FONT_SMALL,
                     bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
                     width=w, anchor="w").pack(side="left")

        for s in items:
            self._session_row(scrollable, s)

        # pagination
        total_pages = pagination.get("total_pages", 1)
        if total_pages > 1:
            pf = tk.Frame(scrollable, bg=theme.BG_PRIMARY)
            pf.pack(fill="x", pady=12)
            if self._page > 1:
                tk.Button(
                    pf, text="\u2190 Prev", font=theme.FONT_SMALL,
                    bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                    relief="flat", cursor="hand2",
                    command=lambda: self._go_page(-1),
                ).pack(side="left")
            tk.Label(
                pf, text=f"Page {self._page} of {total_pages}",
                font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(side="left", padx=12)
            if self._page < total_pages:
                tk.Button(
                    pf, text="Next \u2192", font=theme.FONT_SMALL,
                    bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                    relief="flat", cursor="hand2",
                    command=lambda: self._go_page(1),
                ).pack(side="left")

    def _session_row(self, parent: tk.Widget, sess: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=2)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=12, pady=8)

        ended = sess.get("ended_at", "") or ""
        date_str = ended[:10] if ended else "\u2014"
        tk.Label(inner, text=date_str, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                 width=14, anchor="w").pack(side="left")

        tk.Label(inner, text=sess.get("exam_title", ""),
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_PRIMARY, width=30,
                 anchor="w").pack(side="left")

        status = sess.get("status", "")
        clr = _STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
        tk.Label(inner, text=status, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=clr,
                 width=18, anchor="w").pack(side="left")

        score = sess.get("score")
        total = sess.get("total_marks")
        stxt = f"{score}/{total}" if score is not None else "\u2014"
        tk.Label(inner, text=stxt, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 width=10, anchor="w").pack(side="left")

        if status == "submitted":
            for w in (row, inner, *inner.winfo_children()):
                w.configure(cursor="hand2")
                w.bind("<Button-1>",
                       lambda _e, s=sess: self._show_result(s))

    def _go_page(self, delta: int) -> None:
        self._page += delta
        self.cache.pop("history", None)
        self._clear_body()
        self._show_loading()
        self._fetch()

    # ---- result drill-down ----

    def _show_result(self, sess: dict) -> None:
        self._clear_body()
        _ResultDetail(self.body, self, sess.get("id")).pack(
            fill="both", expand=True)


class _ResultDetail(tk.Frame):
    """Drill-down view for a submitted session's result."""

    def __init__(self, parent: tk.Widget, history_view: _HistoryView,
                 session_id: int) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._hv = history_view
        self._api = history_view.api
        self._root = history_view.root

        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", pady=(0, 10))
        back = tk.Label(hdr, text="\u2190 Back", font=theme.FONT_BODY,
                        bg=theme.BG_PRIMARY, fg=theme.ACCENT, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda _e: self._go_back())
        tk.Label(hdr, text="Exam Result", font=theme.FONT_SUBHEADING,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY).pack(
            side="left", padx=12)

        self._inner = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._inner.pack(fill="both", expand=True)
        tk.Label(self._inner, text="Loading result\u2026",
                 font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                 fg=theme.TEXT_SECONDARY).pack(pady=20)

        threading.Thread(target=self._fetch, args=(session_id,),
                         daemon=True).start()

    def _fetch(self, sid: int) -> None:
        ok, payload, err = self._api.get(f"/sessions/{sid}/result")
        if ok:
            self._root.after(0, lambda: self._render(payload))
        else:
            msg = err.message if err else "Failed to load result."
            self._root.after(0, lambda: self._err(msg))

    def _err(self, msg: str) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        tk.Label(self._inner, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=20)

    def _render(self, result: dict) -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        # summary card
        card = tk.Frame(self._inner, bg=theme.BG_SECONDARY,
                        highlightbackground=theme.BORDER,
                        highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        ci = tk.Frame(card, bg=theme.BG_SECONDARY)
        ci.pack(padx=16, pady=12, fill="x")
        tk.Label(ci, text=result.get("exam_title", ""),
                 font=theme.FONT_SUBHEADING, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_PRIMARY).pack(anchor="w")
        score = result.get("score")
        total = result.get("total_marks")
        stxt = f"Score: {score}/{total}" if score is not None else "Score: \u2014"
        tk.Label(ci, text=stxt, font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(anchor="w")

        # question breakdown
        _canvas, scrollable = _make_scrollable(self._inner)
        for i, q in enumerate(result.get("breakdown", []), 1):
            qc = tk.Frame(scrollable, bg=theme.BG_SECONDARY,
                          highlightbackground=theme.BORDER,
                          highlightthickness=1)
            qc.pack(fill="x", pady=3)
            qi = tk.Frame(qc, bg=theme.BG_SECONDARY)
            qi.pack(padx=16, pady=10, fill="x")

            tk.Label(qi, text=f"Q{i}. {q.get('question_text', '')}",
                     font=theme.FONT_BODY, bg=theme.BG_SECONDARY,
                     fg=theme.TEXT_PRIMARY, wraplength=580,
                     justify="left").pack(anchor="w")

            ans = q.get("answer_text") or "\u2014"
            tk.Label(qi, text=f"Your answer: {ans}",
                     font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                     fg=theme.TEXT_SECONDARY, wraplength=580,
                     justify="left").pack(anchor="w")

            awarded = q.get("marks_awarded")
            marks = q.get("marks", 0)
            mtxt = (f"Marks: {awarded}/{marks}" if awarded is not None
                    else f"Marks: \u2014/{marks}")
            mclr = (theme.SUCCESS if awarded is not None and awarded == marks
                    else theme.TEXT_SECONDARY)
            tk.Label(qi, text=mtxt, font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=mclr).pack(anchor="w")

    def _go_back(self) -> None:
        self._hv._clear_body()
        cached = self._hv.cache.get("history")
        if cached:
            self._hv._render(cached)
        else:
            self._hv._show_loading()
            self._hv._fetch()
