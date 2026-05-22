"""
Teacher dashboard — sidebar navigation + switchable content area.

Sub-views: My Courses, Reports.
Course detail mini-view with Students and Exams tabs.
All network calls run in background threads; results are marshalled back
to the main thread via ``root.after``.
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
_NAV_ITEMS = ("My Courses", "Reports")

_STATUS_COLORS: Dict[str, str] = {
    "active": theme.SUCCESS,
    "inactive": theme.TEXT_SECONDARY,
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


# ===================================================================
# Main screen
# ===================================================================

class TeacherDashboardScreen(tk.Frame):
    """Full teacher dashboard with left sidebar and switchable content."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api
        self._session = router.session
        self._root: tk.Tk = router.root

        existing = self._session.get("_teacher_cache")
        if existing is None:
            existing = {}
            self._session.set("_teacher_cache", existing)
        self._cache: Dict[str, Any] = existing

        self._active_nav: Optional[str] = None
        self._nav_buttons: Dict[str, tk.Label] = {}
        self._current_subview: Optional[tk.Frame] = None

        self._build_sidebar()
        self._build_content_area()
        self._select_nav("My Courses")

    # ---- sidebar ----------------------------------------------------------

    def _build_sidebar(self) -> None:
        sb = tk.Frame(self, bg=theme.BG_SECONDARY, width=_SIDEBAR_WIDTH)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        user = self._session.user or {}
        name = user.get("full_name", "Teacher")
        role = user.get("role", "teacher").title()

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
            "My Courses": _MyCoursesView,
            "Reports": _ReportsView,
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
# Base class shared by sub-views
# ===================================================================

class _SubViewBase(tk.Frame):
    def __init__(self, parent: tk.Widget, dashboard: TeacherDashboardScreen,
                 title: str, *, show_refresh: bool = True) -> None:
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

        if show_refresh:
            tk.Button(
                hdr, text="\u21bb Refresh", font=theme.FONT_SMALL,
                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
                relief="flat", cursor="hand2", bd=0, padx=8, pady=2,
                command=self._on_refresh,
            ).pack(side="right")

        self.body = tk.Frame(self, bg=theme.BG_PRIMARY)
        self.body.pack(fill="both", expand=True, padx=24)

    def _on_refresh(self) -> None:
        pass

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

    def _bg_fetch(self, getter: Callable, on_ok: Callable,
                  on_err: Callable) -> None:
        def _work():
            ok, payload, err = getter()
            if ok:
                self.root.after(0, lambda: on_ok(payload))
            else:
                msg = err.message if err else "Request failed."
                self.root.after(0, lambda: on_err(msg))
        threading.Thread(target=_work, daemon=True).start()


# ===================================================================
# Reports sub-view (placeholder)
# ===================================================================

