# ExamSentinel

A secure online examination system that enforces exam integrity at the operating system level through native Windows lockdown mechanisms and hardware-level virtual machine detection.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [System Architecture](#system-architecture)
- [OS Lockdown System](#os-lockdown-system)
- [VM Detection](#vm-detection)
  - [Standard Detection](#standard-vm-detection)
  - [Stealth Detection](#stealth-vm-detection)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Local Development Setup](#local-development-setup)
  - [Server Setup](#server-setup)
  - [Client Setup](#client-setup)
  - [Building the Executable](#building-the-executable)
- [Deployment](#deployment)
- [Seed Data](#seed-data)
- [About](#about)

---

## Problem Statement

Online examinations have become widespread in academic institutions, but existing proctoring solutions operate at the browser level and are fundamentally limited. A browser cannot control what happens outside its window. Students can bypass browser-based proctoring by:

- Alt-tabbing to search engines or reference material during the exam
- Using screen-sharing or remote desktop tools (TeamViewer, AnyDesk) to receive external help
- Running screen recording software (OBS, Camtasia) to capture and share questions
- Copying answers from the clipboard
- Connecting a second monitor to view notes while the exam is on the primary screen
- Running the entire exam inside a Virtual Machine, rendering all browser-based monitoring useless since the VM appears as a clean environment while the host OS provides unrestricted access

There is no way for a web application to prevent these actions. The operating system must be involved.

---

## Solution Overview

ExamSentinel is a native Windows desktop application that operates with administrator privileges to directly control the testing environment during an exam. The system consists of two components:

**Desktop Client** — A Python/Tkinter application compiled into a standalone Windows executable. It performs pre-exam VM detection, enforces OS-level lockdown during the exam, and reports all violations to the server in real-time.

**Backend Server** — A Flask REST API with PostgreSQL that handles authentication, course/exam management, session lifecycle, answer grading, and incident storage. Teachers use the client application to create exams and review student sessions with full incident timelines.

The exam flow is:
1. Teacher creates a course, enrolls students, and authors an MCQ exam
2. Teacher activates the exam when ready
3. Student launches ExamSentinel, logs in, and starts the exam
4. Pre-exam integrity check runs (Standard VM Detection + Stealth VM Detection)
5. If the machine passes, the session transitions to in_progress and lockdown engages
6. Student answers questions under full OS lockdown — all violations are logged
7. Student submits the exam — lockdown disengages
8. Teacher reviews each student's session, score, and incident timeline

---

## System Architecture

```
+---------------------+          HTTPS           +-------------------+
|                     |  <-------------------->  |                   |
|  Windows Client     |                          |  Flask Server     |
|  (ExamSentinel.exe) |                          |  (Railway)        |
|                     |                          |                   |
|  - Tkinter GUI      |   POST /auth/login       |  - REST API       |
|  - VM Detection     |   GET  /exams            |  - SQLAlchemy ORM |
|  - OS Lockdown      |   POST /sessions         |  - JWT Auth       |
|  - Incident Report  |   POST /sessions/submit  |  - Auto-grading   |
|                     |   POST /incidents        |                   |
+---------------------+                          +--------+----------+
                                                          |
                                                          v
                                                 +--------+----------+
                                                 |                   |
                                                 |  PostgreSQL       |
                                                 |  (Railway)        |
                                                 |                   |
                                                 +-------------------+
```

---

## OS Lockdown System

When a student begins an exam, ExamSentinel activates a multi-layered lockdown. Each subsystem runs on its own daemon thread and reports violations to the server with timestamps.

| Subsystem | What it does | Incident Type |
|-----------|-------------|---------------|
| Fullscreen Enforcement | Forces exam window to remain fullscreen; reverts any resize/minimize | FULLSCREEN_BREACH |
| Focus Monitor | Detects when another window gains focus; logs the window title | FOCUS_LOST |
| Keyboard Hook | Low-level hook that blocks Win, Alt+Tab, Alt+F4, PrintScreen, Ctrl+Alt+Del, snipping shortcuts | KEYBOARD_BLOCKED |
| Mouse Boundary | Detects cursor movement outside exam window bounds | MOUSE_ESCAPE |
| Clipboard Scrubber | Periodically checks and wipes clipboard contents; logs the format type | CLIPBOARD_SCRUB |
| Process Killer | Scans running processes against a blacklist (OBS, TeamViewer, AnyDesk, Discord, Zoom, etc.); force-terminates matches | BLACKLISTED_PROCESS_KILLED |
| Right-Click Suppression | Blocks context menu in exam window | RIGHT_CLICK_BLOCKED |
| Multi-Monitor Detection | Detects secondary displays; aborts the exam session immediately | MULTI_MONITOR_DETECTED |

All incidents include a timestamp, severity level (info/warning/critical), description, and forensic metadata. Teachers see the complete timeline when reviewing a student's session.

---

## VM Detection

### Standard VM Detection

Runs before the exam begins. Checks for obvious virtualization indicators present on default VM installations:

**1. Process Scanning** — Checks running processes against known VM guest tool names: VBoxService.exe, VBoxTray.exe (VirtualBox), vmtoolsd.exe, vmwaretray.exe (VMware), vmcompute.exe (Hyper-V), qemu-ga.exe (QEMU).

**2. Registry Key Detection** — Scans HKLM for VM-specific keys: Oracle\VirtualBox Guest Additions, VMware Inc.\VMware Tools, ControlSet001\Services\VBoxGuest, VBoxMouse, VBoxSF, VBoxVideo.

**3. WMI Hardware Strings** — Queries Win32_ComputerSystem and Win32_BIOS for manufacturer/model strings containing "virtualbox", "vmware", "innotek", "qemu", "microsoft corporation".

**4. MAC Address OUI** — Checks network adapter MAC prefixes against known VM vendor ranges: 08:00:27 (VirtualBox), 00:0C:29 (VMware), 00:15:5D (Hyper-V), 52:54:00 (QEMU).

**Limitation:** All four methods can be bypassed by removing guest additions, spoofing registry keys, changing MAC addresses via VBoxManage, and modifying WMI strings. This is where Stealth Detection becomes essential.

### Stealth VM Detection

Uses hardware-level signals that cannot be faked from user-mode, even after all guest tools are removed and system identifiers are spoofed:

**1. RDTSC Timing (CPU Trap Latency)** — The most reliable method. Measures the CPU cycle cost of executing a CPUID instruction using RDTSC (Read Time-Stamp Counter). On bare metal, CPUID takes 50-150 cycles. On any hypervisor, CPUID causes a mandatory VM-exit trap that adds 3,000-50,000+ cycles of overhead. This is an architectural property of x86 virtualization that no configuration command can eliminate. ExamSentinel injects x86-64 shellcode into executable memory, runs 200 iterations, takes the median, and compares against a threshold of 2,500 cycles.

**2. Thermal Zone Absence** — Every physical PC has at least one thermal sensor exposed through the WMI MSAcpi_ThermalZoneTemperature class. These sensors report CPU/motherboard temperature readings that fluctuate naturally. Virtual machines have no physical hardware, so they either report zero thermal zones or return a constant stub value (exactly 26.85C / 300K).

**3. SCSI Disk Identifier** — Virtual disk controllers report identifiers like "VBOX HARDDISK" or "VMware Virtual disk" in the registry under HARDWARE\DEVICEMAP\Scsi. These come from the virtual storage controller firmware, not from installed tools. Removing Guest Additions, spoofing BIOS strings, or changing MAC addresses does not affect this identifier.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Client GUI | Python 3.11, Tkinter |
| OS Integration | ctypes, pywin32, psutil, WMI |
| Client Packaging | PyInstaller (single .exe) |
| Server Framework | Flask 3.1, Flask-SQLAlchemy, Flask-JWT-Extended |
| Database | PostgreSQL (Railway managed) |
| ORM / Migrations | SQLAlchemy 2.0, Alembic (Flask-Migrate) |
| Authentication | JWT (access tokens) |
| Deployment | Railway (server + DB), Gunicorn |
| Python Version | 3.11.11 |

---

## Project Structure

```
ExamSentinel/
├── client/
│   ├── app/
│   │   ├── lockdown/          # OS lockdown subsystems
│   │   │   ├── manager.py     # Orchestrates all subsystems
│   │   │   ├── fullscreen.py
│   │   │   ├── focus_monitor.py
│   │   │   ├── keyboard.py
│   │   │   ├── mouse_boundary.py
│   │   │   ├── clipboard_scrub.py
│   │   │   ├── process_kill.py
│   │   │   ├── right_click_suppress.py
│   │   │   └── multi_monitor.py
│   │   ├── vm_detect/         # VM detection modules
│   │   │   ├── standard.py    # Process, registry, WMI, MAC checks
│   │   │   └── stealth.py     # RDTSC timing, thermal, SCSI checks
│   │   ├── screens/           # Tkinter GUI screens
│   │   ├── services/          # API client, router, session manager
│   │   ├── ui/                # Theme, widgets, styling
│   │   └── main.py            # Application entry point
│   ├── build/
│   │   ├── ExamSentinel.spec  # PyInstaller spec file
│   │   ├── icon.ico           # Application icon
│   │   └── dist/              # Built executable output
│   ├── requirements.txt
│   └── .env.example
├── server/
│   ├── app/
│   │   ├── models/            # SQLAlchemy models (User, Student, Teacher, Course, Exam, etc.)
│   │   ├── routes/            # Flask blueprints (auth, courses, exams, sessions, incidents)
│   │   ├── services/          # Business logic layer
│   │   ├── schemas/           # Marshmallow serialization schemas
│   │   └── extensions.py      # Flask extensions (db, jwt, migrate)
│   ├── migrations/            # Alembic database migrations
│   ├── seed/                  # Seed data scripts
│   ├── wsgi.py                # WSGI entry point
│   └── .env.example
├── requirements.txt           # Server dependencies (used by Railway)
├── Procfile                   # Railway process definitions
├── runtime.txt                # Python version for Railway
└── README.md
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (local instance or use the Railway DB directly)
- Windows 10/11 (client requires Windows APIs)
- Git

### Server Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/inam0ul0haq/ExamSentinel.git
   cd ExamSentinel
   ```

2. Create a virtual environment for the server:
   ```bash
   cd server
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install server dependencies:
   ```bash
   pip install -r ../requirements.txt
   ```

4. Configure environment variables:
   ```bash
   copy .env.example .env
   ```
   Edit `server/.env` and set:
   - `DATABASE_URL` — Your PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5432/examsentinel`)
   - `SECRET_KEY` — Random 64-character hex string
   - `JWT_SECRET_KEY` — Another random string for JWT signing
   - `SEED_TOKEN` — Token for the seed endpoint (any random string)

5. Run database migrations:
   ```bash
   flask --app wsgi db upgrade
   ```

6. Start the development server:
   ```bash
   python run_dev.py
   ```
   Server runs at `http://127.0.0.1:5000`

### Client Setup

1. Open a new terminal and navigate to the client:
   ```bash
   cd client
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install client dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   copy .env.example .env
   ```
   Edit `client/.env` and set:
   - `API_BASE_URL=http://127.0.0.1:5000/api/v1` (for local server)
   - Optionally set `SKIP_LOCKDOWN=1` during development to disable OS lockdown
   - Optionally set `SKIP_VM_CHECK=1` to bypass VM detection during development

4. Run the client in development mode:
   ```bash
   python -m client.app.main
   ```

### Building the Executable

To build the standalone .exe:

```bash
cd client\build
pip install pyinstaller Pillow
python gen_icon.py          # generates icon.ico (only needed once)
pyinstaller --clean ExamSentinel.spec --distpath dist --workpath build
```

The output will be at `client/build/dist/ExamSentinel.exe`.

---

## Deployment

The server is deployed on Railway with the following configuration:

- **Web Service:** Gunicorn serves the Flask app (defined in `Procfile`)
- **Database:** Railway-managed PostgreSQL
- **Release Command:** Runs `flask db upgrade` on each deploy to apply migrations automatically
- **Runtime:** Python 3.11.11 (defined in `runtime.txt`)

Environment variables on Railway:
- `DATABASE_URL` — Injected automatically by Railway PostgreSQL plugin
- `SECRET_KEY`, `JWT_SECRET_KEY` — Set manually in Railway dashboard
- `SEED_TOKEN` — For seeding data via the API
- `FLASK_ENV=production`

The client connects to the Railway-hosted server by default (configured in `client/.env`).

---

## Seed Data

For demonstration, the database is seeded with:

- **5 Teachers** — Nadeem Akhtar, Waqar Ul Qonain, Asif Sohail, Muhammad Farooq, Ahmad Ghazali
- **10 Courses** — 2 per teacher (SQA, SE, DSA, OOP, DB, Web Engineering, CN, OS, AI, ML)
- **20 Students** — Roll numbers bitf22m001 through bitf22m020
- **10 Exams** — 1 per course, 5 MCQ questions each, 25 marks total
- **80 Enrollments** — Each student enrolled with 2 teachers (4 courses)

**Login credentials for all accounts:**
- Email: `nadeem.akhtar@pucit.edu.pk` (teacher) or `bitf22m001@pucit.edu.pk` (student)
- Password: `pucit`

Teachers must activate an exam from the GUI before students can see and attempt it.

---

## About

**ExamSentinel** is a Final Year Project developed at the **Punjab University College of Information Technology (PUCIT)**, University of the Punjab, Lahore.

**Developer:** Inam Ul Haq (BITF22M017)

**Supervisor:** Department of Information Technology, PUCIT

---
