# ExamSentinel — Threat Model

> **Status:** Pre-implementation specification
> **Companion to:** `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/SECURITY_DESIGN.md`
> **Audience:** Anyone designing or reviewing a defense in this system.

---

## 1. Adversary

The adversary is **the student sitting the exam**. They have:

- Full administrative or standard-user access to the Windows 10/11 machine they are taking the exam on (we assume the institution has not centrally locked the machine down — the `.exe` is the only line of defense).
- Time to prepare before the exam: they can install software, configure hardware, learn the binary's behaviour by running it on practice exams, read leaked documentation, and rehearse cheat workflows.
- A motive: a higher score. The adversary is rational; we model them as paying a cost (effort, risk of detection) for a benefit (extra marks). Our job is to raise the cost faster than the benefit grows.
- The exam binary itself, which they may attempt to reverse-engineer, patch, or run under instrumentation.

The adversary is **not** assumed to be a sophisticated attacker by default — most students will try the path-of-least-effort attacks (alt-tab, copy-paste, screen-share). A minority will go further (VMs, helper apps). A very small minority will attempt true bypass-grade attacks (driver loading, kernel hooks, hardware injection); those fall out of scope, see §3.

---

## 2. In-Scope Threats

Each threat below is one we commit to detect, prevent, or evidence. The corresponding defense is documented in `docs/SECURITY_DESIGN.md`.

### 2.1 App switching to consult notes
The student presses Alt+Tab, the Windows key, or clicks the taskbar to switch to a Notepad window, an Edge tab, a PDF reader, or any other application containing prepared notes, lecture slides, or model answers. They read the answer, switch back, and type. Variants include alt-launching via Ctrl+Esc (Start menu), Ctrl+Shift+Esc (Task Manager), or Win+R (Run dialog). This is the highest-volume threat by far — it is what the median cheating student attempts first. Our response combines a low-level keyboard hook that swallows the relevant key combos before they reach the OS, a focus monitor that detects any loss of foreground status and force-restores the exam window while logging an incident, and a fullscreen takeover that hides the taskbar so visual affordances for switching are gone.

### 2.2 Copy-paste of question or answer text
The student selects question text in the exam window and copies it to the clipboard, then pastes it into a search engine, a friend's chat, an AI assistant, or a notes app to obtain an answer. The reverse — pasting prepared answer text from the clipboard into the answer field — is equally damaging. Both share a common surface: the Windows clipboard. Our response is a clipboard scrubber that clears the clipboard on a short interval throughout the live phase and logs each scrub with a hash and length of what was wiped (never the content), plus right-click suppression in the Tkinter widgets to remove the obvious copy/paste UI affordance.

### 2.3 Full-screen screenshots and screen recorders
The student presses Print Screen to capture question text to a file, runs Snipping Tool to capture a region, or starts a recording in OBS, NVIDIA ShadowPlay, or the Xbox Game Bar to record the entire exam for later review or to share with a confederate in real time. Our response captures the Print Screen scancode in the keyboard hook and discards it, blacklists the known screen-capture process names so they are killed on sight by the process scanner, and logs every kill as an incident so the teacher can see attempts even when prevention succeeds.

### 2.4 Helper apps (Discord, AnyDesk, TeamViewer, OBS, Snipping Tool)
The student runs Discord (to receive answers via screen-share or chat), AnyDesk or TeamViewer (to give a remote helper full control of their machine), OBS (to record), Snipping Tool (to capture stills), or similar utilities. These tools may be launched before the exam starts and minimised, or alt-launched during the exam via the techniques in 2.1. Our response is a process scanner running on a periodic interval against a named blacklist; any match is terminated via psutil and logged as a `blacklist_process_killed` incident with the process name and pid in the detail blob.

### 2.5 VirtualBox / VMware / Hyper-V guest with host as cheat surface
The student installs a hypervisor on the physical machine and runs the exam binary inside a guest VM. The host operating system, fully outside the binary's reach, displays notes, runs a search engine, runs Discord with a confederate, or runs AnyDesk for live remote help. Inside the guest the lockdown looks pristine. Our response is the **Standard VM Detection** gate that runs before the live phase — it queries WMI for BIOS, system manufacturer, motherboard, and video-controller fingerprints; checks the MAC address OUI against the well-known VMware / VirtualBox / Hyper-V ranges; reads registry artifacts left by guest-additions installs; and enumerates running processes for `vmtoolsd`, `VBoxService`, `vmwaretray`, and equivalents. Any positive aborts the session as `aborted_vm`.

