# Poster Generation Prompt — ExamSentinel Capstone Project

Use the following prompt with GPT-4o / Gemini / any AI image or design tool to generate a 2×5 ft academic capstone poster.

---

## PROMPT (copy this entire block):

---

Design a professional academic capstone project poster (2 feet wide × 5 feet tall, portrait orientation, 7200 × 18000 pixels at 300 DPI) for a Final Year Project titled **"ExamSentinel: A Secure Desktop Examination System with OS-Level Anti-Cheating"**.

**REFERENCE STYLE**: Use the attached example poster (SCOUT - AI-powered Lead Generation) as a style reference. Match its clean white background, rounded card sections, colorful tech-stack icons at the bottom, bold project title at the top, and the PUCIT logo placement in the footer. Make it similarly modern, visually appealing, and easy to scan.

### VISUAL STYLE:
- **White/light background** with blue (#4E7AFF) and navy (#0A0E1A) accents — clean and printable
- Rounded-corner card sections for each content block (like the reference poster)
- Clean sans-serif fonts (Inter, Segoe UI, or similar)
- Include subtle tech-inspired geometric patterns or light blue gradient overlay at the top
- A shield/lock icon or a stylized sentinel mascot as the project visual near the top
- Professional spacing, clear visual hierarchy, easy to read from 3 feet away
- Color palette: white bg, navy headings, blue accents, dark gray body text

### LAYOUT (top to bottom):

#### 1. HEADER (top ~10%)
- **Project title (very large, bold, top-left):** ExamSentinel
- Subtitle below: "A Secure Desktop Examination System with OS-Level Anti-Cheating"
- Tagline: "Detect. Lock. Monitor. Report."
- A relevant hero visual on the right (shield with lock, or a secure exam illustration)

#### 2. FOOTER (bottom strip):
- Bottom-left: **Inam Ul Haq** (BITF22M017)
- Bottom-right: **PUCIT** logo (Punjab University College of Information Technology) / FCIT (Faculty of Computing & Information Technology), University of the Punjab, Lahore
- Bottom-right below logo: **Supervisor:** Dr. Nadeem Akhtar
- Include the official PUCIT crest/logo (blue and white university seal)

#### 2. PROBLEM STATEMENT (~10%)
- Heading: "The Problem"
- Content: Online examinations are plagued by cheating through virtual machines, screen sharing, application switching, copy-paste, and unauthorized browser usage. Existing solutions rely on browser-based proctoring which is easily bypassed. There is no robust desktop-native solution that enforces exam integrity at the operating system level.
- Include a small infographic: icons showing common cheating vectors (VM, Alt+Tab, clipboard, screen capture, dual monitors) with red X marks

#### 3. PROPOSED SOLUTION (~10%)
- Heading: "The Solution"
- Content: ExamSentinel is a standalone Windows desktop application that enforces exam integrity through multi-layered OS-level security. It detects virtual machines, locks down the operating system during exams, and reports all violation incidents to the teacher in real-time.
- Key differentiators in 3 bullet icons:
  • **VM Detection** — Hardware fingerprinting, registry scans, MAC OUI analysis, process detection
  • **OS Lockdown** — 8 subsystems controlling keyboard, processes, clipboard, display, focus, cursor
  • **Incident Pipeline** — Every violation logged with forensic metadata for teacher review

#### 4. SYSTEM ARCHITECTURE (~15%)
- Heading: "System Architecture"
- Include a clean architectural diagram showing:
  - **Desktop Client** (Python/Tkinter): UI Layer, VM Detection Module, OS Lockdown Module, API Client (requests + JWT)
  - Arrow: HTTPS connection
  - **Cloud Server** (Railway): Flask REST API, Service Layer (Auth, Grading, Sessions), SQLAlchemy ORM, PostgreSQL
- Label the tech stack clearly: Python 3.11, Flask, PostgreSQL, PyInstaller, Win32 API

#### 5. SECURITY ENGINE — VM DETECTION (~12%)
- Heading: "VM Detection Engine"
- Show the pre-check workflow as a flowchart:
  - Exam Selected → Session Created (pre_check) → VM Detection Module runs 4 checks:
    1. WMI Hardware Scan (BIOS, motherboard, disk serial)
    2. MAC OUI Lookup (known VM vendor prefixes)
    3. Registry Artifact Scan (VirtualBox/VMware/Hyper-V keys)
    4. System Process Detection (vmtoolsd, VBoxService, etc.)
  - Decision: VM Detected? → YES: Log Incident, Abort Session, Block Exam / NO: Proceed to Lockdown
- Use green checkmark and red X for the two paths

#### 6. SECURITY ENGINE — OS LOCKDOWN (~15%)
- Heading: "OS Lockdown Engine (8 Subsystems)"
- Show a numbered list with icons for each subsystem:
  1. **Multi-Monitor Detection** — Detects hot-plugged displays, triggers immediate abort
  2. **Keyboard Hook** — Low-level WH_KEYBOARD_LL blocks Alt+Tab, Alt+F4, Win key, PrintScreen
  3. **Process Killer** — Terminates 40+ blacklisted apps (browsers, messaging, remote desktop)
  4. **Clipboard Scrub** — Clears clipboard every 500ms
  5. **Right-Click Suppress** — Blocks context menus
  6. **Fullscreen Enforcer** — Borderless fullscreen, hides taskbar, HWND_TOPMOST
  7. **Focus Monitor** — Detects focus loss, yanks back within 500ms
  8. **Mouse Boundary** — ClipCursor confines pointer to exam window
- Note: "Startup order matters. Shutdown in reverse. Fault-tolerant — partial failure doesn't crash the exam."

#### 7. KEY FEATURES (~10%)
- Heading: "Key Features"
- Two columns:
  **Student Side:**
  - Secure login (JWT auth)
  - Active exam browser with enrollment
  - Integrity pre-check before exam starts
  - Auto-save answers every keystroke
  - Timer with auto-submit on expiry
  - Instant result with score breakdown

  **Teacher Side:**
  - Course & exam management
  - MCQ + short-answer question builder
  - Exam activation/deactivation scheduling
  - Student enrollment by email
  - Full incident timeline per session
  - Auto-grading for MCQs

#### 8. INCIDENT REPORTING (~8%)
- Heading: "Incident Forensics"
- Show a sample incident timeline:
  ```
  LOCKDOWN_ENGAGED → BLACKLISTED_PROCESS_KILLED (msedge.exe) → CLIPBOARD_SCRUB → FOCUS_LOST (chrome.exe) → KEYBOARD_BLOCKED (Alt+Tab) → LOCKDOWN_DISENGAGED
  ```
- Note: "Every violation is timestamped, categorized by severity (info/warning/critical), and stored server-side for teacher review."

#### 9. TECH STACK & DEPLOYMENT (~6%)
- Heading: "Technology Stack"
- Visual tech badges/icons in a row:
  - Python 3.11 | Flask | PostgreSQL | Tkinter | Win32 API | PyInstaller | Railway | JWT
- Deployment note: "Single .exe (16 MB), no Python install required. Runs on any Windows 10/11 machine. Server deployed on Railway with PostgreSQL."

#### 10. RESULTS & CONCLUSION (~6%)
- Heading: "Results"
- Bullet points:
  - Successfully blocks all common cheating vectors at OS level
  - VM detection catches VirtualBox, VMware, Hyper-V, QEMU
  - 8 lockdown subsystems activate in <500ms, disengage cleanly on submit
  - Exception handler ensures taskbar/cursor always restored even on crash
  - Full exam lifecycle tested end-to-end: login → integrity check → lockdown → exam → submit → grade → review
- Conclusion: "ExamSentinel demonstrates that OS-level enforcement provides significantly stronger exam integrity than browser-based proctoring alone."

(Footer is already defined in section 2 above)

### IMPORTANT DESIGN NOTESn:
- This is a PRINTED poster — text must be readable from 3+ feet
- Title: 72-96pt, Section headings: 36-48pt, Body text: 24-28pt
- Use consistent iconography throughout
- Diagrams should be vector-style (clean lines, no pixelation)
- Leave breathing room between sections (don't cram)
- The poster should tell the story: Problem → Solution → How it works → Results

---
