"""
ExamSentinel — client entry point.

Creates the root Tk window, instantiates core services, registers all
screens, and navigates to the splash screen.

Run with:  python -m client.app.main
"""

from __future__ import annotations

import tkinter as tk

from client.app.ui import theme
from client.app.services.api_client import ApiClient
from client.app.services.session_state import SessionState
from client.app.services.router import Router

# Screen imports
from client.app.screens.splash import SplashScreen
from client.app.screens.login import LoginScreen
from client.app.screens.register import RegisterScreen
from client.app.screens.teacher_dashboard import TeacherDashboardScreen
from client.app.screens.student_dashboard import StudentDashboardScreen
from client.app.screens.exam_integrity_check import ExamIntegrityCheckScreen
from client.app.screens.exam_taking import ExamTakingScreen
from client.app.screens.exam_editor import ExamCreationScreen
from client.app.screens.teacher_review import TeacherReviewScreen
from client.app.screens.teacher_sessions_list import TeacherSessionsListScreen
from client.app.screens.teacher_session_detail import TeacherSessionDetailScreen


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "ExamSentinel"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720


def _centre_window(root: tk.Tk, w: int, h: int) -> None:
    """Position *root* at the centre of the primary monitor."""
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - w) // 2
    y = (screen_h - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")


def main() -> None:
    root = tk.Tk()
    root.title(APP_TITLE)
    root.configure(bg=theme.BG_PRIMARY)
    root.resizable(False, False)
    _centre_window(root, WINDOW_WIDTH, WINDOW_HEIGHT)

    # --- core services (accessible from screens via router / app) ----------
    api_client = ApiClient()
    session_state = SessionState()

    # Wire logout → clear token
    session_state.on_logout(api_client.clear_token)

    # --- router & screen registration -------------------------------------
    router = Router(root)

    # Attach services to the router so screens can reach them.
    router.api = api_client          # type: ignore[attr-defined]
    router.session = session_state   # type: ignore[attr-defined]

    router.register("splash", SplashScreen)
    router.register("login", LoginScreen)
    router.register("register", RegisterScreen)
    router.register("teacher_dashboard", TeacherDashboardScreen)
    router.register("student_dashboard", StudentDashboardScreen)
    router.register("exam_integrity_check", ExamIntegrityCheckScreen)
    router.register("exam_taking", ExamTakingScreen)
    router.register("exam_creation", ExamCreationScreen)
    router.register("teacher_review", TeacherReviewScreen)
    router.register("teacher_sessions_list", TeacherSessionsListScreen)
    router.register("teacher_session_detail", TeacherSessionDetailScreen)

    # --- navigate to initial screen ----------------------------------------
    router.show("splash", push=False)

    root.mainloop()


if __name__ == "__main__":
    main()