### 2.6 Hardened/stealth VMs
A more sophisticated student removes guest tools, spoofs the BIOS strings via VBoxManage `setextradata`, randomises the MAC address out of the OUI ranges, and uninstalls anything advertising "VMware" or "VirtualBox". The Standard gate sees a clean machine. Our response is the **Stealth VM Detection** gate, also pre-live: it reads the CPUID hypervisor-present bit at leaf 1, ECX, bit 31; reads the hypervisor vendor string at CPUID leaf 0x40000000; measures RDTSC deltas across instructions known to trap on hypervisors (e.g. CPUID itself); compares short Sleep durations to wall-clock to detect timing dilation; enumerates suspicious driver names that persist after guest-tool removal; and reads thermal-zone temperatures via WMI as a soft signal (real hardware exposes thermal sensors; many VMs do not). Any single critical signal aborts the session as `aborted_stealth_vm`.

### 2.7 Alt-launch via Win key / Ctrl+Esc / Ctrl+Shift+Esc / Task Manager / Run dialog
A subset of 2.1 worth calling out separately because each has its own keyboard path. Pressing the Windows key (left or right) opens the Start menu. Ctrl+Esc does the same. Ctrl+Shift+Esc opens Task Manager directly, bypassing the Start menu. Win+R opens the Run dialog from which arbitrary executables can be launched. Win+E opens File Explorer. Each of these is a distinct keyboard combination handled explicitly in the keyboard hook's swallow list. Task Manager itself, if it does open (because the keyboard hook is bypassed via a hardware path), is also in the process blacklist.

### 2.8 Multi-monitor cheat displays
The student attaches a second monitor — built into a laptop dock, an HDMI-connected TV, an extended display from a USB capture card — and arranges Windows so that the exam runs on the primary monitor while notes, a chat window, or a confederate's screen-share runs on the secondary. The fullscreen takeover only covers one display, so visually the cheat surface is still visible and the cursor can travel to it. Our response is multi-monitor detection at session start: if more than one display is enumerated the exam refuses to start, surfacing a `multi_monitor_blocked` error with instructions to disconnect the secondary display. The detection is repeated on a hot-plug interval during the live phase; an attached display mid-exam logs an incident and pauses the exam UI until the display is removed.

### 2.9 Network exfiltration of question content
The student copies question text into a script that posts it to Pastebin, a Discord webhook, or a personal server so that a confederate elsewhere can answer and reply. Network egress is not directly blockable from user-mode without administrative changes to the host firewall, which we cannot assume. Our response is partial and indirect: the clipboard scrubber removes the most common copy path; the helper-app blacklist denies the most common chat clients; and the screenshot suppression denies the most common image-capture path. What remains — typing question text into a still-allowed channel — produces evidence in the form of large outbound focus-loss windows that the teacher can review. We do not claim to prevent network exfiltration; we claim to make it harder and to leave a trail.

---

## 3. Out-of-Scope Threats

We explicitly do not defend against these. Pretending otherwise would be dishonest and would lower the ceiling of what the in-scope defenses can promise.

- **A second physical device.** A phone, tablet, or second laptop next to the keyboard, used to consult notes or chat with a confederate, is invisible to a process running on the exam machine. We have no sensor for it. Mitigation belongs to the proctoring layer (camera, in-person invigilation) which is outside this product.
- **Another human in the room.** A friend, sibling, or paid helper sitting next to the student and dictating answers leaves no software trace. Same mitigation.
- **OS-level rootkits or signed-driver malware.** A kernel-mode driver can hide processes from psutil, hide files from the registry checks, and forge CPUID returns. We run in user mode; if the kernel lies to us, we believe it. Defending against a malicious ring-0 component requires a different product class (an EDR agent loaded earlier in boot than the adversary's driver).
- **Hardware-level attacks.** A USB device that injects keystrokes (Rubber Ducky, Bash Bunny), a hardware key-logger that records the answer key after the teacher types it elsewhere, an HDMI splitter that mirrors the exam screen to a hidden monitor, BadUSB-class peripherals — these operate below the OS and below any user-mode defense. Out of scope.

---

## 4. Defense Philosophy

ExamSentinel is **defense in depth**: each layer (pre-exam VM gates → live OS lockdown → continuous monitoring → forensic logging → teacher review) is independently weak but collectively raises the cost of cheating to a level most students will not pay, and produces a defensible evidence trail for the few who try. We **do not claim bypass-proofness**. A determined adversary with administrative privileges, a kernel debugger, and enough time can defeat any user-mode lockdown. Our goal is to push the median attacker toward the threshold of effort where cheating is no longer rational and to give the teacher, when an attempt is made, a structured timeline of incidents — VM detections, focus losses, blacklist-process kills, clipboard scrubs, lockdown-key attempts — that makes academic-integrity decisions defensible. The system is honest about its limits; the threat model exists so that no one mistakes "we tried" for "we succeeded."