class _ReportsView(_SubViewBase):
    """Lists every exam the teacher owns, across all courses, with quick
    links into each exam's sessions list."""

    def __init__(self, parent: tk.Widget,
                 dashboard: TeacherDashboardScreen) -> None:
        super().__init__(parent, dashboard, "Reports")
        self._all_exams: List[dict] = []
        self._list_frame = tk.Frame(self.body, bg=theme.BG_PRIMARY)
        self._list_frame.pack(fill="both", expand=True)
        self._show_list_loading()
        self._fetch()

    def _on_refresh(self) -> None:
        self._clear_list()
        self._show_list_loading()
        self._fetch()

    def _clear_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

    def _show_list_loading(self) -> None:
        tk.Label(self._list_frame, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=40)

    def _fetch(self) -> None:
        """Fetch all courses, then all exams per course."""
        def _work():
            ok, payload, err = self.api.get("/courses/me?page_size=100")
            if not ok:
                msg = err.message if err else "Failed to load courses."
                self.root.after(0, lambda: self._show_error(msg))
                return
            courses = payload.get("items", [])
            all_exams: List[dict] = []
            for c in courses:
                cid = c.get("id")
                ok2, p2, _ = self.api.get(
                    f"/courses/{cid}/exams?page_size=100")
                if ok2:
                    for ex in p2.get("items", []):
                        ex["_course_code"] = c.get("code", "")
                        ex["_course_title"] = c.get("title", "")
                        all_exams.append(ex)
            self.root.after(0, lambda: self._render(all_exams))
        threading.Thread(target=_work, daemon=True).start()

    def _render(self, exams: List[dict]) -> None:
        self._clear_list()
        self._all_exams = exams

        if not exams:
            tk.Label(self._list_frame,
                     text="No exams found across your courses.",
                     font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(pady=60)
            return

        canvas = tk.Canvas(self._list_frame, bg=theme.BG_PRIMARY,
                           highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(self._list_frame, orient="vertical",
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

        # Header
        hdr = tk.Frame(inner, bg=theme.BG_INPUT)
        hdr.pack(fill="x", pady=(0, 2))
        for txt, w in [("Course", 12), ("Exam", 28), ("Marks", 8),
                       ("Status", 8), ("", 12)]:
            tk.Label(hdr, text=txt, font=("Segoe UI", 9, "bold"),
                     bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY,
                     width=w, anchor="w").pack(side="left", padx=2, pady=4)

        for ex in exams:
            self._exam_row(inner, ex)

    def _exam_row(self, parent: tk.Widget, exam: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=2)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=8, pady=6)

        tk.Label(inner, text=exam.get("_course_code", ""),
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.ACCENT, width=12, anchor="w").pack(side="left", padx=2)
        tk.Label(inner, text=exam.get("title", ""),
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_PRIMARY, width=28, anchor="w").pack(
            side="left", padx=2)
        tm = exam.get("total_marks") or "\u2014"
        tk.Label(inner, text=str(tm), font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                 width=8, anchor="w").pack(side="left", padx=2)
        active = "Active" if exam.get("is_active") else "Inactive"
        a_clr = theme.SUCCESS if exam.get("is_active") else theme.TEXT_SECONDARY
        tk.Label(inner, text=active, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=a_clr,
                 width=8, anchor="w").pack(side="left", padx=2)

        eid = exam.get("id")
        tk.Button(inner, text="Review Sessions",
                  font=("Segoe UI", 9, "bold"),
                  bg=theme.ACCENT, fg="#FFFFFF",
                  activebackground=theme.ACCENT_HOVER,
                  activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0,
                  padx=8, pady=2,
                  command=lambda: self.dashboard._router.show(
                      "teacher_sessions_list", exam_id=eid)).pack(
            side="left", padx=2)


# ===================================================================
# My Courses sub-view
# ===================================================================

class _MyCoursesView(_SubViewBase):
    def __init__(self, parent: tk.Widget,
                 dashboard: TeacherDashboardScreen) -> None:
        super().__init__(parent, dashboard, "My Courses")
        self._all_courses: List[dict] = []
        self._search_var = tk.StringVar()

        # Toolbar: search + new course button
        toolbar = tk.Frame(self.body, bg=theme.BG_PRIMARY)
        toolbar.pack(fill="x", pady=(0, 10))

        search_entry = tk.Entry(
            toolbar, textvariable=self._search_var,
            font=theme.FONT_BODY, bg=theme.BG_INPUT,
            fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
            relief="flat", bd=0, width=30,
        )
        search_entry.pack(side="left", ipady=6, padx=(0, 8))
        search_entry.insert(0, "")
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        tk.Button(
            toolbar, text="+ New Course", font=("Segoe UI", 10, "bold"),
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0, padx=12, pady=4,
            command=self._show_new_course_modal,
        ).pack(side="right")

        # search placeholder
        self._search_placeholder = tk.Label(
            toolbar, text="Search courses\u2026", font=theme.FONT_BODY,
            bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY, anchor="w",
            cursor="xterm",
        )
        self._search_placeholder.place(in_=search_entry, x=4, rely=0.5,
                                       anchor="w")
        self._search_placeholder.bind(
            "<Button-1>", lambda _e: search_entry.focus_set())

        def _toggle_ph(*_a):
            if self._search_var.get():
                self._search_placeholder.place_forget()
            else:
                self._search_placeholder.place(in_=search_entry, x=4,
                                               rely=0.5, anchor="w")
        self._search_var.trace_add("write", _toggle_ph)
        search_entry.bind("<FocusIn>",
                          lambda _e: self._search_placeholder.place_forget())
        search_entry.bind("<FocusOut>", _toggle_ph)

        self._list_frame = tk.Frame(self.body, bg=theme.BG_PRIMARY)
        self._list_frame.pack(fill="both", expand=True)

        cached = self.cache.get("teacher_courses")
        if cached is not None:
            self._all_courses = cached
            self._render_list(cached)
        else:
            self._show_list_loading()
            self._fetch()

    def _on_refresh(self) -> None:
        self.cache.pop("teacher_courses", None)
        self._clear_list()
        self._show_list_loading()
        self._fetch()

    def _fetch(self) -> None:
        self._bg_fetch(
            lambda: self.api.get("/courses/me?page_size=100"),
            self._on_ok,
            self._show_error,
        )

    def _on_ok(self, payload: dict) -> None:
        items = payload.get("items", [])
        self._all_courses = items
        self.cache["teacher_courses"] = items
        self._clear_list()
        self._render_list(items)

    def _clear_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

    def _show_list_loading(self) -> None:
        tk.Label(self._list_frame, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=40)

    def _apply_filter(self) -> None:
        q = self._search_var.get().strip().lower()
        if not q:
            filtered = self._all_courses
        else:
            filtered = [
                c for c in self._all_courses
                if q in c.get("code", "").lower()
                or q in c.get("title", "").lower()
            ]
        self._clear_list()
        self._render_list(filtered)

    def _render_list(self, items: List[dict]) -> None:
        if not items:
            tk.Label(
                self._list_frame,
                text="No courses found.",
                font=theme.FONT_BODY,
                bg=theme.BG_PRIMARY,
                fg=theme.TEXT_SECONDARY,
            ).pack(pady=60)
            return

        _canvas, scrollable = _make_scrollable(self._list_frame)
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

        meta = tk.Frame(inner, bg=theme.BG_SECONDARY)
        meta.pack(anchor="w")
        ec = course.get("enrollment_count", 0) or 0
        xc = course.get("exam_count", 0) or 0
        tk.Label(meta, text=f"{ec} students", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 16))
        tk.Label(meta, text=f"{xc} exams", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
            side="left")

        def _click(_e, c=course):
            self._show_detail(c)
        for w in (card, inner, *inner.winfo_children(), meta,
                  *meta.winfo_children()):
            w.bind("<Button-1>", _click)

    # ---- course detail ----

    def _show_detail(self, course: dict) -> None:
        self._clear_body()
        _CourseDetailMini(self.body, self, course).pack(
            fill="both", expand=True)

    # ---- new course modal ----

    def _show_new_course_modal(self) -> None:
        _NewCourseModal(self, self.api, self.root, self._on_course_created)

    def _on_course_created(self, course: dict) -> None:
        self._all_courses.append(course)
        self.cache["teacher_courses"] = self._all_courses
        self._clear_list()
        self._render_list(self._all_courses)


# ===================================================================
# New Course Modal (inline overlay)
# ===================================================================

class _NewCourseModal(tk.Toplevel):
    def __init__(self, parent: tk.Widget, api, root: tk.Tk,
                 on_created: Callable) -> None:
        super().__init__(parent)
        self._api = api
        self._root = root
        self._on_created = on_created

        self.title("New Course")
        self.configure(bg=theme.BG_SECONDARY)
        self.resizable(False, False)
        self.geometry("420x340")
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        # --- Pack buttons at BOTTOM first (Tk gives bottom priority) ---
        btns = tk.Frame(self, bg=theme.BG_SECONDARY)
        btns.pack(side="bottom", fill="x", padx=20, pady=(0, 16))

        tk.Button(btns, text="Cancel", font=theme.FONT_BODY,
                  bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY,
                  relief="flat", cursor="hand2", bd=0, padx=14, pady=6,
                  command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Create Course", font=("Segoe UI", 11, "bold"),
                  bg=theme.ACCENT, fg="#FFFFFF",
                  activebackground=theme.ACCENT_HOVER,
                  activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0, padx=16, pady=6,
                  command=self._submit).pack(side="right")

        self._msg = tk.Label(self, text="", font=theme.FONT_SMALL,
                             bg=theme.BG_SECONDARY, fg=theme.ERROR)
        self._msg.pack(side="bottom", fill="x", padx=20, pady=(8, 4))

        # --- Form fields ---
        pad = {"padx": 20, "pady": (16, 0)}
        tk.Label(self, text="Create New Course", font=theme.FONT_SUBHEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(**pad)

        tk.Label(self, text="Course Code", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                 anchor="w").pack(fill="x", padx=20, pady=(16, 2))
        self._code_var = tk.StringVar()
        tk.Entry(self, textvariable=self._code_var, font=theme.FONT_BODY,
                 bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
                 insertbackground=theme.TEXT_PRIMARY,
                 relief="flat", bd=0).pack(fill="x", padx=20, ipady=6)

        tk.Label(self, text="Title", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                 anchor="w").pack(fill="x", padx=20, pady=(12, 2))
        self._title_var = tk.StringVar()
        tk.Entry(self, textvariable=self._title_var, font=theme.FONT_BODY,
                 bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY,
                 insertbackground=theme.TEXT_PRIMARY,
                 relief="flat", bd=0).pack(fill="x", padx=20, ipady=6)

    def _submit(self) -> None:
        code = self._code_var.get().strip()
        title = self._title_var.get().strip()
        if not code or not title:
            self._msg.configure(text="Both fields are required.")
            return
        self._msg.configure(text="Creating\u2026", fg=theme.TEXT_SECONDARY)

        def _work():
            ok, payload, err = self._api.post(
                "/courses", body={"code": code, "title": title})
            if ok:
                self._root.after(0, lambda: self._done(payload))
            else:
                msg = err.message if err else "Failed to create course."
                self._root.after(
                    0, lambda: self._msg.configure(text=msg, fg=theme.ERROR))
        threading.Thread(target=_work, daemon=True).start()

    def _done(self, course: dict) -> None:
        self._on_created(course)
        self.destroy()


# ===================================================================
# Course Detail Mini-view (in-place)
# ===================================================================

class _CourseDetailMini(tk.Frame):
    """In-place detail with Students / Exams tabs."""

    def __init__(self, parent: tk.Widget, courses_view: _MyCoursesView,
                 course: dict) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._cv = courses_view
        self._api = courses_view.api
        self._root = courses_view.root
        self._course = course
        self._course_id = course.get("id")
        self._active_tab: Optional[str] = None
        self._tab_buttons: Dict[str, tk.Label] = {}

        # header
        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", pady=(0, 6))
        back = tk.Label(hdr, text="\u2190 Back", font=theme.FONT_BODY,
                        bg=theme.BG_PRIMARY, fg=theme.ACCENT, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda _e: self._go_back())
        tk.Label(
            hdr,
            text=f"{course.get('code', '')} \u2014 {course.get('title', '')}",
            font=theme.FONT_SUBHEADING, bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
        ).pack(side="left", padx=12)

        # tabs
        tab_bar = tk.Frame(self, bg=theme.BG_PRIMARY)
        tab_bar.pack(fill="x", pady=(0, 8))
        for t in ("Students", "Exams"):
            lbl = tk.Label(tab_bar, text=t, font=theme.FONT_BODY,
                           bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
                           padx=16, pady=4, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _e, n=t: self._select_tab(n))
            self._tab_buttons[t] = lbl

        tk.Frame(self, bg=theme.BORDER, height=1).pack(fill="x")

        self._tab_body = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._tab_body.pack(fill="both", expand=True, pady=(8, 0))

        self._select_tab("Students")

    def _select_tab(self, name: str) -> None:
        if name == self._active_tab:
            return
        self._active_tab = name
        for n, btn in self._tab_buttons.items():
            if n == name:
                btn.configure(fg=theme.ACCENT,
                              font=("Segoe UI", 12, "bold"))
            else:
                btn.configure(fg=theme.TEXT_SECONDARY,
                              font=theme.FONT_BODY)
        for w in self._tab_body.winfo_children():
            w.destroy()

        if name == "Students":
            _StudentsTab(self._tab_body, self).pack(fill="both", expand=True)
        else:
            _ExamsTab(self._tab_body, self).pack(fill="both", expand=True)

    def _go_back(self) -> None:
        self._cv._clear_body()
        self._cv._clear_list()
        self._cv._render_list(self._cv._all_courses)


# ===================================================================
# Students Tab
# ===================================================================

class _StudentsTab(tk.Frame):
    def __init__(self, parent: tk.Widget, detail: _CourseDetailMini) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._detail = detail
        self._api = detail._api
        self._root = detail._root
        self._course_id = detail._course_id
        self._page = 1

        # Enroll bar
        enroll_bar = tk.Frame(self, bg=theme.BG_PRIMARY)
        enroll_bar.pack(fill="x", pady=(0, 8))
        tk.Label(enroll_bar, text="Enroll Student:", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(
            side="left", padx=(0, 6))
        self._email_var = tk.StringVar()
        tk.Entry(enroll_bar, textvariable=self._email_var,
                 font=theme.FONT_SMALL, bg=theme.BG_INPUT,
                 fg=theme.TEXT_PRIMARY, insertbackground=theme.TEXT_PRIMARY,
                 relief="flat", bd=0, width=28).pack(
            side="left", ipady=4, padx=(0, 6))
        tk.Button(enroll_bar, text="Enroll", font=("Segoe UI", 9, "bold"),
                  bg=theme.ACCENT, fg="#FFFFFF",
                  activebackground=theme.ACCENT_HOVER,
                  activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0, padx=10, pady=2,
                  command=self._enroll).pack(side="left")
        self._enroll_msg = tk.Label(enroll_bar, text="", font=theme.FONT_SMALL,
                                    bg=theme.BG_PRIMARY, fg=theme.ERROR)
        self._enroll_msg.pack(side="left", padx=8)

        self._list_frame = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._list_frame.pack(fill="both", expand=True)

        self._show_loading()
        self._fetch()

    def _show_loading(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        tk.Label(self._list_frame, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=20)

    def _fetch(self) -> None:
        cid = self._course_id
        page = self._page

        def _get():
            return self._api.get(
                f"/courses/{cid}/enrollments?page={page}&page_size=20"
                f"&status=active")

        def _ok(payload):
            for w in self._list_frame.winfo_children():
                w.destroy()
            self._render(payload)

        def _err(msg):
            for w in self._list_frame.winfo_children():
                w.destroy()
            tk.Label(self._list_frame, text=msg, font=theme.FONT_BODY,
                     bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=20)

        def _work():
            ok, payload, err = _get()
            if ok:
                self._root.after(0, lambda: _ok(payload))
            else:
                m = err.message if err else "Failed to load students."
                self._root.after(0, lambda: _err(m))
        threading.Thread(target=_work, daemon=True).start()

    def _render(self, payload: dict) -> None:
        items = payload.get("items", [])
        pagination = payload.get("pagination", {})

        if not items:
            tk.Label(self._list_frame, text="No students enrolled yet.",
                     font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(pady=20)
            return

        _canvas, scrollable = _make_scrollable(self._list_frame)

        # Header
        hdr = tk.Frame(scrollable, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in (("Name", 20), ("Roll #", 14), ("Dept", 14),
                       ("Sem", 5), ("", 8)):
            tk.Label(hdr, text=txt, font=theme.FONT_SMALL,
                     bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
                     width=w, anchor="w").pack(side="left")

        for e in items:
            self._row(scrollable, e)

        # Pagination
        total_pages = pagination.get("total_pages", 1)
        if total_pages > 1:
            pf = tk.Frame(scrollable, bg=theme.BG_PRIMARY)
            pf.pack(fill="x", pady=8)
            if self._page > 1:
                tk.Button(pf, text="\u2190 Prev", font=theme.FONT_SMALL,
                          bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                          relief="flat", cursor="hand2",
                          command=lambda: self._go_page(-1)).pack(side="left")
            tk.Label(pf, text=f"Page {self._page}/{total_pages}",
                     font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(side="left", padx=8)
            if self._page < total_pages:
                tk.Button(pf, text="Next \u2192", font=theme.FONT_SMALL,
                          bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                          relief="flat", cursor="hand2",
                          command=lambda: self._go_page(1)).pack(side="left")

    def _row(self, parent: tk.Widget, enrollment: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=2)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=8, pady=6)

        tk.Label(inner, text=enrollment.get("student_full_name", ""),
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_PRIMARY, width=20,
                 anchor="w").pack(side="left")
        tk.Label(inner, text=enrollment.get("student_roll_number", ""),
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY, width=14,
                 anchor="w").pack(side="left")
        tk.Label(inner, text=enrollment.get("student_department_name", "\u2014") or "\u2014",
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY, width=14,
                 anchor="w").pack(side="left")
        sem = enrollment.get("student_semester")
        tk.Label(inner, text=str(sem) if sem else "\u2014",
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY, width=5,
                 anchor="w").pack(side="left")

        eid = enrollment.get("id")
        tk.Button(inner, text="Remove", font=("Segoe UI", 9),
                  bg=theme.ERROR, fg="#FFFFFF",
                  activebackground="#FF6B6B", activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0, padx=8, pady=1,
                  command=lambda: self._remove(eid)).pack(side="left")

    def _remove(self, enrollment_id: int) -> None:
        cid = self._course_id

        def _work():
            ok, _, err = self._api.delete(
                f"/courses/{cid}/enrollments/{enrollment_id}")
            if ok:
                self._root.after(0, self._refresh)
            else:
                msg = err.message if err else "Failed to remove."
                self._root.after(
                    0, lambda: self._enroll_msg.configure(
                        text=msg, fg=theme.ERROR))
        threading.Thread(target=_work, daemon=True).start()

    def _enroll(self) -> None:
        email = self._email_var.get().strip()
        if not email:
            self._enroll_msg.configure(text="Enter a student email.",
                                       fg=theme.ERROR)
            return
        self._enroll_msg.configure(text="Enrolling\u2026",
                                   fg=theme.TEXT_SECONDARY)
        cid = self._course_id

        def _work():
            ok, payload, err = self._api.post(
                f"/courses/{cid}/enrollments",
                body={"student_email": email})
            if ok:
                self._root.after(0, lambda: self._enroll_ok())
            else:
                msg = err.message if err else "Failed to enroll."
                self._root.after(
                    0, lambda: self._enroll_msg.configure(
                        text=msg, fg=theme.ERROR))
        threading.Thread(target=_work, daemon=True).start()

    def _enroll_ok(self) -> None:
        self._email_var.set("")
        self._enroll_msg.configure(text="Enrolled!", fg=theme.SUCCESS)
        self._refresh()

    def _refresh(self) -> None:
        self._show_loading()
        self._fetch()

    def _go_page(self, delta: int) -> None:
        self._page += delta
        self._show_loading()
        self._fetch()


# ===================================================================
# Exams Tab
# ===================================================================

class _ExamsTab(tk.Frame):
    def __init__(self, parent: tk.Widget, detail: _CourseDetailMini) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._detail = detail
        self._api = detail._api
        self._root = detail._root
        self._course_id = detail._course_id
        self._dashboard = detail._cv.dashboard

        # Create Exam button
        top = tk.Frame(self, bg=theme.BG_PRIMARY)
        top.pack(fill="x", pady=(0, 8))
        tk.Button(
            top, text="+ Create Exam", font=("Segoe UI", 10, "bold"),
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0, padx=12, pady=4,
            command=self._create_exam,
        ).pack(side="right")

        self._list_frame = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._list_frame.pack(fill="both", expand=True)

        self._show_loading()
        self._fetch()

    def _show_loading(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        tk.Label(self._list_frame, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=20)

    def _fetch(self) -> None:
        cid = self._course_id

        def _work():
            ok, payload, err = self._api.get(
                f"/courses/{cid}/exams?page_size=100")
            if ok:
                items = payload.get("items", [])
                self._root.after(0, lambda: self._render(items))
            else:
                msg = err.message if err else "Failed to load exams."
                self._root.after(0, lambda: self._show_err(msg))
        threading.Thread(target=_work, daemon=True).start()

    def _show_err(self, msg: str) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        tk.Label(self._list_frame, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=20)

    def _render(self, items: list) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not items:
            tk.Label(self._list_frame, text="No exams in this course yet.",
                     font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(pady=20)
            return

        _canvas, scrollable = _make_scrollable(self._list_frame)
        for ex in items:
            self._exam_row(scrollable, ex)

    def _exam_row(self, parent: tk.Widget, exam: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=3)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=12, pady=8)

        left = tk.Frame(inner, bg=theme.BG_SECONDARY)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text=exam.get("title", ""), font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
            anchor="w")

        meta = tk.Frame(left, bg=theme.BG_SECONDARY)
        meta.pack(anchor="w")
        qc = exam.get("question_count", 0) or 0
        tm = exam.get("total_marks") or "\u2014"
        dur = exam.get("duration_minutes", 0) or 0
        tk.Label(meta, text=f"{qc} questions",
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY).pack(side="left", padx=(0, 12))
        tk.Label(meta, text=f"Marks: {tm}",
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY).pack(side="left", padx=(0, 12))
        tk.Label(meta, text=f"{dur} min",
                 font=theme.FONT_SMALL, bg=theme.BG_SECONDARY,
                 fg=theme.TEXT_SECONDARY).pack(side="left")

        right = tk.Frame(inner, bg=theme.BG_SECONDARY)
        right.pack(side="right")

        # Active toggle
        is_active = exam.get("is_active", False)
        toggle_text = "Deactivate" if is_active else "Activate"
        toggle_bg = theme.WARNING if is_active else theme.SUCCESS
        active_lbl = "Active" if is_active else "Inactive"
        active_clr = theme.SUCCESS if is_active else theme.TEXT_SECONDARY

        tk.Label(right, text=active_lbl, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=active_clr).pack(pady=(0, 2))

        btn_row = tk.Frame(right, bg=theme.BG_SECONDARY)
        btn_row.pack()

        eid = exam.get("id")

        tk.Button(btn_row, text=toggle_text, font=("Segoe UI", 9),
                  bg=toggle_bg, fg="#FFFFFF",
                  activebackground=toggle_bg, activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0, padx=6, pady=1,
                  command=lambda: self._toggle(eid, is_active)).pack(
            side="left", padx=2)

        tk.Button(btn_row, text="Edit", font=("Segoe UI", 9),
                  bg=theme.ACCENT, fg="#FFFFFF",
                  activebackground=theme.ACCENT_HOVER,
                  activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", bd=0, padx=6, pady=1,
                  command=lambda: self._edit_exam(eid)).pack(
            side="left", padx=2)

        tk.Button(btn_row, text="Sessions", font=("Segoe UI", 9),
                  bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY,
                  activebackground=theme.BORDER,
                  activeforeground=theme.TEXT_PRIMARY,
                  relief="flat", cursor="hand2", bd=0, padx=6, pady=1,
                  command=lambda: self._review_sessions(eid)).pack(
            side="left", padx=2)

    def _toggle(self, exam_id: int, currently_active: bool) -> None:
        action = "deactivate" if currently_active else "activate"

        def _work():
            ok, _, err = self._api.post(f"/exams/{exam_id}/{action}")
            if ok:
                self._root.after(0, self._refresh)
            else:
                msg = err.message if err else f"Failed to {action}."
                self._root.after(0, lambda: self._show_err(msg))
        threading.Thread(target=_work, daemon=True).start()

    def _refresh(self) -> None:
        self._show_loading()
        self._fetch()

    def _create_exam(self) -> None:
        self._dashboard._router.show(
            "exam_creation", course_id=self._course_id)

    def _edit_exam(self, exam_id: int) -> None:
        self._dashboard._router.show(
            "exam_creation", course_id=self._course_id, exam_id=exam_id)

    def _review_sessions(self, exam_id: int) -> None:
        self._dashboard._router.show(
            "teacher_sessions_list", exam_id=exam_id)
