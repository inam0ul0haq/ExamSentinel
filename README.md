# ExamSentinel

ExamSentinel is a secure online examination system composed of a Flask REST API hosted on Railway with a managed PostgreSQL database and a Tkinter-based Windows desktop client distributed as a single PyInstaller `.exe`. The client enforces pre-exam virtual-machine detection gates and a live OS-level lockdown (keyboard hooks, process killing, clipboard scrubbing, fullscreen takeover, focus monitoring, mouse boundary lock, multi-monitor block) while the server manages users, courses, exams, sessions, answers, and a forensic incident log — together raising the cost of cheating and producing a defensible evidence trail for teacher review.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system specification.
