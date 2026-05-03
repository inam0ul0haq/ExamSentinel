# ExamSentinel — Security Design

> **Status:** Pre-implementation specification
> **Companion to:** `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/THREAT_MODEL.md`
> **Audience:** Implementers of the `client/app/vm_detect/` and `client/app/lockdown/` modules.

This document describes every defense in the client. For each defense it states what the defense does, the Windows mechanism it relies on (named in prose, no code), how it integrates with the lockdown manager, what it logs, and where it is known to be weak. The threats each defense addresses are catalogued in `docs/THREAT_MODEL.md`.

---

## 1. Phase Ordering and the Two-Gate Rule

The client enforces three phases in strict order. **Both** the Standard VM gate and the Stealth VM gate must return negative before the live phase begins. A positive on either gate logs an `IncidentLog` of type `vm_detected` or `stealth_vm_detected`, transitions the `ExamSession` to `aborted_vm` or `aborted_stealth_vm` respectively, and refuses to engage lockdown. The exam UI is never shown.

Closing and re-running the `.exe` always re-runs **both** gates from scratch — there is no cached "you already passed" state on disk. This is by design: an adversary who successfully convinces the gate once on a given machine state must convince it again every time. Combined with the server's idempotent session-restart behaviour (see `docs/API.md` §6, `POST /sessions`), the student lands back at the same `pre_check` session id and the gates run anew.

A developer-only flag, **`SKIP_VM_CHECK`**, exists to bypass both gates during local development. It is read from an environment variable at startup; when set to a truthy value, the client logs a one-time warning, emits an `IncidentLog` of type `lockdown_violation` with `severity = critical` and detail `{ "reason": "skip_vm_check_set" }` so the bypass is visible to the teacher in the timeline, and proceeds to lockdown. The flag is intended for testing on developer machines that are themselves VMs; production builds packaged for distribution must have the flag-reading code path stripped or hard-disabled at build time, and the build pipeline must verify this before signing the executable.

---

## 2. Standard VM Detection (`client/app/vm_detect/standard.py`)

### What it does
Runs four independent checks; if any returns positive, the gate fails. Each check produces a structured result the detail blob carries to the server.

### Windows mechanisms
- **WMI hardware fingerprints.** Queries the WMI namespace `root\CIMV2` for `Win32_BIOS` (manufacturer, serial number, version), `Win32_ComputerSystem` (manufacturer, model), `Win32_BaseBoard` (motherboard manufacturer and product), and `Win32_VideoController` (adapter name). These fields are matched against substring patterns known to appear on hypervisor guests: `VirtualBox`, `VBOX`, `VMware`, `VMW`, `Microsoft Corporation` paired with `Virtual Machine`, `QEMU`, `Xen`, `innotek`, `Parallels`. A match on any field flips the check positive.
- **MAC address OUI checks.** Enumerates network adapters and reads each MAC address. The first three octets (OUI) are compared against published vendor ranges: VMware (`00:05:69`, `00:0C:29`, `00:1C:14`, `00:50:56`), VirtualBox (`08:00:27`, `0A:00:27`), Hyper-V / Microsoft virtual adapter (`00:15:5D`), Parallels (`00:1C:42`). A match on any active adapter is positive.
- **Registry artifact checks.** Reads well-known registry keys that guest-tool installers create: `HKLM\SOFTWARE\Oracle\VirtualBox Guest Additions`, `HKLM\SOFTWARE\VMware, Inc.\VMware Tools`, `HKLM\SYSTEM\ControlSet001\Services\VBoxGuest`, `HKLM\SYSTEM\ControlSet001\Services\vmtools`, plus the Hyper-V integration services keys. Presence of any of these keys is positive.
- **Running-process checks.** Enumerates processes via psutil and matches names case-insensitively against `vmtoolsd.exe`, `vmwaretray.exe`, `vmwareuser.exe`, `VBoxService.exe`, `VBoxTray.exe`, `vmcompute.exe`, `vmms.exe`, `prl_tools.exe`. A match is positive.

### Integration with the lockdown manager
The lockdown manager (`client/app/lockdown/manager.py`, conceptually) calls `standard.run()` at the end of pre-check before it ever calls the stealth detector. The function returns a `(passed: bool, detail: dict)` tuple. On `passed = False` the manager:
1. Calls the API client to ship an `IncidentLog` with `incident_type = vm_detected`, `severity = critical`, `client_timestamp = now`, and `detail` carrying the full per-check breakdown so the teacher can see which signal fired.
2. Calls the API client to PATCH the session to `aborted_vm`.
3. Surfaces a Tkinter modal with the message "VM environment detected. The exam cannot run inside a virtual machine." and an OK button that exits the process.

It does not engage any lockdown component. No keyboard hook, no fullscreen, nothing — the student should retain a normal desktop so they can read the message and take corrective action (use a real machine).

### Events logged
A single `IncidentLog` of type `vm_detected` with `detail` carrying:
- `wmi_matches`: array of `{ class, field, matched_value, matched_pattern }`
- `mac_matches`: array of `{ adapter_name, mac, matched_oui, vendor }`
- `registry_matches`: array of registry key paths that exist
- `process_matches`: array of `{ name, pid }`

### Known limitations
- **OUI checks miss randomised MACs.** A student who randomises their virtual NIC's MAC outside the published OUI ranges defeats this check entirely.
- **WMI strings can be spoofed.** VirtualBox supports `setextradata "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVendor"` and similar handles to overwrite every BIOS string. A spoofed-string VM looks identical to bare metal at the WMI layer.
- **Guest tools are optional.** Removing VirtualBox Guest Additions and VMware Tools eliminates the registry, process, and most WMI signals at once. The system remains a guest; we no longer detect it from this gate alone.

These are exactly the gaps the Stealth gate exists to close.

---

## 3. Stealth VM Detection (`client/app/vm_detect/stealth.py`)

### What it does
Runs six checks that target signals harder to scrub than installed tools. Designed to fire on hardened guests where the Standard gate has been deliberately defeated. Each check is heuristic — Stealth detection produces evidence, not proof.

### Windows mechanisms
- **CPUID leaf 1, ECX, bit 31 — hypervisor-present bit.** Issues the CPUID instruction with EAX=1 and reads bit 31 of ECX. This bit is set by every well-behaved hypervisor (it is how hypervisors advertise themselves to guests for paravirtualisation negotiation). On bare metal it is always zero. A naive guest leaves it set; a hardened guest may force it to zero. Set is positive; zero is inconclusive (other checks must decide).
- **CPUID leaf 0x40000000 — hypervisor vendor string.** Issues CPUID with EAX=0x40000000 and reads the 12-byte ASCII vendor string from EBX:ECX:EDX. Known strings: `VMwareVMware`, `VBoxVBoxVBox`, `Microsoft Hv` (Hyper-V), `KVMKVMKVM`, `XenVMMXenVMM`, `prl hyperv`. Any non-empty value is positive (bare metal returns zeros at this leaf).
- **RDTSC timing deltas across trapping instructions.** Reads the timestamp counter via RDTSC immediately before and after instructions that trap into the hypervisor — CPUID is the canonical choice. On bare metal CPUID takes a few hundred cycles. On a hypervisor it traps and the delta jumps by an order of magnitude (thousands to tens of thousands of cycles). The check averages a thousand samples to absorb scheduler noise; a median delta above a calibrated threshold is positive.
- **Sleep-versus-wallclock skew.** Sleeps for a known short duration (e.g. 50 ms) using the OS scheduler and compares the wall-clock delta (via the Windows performance counter) to the requested duration. On bare metal the actual sleep is within a small percentage of the request. Some hypervisors and timing-attack countermeasures distort this. A consistent skew above threshold across multiple samples is a soft signal.
- **Suspicious-driver enumeration.** Reads `HKLM\SYSTEM\CurrentControlSet\Services` and lists driver entries whose `ImagePath` contains substrings like `vbox`, `vmware`, `vmci`, `vmusb`, `prl`, plus the Hyper-V integration drivers. These entries persist after guest-tool uninstallation in many cases — the `*.sys` files are removed but the service registration is left behind. Any match is positive.
- **Deep registry artifacts.** Beyond the keys checked by the Standard gate, this scans the entire `HKLM\HARDWARE\DESCRIPTION\System` tree for `SystemBiosVersion` and `VideoBiosVersion` strings containing virtualisation indicators, and `HKLM\HARDWARE\DEVICEMAP\Scsi` for SCSI controller names like `VBOX HARDDISK` or `VMware Virtual disk`. These are read by the BIOS-emulator and harder to fully scrub than the visible install keys.
- **Thermal-zone constancy (soft signal).** Queries WMI namespace `root\WMI` for `MSAcpi_ThermalZoneTemperature`. Real machines expose at least one thermal sensor with a value that drifts over time. Many VMs return either no instances at all or a single instance with an implausibly constant value (e.g. exactly 300 K). Zero instances or a constant-value reading across two samples taken seconds apart is a soft signal — never used alone, but combined with another signal it tips the gate.

### Integration with the lockdown manager
Same pattern as the Standard gate. The manager calls `stealth.run()` after `standard.run()` returns clean. Return is `(passed, detail)`. The manager combines the per-check results with a small policy: any of CPUID-bit, CPUID-vendor-string, suspicious-driver, or deep-registry alone is a hard fail; RDTSC, sleep-skew, and thermal-zone alone are soft signals; two soft signals together are a hard fail. On hard fail the manager ships a `stealth_vm_detected` incident, transitions to `aborted_stealth_vm`, surfaces a Tkinter modal, and exits. Lockdown is never engaged.

### Events logged
A single `IncidentLog` of type `stealth_vm_detected` with `detail` carrying:
- `cpuid_hv_bit`: boolean
- `cpuid_vendor`: string or null
- `rdtsc_median_delta`: integer cycles
- `rdtsc_threshold`: integer cycles
- `sleep_skew_ratio`: float
- `suspicious_drivers`: array of driver service names
- `deep_registry_matches`: array of `{ key, value, matched_pattern }`
- `thermal_samples`: array of float Celsius readings (or empty array, which itself is the signal)
- `timing_samples`: array of float microsecond deltas from the RDTSC probe

The `timing_samples` and `thermal_samples` arrays are precisely the optional fields documented in `docs/API.md` §7 — this is where they are populated.

### Known limitations
- **Heuristic, not proof.** Every signal can be defeated individually by a sufficiently determined adversary. CPUID can be hidden by a hypervisor that intercepts the instruction (most modern ones do not bother because guests rely on the bit). Vendor strings can be patched by recompiling the hypervisor. RDTSC can be smoothed by the hypervisor. Stealth detection produces *evidence the teacher can act on*, not a binary "this is a VM" certainty.
- **False positives on real machines.** Some unusual real hardware (laptops with aggressive thermal throttling, machines with CPU-virtualisation features lit up by other applications) can fire RDTSC or thermal signals. The two-soft-signals-equals-hard-fail policy is calibrated to keep false positives rare; the threshold values must be tuned during development against a corpus of real student machines and adjusted before production rollout.
- **CPUID can be lied to by ring-0.** A signed driver loaded by the adversary can intercept CPUID and forge the result. We do not defend against this — see `docs/THREAT_MODEL.md` §3.

---

## 4. Live-Phase Windows Lockdown (`client/app/lockdown/`)

The lockdown manager engages the components below in a fixed order as soon as both VM gates pass, then disengages them in reverse order at the end of the post phase. Every component exposes `engage()` and `disengage()` and each `disengage()` is idempotent and crash-safe (see §6).

### 4.1 Low-level keyboard hook (`keyboard_hook.py`)

**What it does.** Intercepts every keystroke before it reaches any application — including the Windows shell — and swallows a denylist of combinations. Allowed keystrokes (alphanumerics, punctuation, navigation) pass through unchanged so the student can type answers.

**Windows mechanism.** Installs a `WH_KEYBOARD_LL` low-level keyboard hook via `SetWindowsHookEx` (called through pywin32 / ctypes). The hook procedure runs on a dedicated thread with a Windows message pump. For each event it inspects the virtual-key code and the current state of modifier keys (held via tracking the make/break of Alt, Ctrl, Shift, and the Windows keys, since the hook does not receive a snapshot of modifier state). On a swallowed combination it returns a non-zero value to stop propagation. On all other events it calls `CallNextHookEx`.

**Swallowed combinations.** Alt+Tab, Alt+F4, the Windows key (left and right, both make and break), Ctrl+Esc, Alt+Esc, Ctrl+Shift+Esc, Print Screen (VK_SNAPSHOT), Win+R, Win+E, Win+D, Win+L, Win+M, Alt+Space, F4 with Alt, F11 (to prevent the student leaving fullscreen by accident or otherwise).

**Integration.** Engaged first so it is in place before any subsequent component opens any visual surface. The hook handle is stored on the manager. Disengagement calls `UnhookWindowsHookEx`. Engaging is idempotent — calling `engage()` twice replaces the previous hook cleanly.

**Events logged.** Every swallowed combination emits a `lockdown_violation` event into the queue (see §5) with `severity = warning` and `detail` carrying the combination name (e.g. `alt_tab`, `print_screen`) and the timestamp. High-frequency combinations are coalesced — the same combination within 500 ms collapses into a single event with a `count` field — to avoid drowning the incident log if a student holds a key down.

**Known limitations.** A low-level hook is itself a user-mode mechanism. A higher-priority hook installed earlier, or a kernel-mode keyboard filter, sees the events first and can either swallow them before our hook runs or inject events that bypass our hook. **Print Screen suppression specifically does not stop hardware Print Screen scancodes on every keyboard** — some keyboards generate the screenshot via a firmware path that talks to the OS at a level our hook cannot reach, and some screen-capture utilities listen on a different input channel (e.g. WM_HOTKEY registered globally). For these, the helper-app blacklist is the second line of defense.

### 4.2 Process scanner / killer (`process_killer.py`)

**What it does.** On a periodic interval, enumerates running processes and terminates any whose name matches a configured blacklist.

**Windows mechanism.** Uses psutil to iterate processes (psutil internally uses `EnumProcesses` and the toolhelp32 snapshot APIs). For each process, the executable name is compared case-insensitively against the blacklist. A match calls `psutil.Process.kill()` which sends `TerminateProcess` under the hood. If termination fails (insufficient privileges, protected process), the failure is logged but the scan continues — a kill failure is itself useful evidence.

**Blacklist (initial).** `discord.exe`, `anydesk.exe`, `teamviewer.exe`, `obs64.exe`, `obs32.exe`, `obs.exe`, `snippingtool.exe`, `screenpresso.exe`, `bandicam.exe`, `nvcontainer.exe` (NVIDIA ShadowPlay container), `xboxapp.exe`, `gamebar.exe`, `taskmgr.exe`, `cmd.exe`, `powershell.exe`, `pwsh.exe`, `regedit.exe`, `mstsc.exe` (Remote Desktop client), `teams.exe`, `zoom.exe`, `slack.exe`, `chrome.exe`, `msedge.exe`, `firefox.exe`, `notepad.exe`, `wordpad.exe`. The list is documented and configurable per deployment; the actual final list will be tuned with the institution.

**Integration.** Engaged second, after the keyboard hook so newly-spawned processes during engagement are caught. Runs on a background thread waking every two seconds (configurable). Disengage signals the thread to stop and joins it with a timeout.

**Events logged.** Each successful kill emits a `blacklist_process_killed` incident with `severity = warning` and `detail` carrying the process name, pid, and command line if accessible. Each failed kill emits the same type with `severity = critical` and an additional `error` field describing the failure (e.g. `access_denied`).

**Known limitations.** A renamed executable bypasses the name match. The list is finite; a helper app the student installs whose name is not on the list runs unmolested. Process scanning is reactive — the helper app runs for up to the scan interval before being killed, which may be enough time to read a question and reply with an answer.

### 4.3 Clipboard scrubber (`clipboard.py`)

**What it does.** Clears the Windows clipboard on a short interval throughout the live phase, denying both the copy-out path (question text → external app) and the paste-in path (prepared answer → answer field).

**Windows mechanism.** Calls `OpenClipboard`, `EmptyClipboard`, `CloseClipboard` via pywin32. Before clearing, it inspects the current clipboard contents — if non-empty, it computes a SHA-256 hash and records the byte length, then clears. The content itself is never logged.

**Integration.** Engaged third. Runs on a background thread waking every one second (configurable). Disengage signals the thread to stop.

**Events logged.** Every non-empty clear emits a `clipboard_scrubbed` incident with `severity = info` and `detail` carrying the SHA-256 hash, the byte length, and the format (text, image, file-list). Empty-clipboard wakes do not log.

**Known limitations.** A one-second interval is a window during which a fast student can paste; pushing it shorter risks causing perceived lag in legitimate apps the user is allowed to interact with (none, in our case, but this is a general consideration). Clipboard managers running with elevated permissions can hold history outside the standard clipboard surface; we do not see those.

### 4.4 Right-click suppression (Tkinter level)

**What it does.** Prevents the right-click context menu from appearing in any answer entry widget, removing the visual affordance for copy/paste.

**Windows mechanism.** None at the Win32 level — this is implemented in Tkinter by binding `<Button-3>` (right-click) on every `Text` and `Entry` widget to an event handler that returns `"break"`. Ctrl+C, Ctrl+V, Ctrl+X, and Ctrl+A keyboard accelerators on the same widgets are bound to no-op handlers. The clipboard scrubber catches anything that slips through these UI bindings.

**Integration.** Engaged fourth, applied at widget construction time in `client/app/ui/exam_screen.py`. No teardown required — Tkinter discards the bindings when the widgets are destroyed.

**Events logged.** None — UI-level suppression is not interesting to the teacher and would generate an unhelpful volume of events.

**Known limitations.** Suppression applies only to the bound widgets; if a future UI change introduces a new editable widget without the suppression bindings, copy-paste returns. The convention is enforced by code review, not by the platform.

### 4.5 Fullscreen takeover (`fullscreen.py`)

**What it does.** Forces the exam Tkinter window to cover all pixels of the primary monitor, removes its title bar and borders, sets it always-on-top, and hides the Windows taskbar. Removes any visual handle by which the student could resize, minimise, or escape the window.

**Windows mechanism.** On the Tkinter root: `attributes('-fullscreen', True)`, `attributes('-topmost', True)`, `overrideredirect(True)` to remove the title bar. For taskbar hide: locates the taskbar window (`Shell_TrayWnd`) via `FindWindow` (pywin32) and calls `SetWindowPos` with `SWP_HIDEWINDOW`, plus `ITaskbarList.SetState` via COM if available, and similarly hides the secondary-taskbar `Shell_SecondaryTrayWnd` on multi-monitor setups even though the multi-monitor block (4.8) should have prevented us reaching this code in that situation.

**Integration.** Engaged fifth. The original window styles, position, and the taskbar's pre-engage visibility state are saved on the manager so disengage can restore them precisely.

**Events logged.** None on engage. Disengage logs nothing on success; on partial failure (e.g. taskbar refuses to re-show because explorer.exe is in a bad state) it logs an `info` incident with `detail.component = fullscreen_disengage` and the specific failure.

**Known limitations.** `overrideredirect` plus topmost is a strong but defeatable combination — a focus-stealing dialog from another process (e.g. a Windows update prompt, a UAC consent dialog) can briefly appear above the exam window. The focus monitor (4.7) catches the focus loss; the visual leak before the focus monitor reacts is a known small-window vulnerability.

### 4.6 Mouse boundary lock (`mouse_lock.py`)

**What it does.** Constrains the cursor to the bounding rectangle of the exam window. The mouse cannot travel to a hidden secondary display, to a sliver of taskbar that may be peeking through, or off-screen entirely.

**Windows mechanism.** Calls `ClipCursor` via pywin32 with the screen rectangle of the exam window. The clip rectangle is re-applied whenever the exam window is moved or resized (not expected during a live exam, but defensively handled). Disengage calls `ClipCursor(None)` to release the clip.

**Integration.** Engaged sixth, after the fullscreen takeover so the bounding rectangle is the full screen. The pre-clip state (whether ClipCursor was already in use by some other application) is recorded; on disengage the recorded state is restored.

**Events logged.** None on engage. The cursor is silently constrained.

**Known limitations.** `ClipCursor` is released by Windows automatically when the focused window changes — meaning a successful focus loss (which the focus monitor 4.7 will react to) also breaks the clip during the failure window. Re-application happens when focus returns. An adversary who can rapidly toggle focus may briefly escape the clip; the focus monitor logs each toggle.

### 4.7 Focus monitor (`focus_monitor.py`)

**What it does.** Detects any loss of foreground status by the exam window and (a) re-foregrounds the exam window, (b) logs the event, (c) snapshots the foreground window that stole focus.

**Windows mechanism.** Installs a WinEvent hook for `EVENT_SYSTEM_FOREGROUND` via `SetWinEventHook`. The hook callback runs on a dedicated message-pump thread. On each foreground change it compares the new foreground HWND to the exam window's HWND. If different, it reads the new window's title (`GetWindowText`) and process name (`GetWindowThreadProcessId` then resolution via psutil), then calls `SetForegroundWindow` on the exam window. The OS may refuse the re-foreground if the calling thread does not own the foreground; the standard mitigation is to attach to the thread that owns the foreground via `AttachThreadInput`, call `SetForegroundWindow`, then detach. Both attempts are made; if both fail, the event is still logged.

**Integration.** Engaged seventh, last among the live components, so the exam window is the foreground at the moment the hook is installed (otherwise the very first event is the spurious "exam became foreground").

**Events logged.** Every foreground-loss event emits a `focus_loss` incident with `severity = warning` (escalated to `critical` after three losses within thirty seconds) and `detail` carrying the offending window title, process name, pid, and the timestamp of loss and the timestamp of recovery (or null if recovery failed).

**Known limitations.** A window the OS refuses to demote (some system dialogs, the secure-attention sequence Ctrl+Alt+Del which is intercepted by Winlogon and not by us at all) cannot be force-demoted. The focus monitor still logs the event so the teacher sees it, but the student briefly sees the other window. Ctrl+Alt+Del is fundamentally undetectable and unrecoverable from user mode — we accept this and rely on the post-recovery focus-loss log for evidence.

### 4.8 Multi-monitor detection / block (`multi_monitor.py`)

**What it does.** At session start, refuses to begin the live phase if more than one display is connected. During the live phase, polls for hot-plug events; if a second display attaches mid-exam, pauses the exam UI with a modal warning and logs an incident, resuming only when the display is removed.

**Windows mechanism.** Calls `EnumDisplayMonitors` via pywin32 / ctypes to enumerate active monitors. The count is checked against one. For hot-plug detection, the lockdown manager registers for the `WM_DISPLAYCHANGE` window message on the exam window's message procedure; arrival of this message during the live phase triggers a re-enumeration.

**Integration.** Engaged after both VM gates and *before* the keyboard hook — if the check fails at session start, no other lockdown component runs and the student is shown a modal "Disconnect secondary displays and re-run the exam" dialog. During the live phase the WM_DISPLAYCHANGE handler is wired up by the fullscreen component when it engages.

**Events logged.** A pre-start failure logs an incident of type `lockdown_violation` with `severity = critical` and `detail.kind = multi_monitor_blocked`, listing each monitor's resolution and device name. A mid-exam hot-plug logs the same type with `detail.kind = multi_monitor_hotplug` and the same per-monitor data. Disconnection of the offending monitor logs `detail.kind = multi_monitor_resolved`.

**Known limitations.** A virtual display driver (e.g. an NVIDIA-emulated monitor for screenshot tools) may not appear in `EnumDisplayMonitors` if it is not marked as an attached display. Capture-card-as-monitor configurations vary widely. Headless capture devices that mirror the existing display rather than presenting a new one are invisible to this check.

---

## 5. Violation Logging Pipeline

### Producer-consumer architecture
Every defense in §4 is a *producer* of incident events. They write into a single in-memory `queue.Queue` instance owned by the lockdown manager (`client/app/lockdown/manager.py`, conceptually). Each event is a structured dict with `incident_type`, `severity`, `client_timestamp`, and `detail`, ready to be POSTed to the server's `/sessions/{id}/incidents` endpoint per `docs/API.md` §7.

### Background flusher
A dedicated daemon thread (`incident_flusher`) consumes the queue and POSTs each event to the server. Submission policy:
- **In-flight:** events are sent one-at-a-time to `POST /sessions/{id}/incidents` during the live phase. The flusher waits up to a small interval (e.g. 250 ms) to coalesce bursts; if multiple events are pending, they are sent serially.
- **On HTTP failure (network drop, server 5xx):** the event is requeued and an exponential backoff applies (1 s, 2 s, 4 s, 8 s, capped at 30 s). The flusher continues to drain new events from the queue meanwhile so the queue does not block.
- **On submit (post phase):** the manager sets a "drain" flag and waits up to ten seconds for the queue to empty. Any remaining events are sent via `POST /sessions/{id}/incidents/bulk` as a single batch. Lockdown disengage is not allowed to start until the drain completes (or times out, in which case the residual events are persisted to a local file `client/build/incidents_<session_id>.jsonl` and the user is informed; the file is the offline fallback for the next launch to re-attempt upload).

### Offline queueing
If the client started offline (no network), events still accumulate in the in-memory queue and the flusher's exponential backoff keeps retrying. If the queue exceeds a soft cap of 5000 events, the oldest `info`-severity events are spilled to the local jsonl file to bound memory; `warning` and `critical` events are never spilled and always retained in memory. On next successful POST, spilled events are read back and re-enqueued in their original order.

### Ordering guarantees
Events are serialised in `client_timestamp` order at insertion; the server stores the `server_timestamp` it observes on receive. The teacher's review payload (`GET /sessions/{id}/full`) sorts by `server_timestamp` ascending, which preserves the order of events that were online at the time and orders offline-buffered events by their delayed-arrival time. The teacher sees both `client_timestamp` and `server_timestamp` per incident, and the divergence between them is itself evidence (a large gap suggests deliberate disconnection during the exam).

---

## 6. Clean-Shutdown Contract

**Every** component in §4 must guarantee its `disengage()` is reachable and successful regardless of whether the live phase ended normally (student submitted), exceptionally (timeout fired, server returned `aborted_*`), or catastrophically (Python exception, OS exception, SIGTERM, the user pulling the power — in which case the contract still applies on the next boot, see "crash recovery" below).

### Try/finally discipline
The lockdown manager wraps the entire live phase in a `try/finally` block. The `finally` clause calls `disengage()` on every component in reverse engage order, swallowing exceptions per-component and logging each failure so a single component's disengage failure does not strand its peers. This applies to:
- The keyboard hook (must call `UnhookWindowsHookEx` — a leaked hook continues to swallow keystrokes after process exit until the OS reclaims it).
- The process scanner thread (must be signalled to stop and joined; the daemon flag means it would die on process exit, but explicit shutdown lets the final scan-in-progress complete cleanly).
- The clipboard scrubber thread (same).
- The fullscreen takeover (must restore the window's `overrideredirect`, fullscreen, and topmost attributes, and re-show the taskbar).
- The cursor clip (must call `ClipCursor(None)`).
- The focus monitor's WinEvent hook (must call `UnhookWinEvent`).
- The multi-monitor WM_DISPLAYCHANGE handler (must be detached from the window proc).
- The incident flusher thread (must drain and stop).

### Crash recovery
A `client/app/lockdown/recovery.py` module runs at every `.exe` startup *before* the login screen. It:
1. Re-shows the taskbar unconditionally (cheap; no-op if already shown).
2. Releases any cursor clip via `ClipCursor(None)`.
3. Removes the topmost flag from any orphaned exam window (search by class name and process owner).
4. Logs a local-only event (not to the server, since no session context exists yet) noting that recovery ran.

This guarantees that a student whose machine crashed mid-exam is not left with a hidden taskbar or clipped cursor when they boot back up. The recovery logic is idempotent and safe to run on every launch.

### Exit signal handling
The Tkinter root is registered with a `WM_DELETE_WINDOW` protocol handler that ignores the close request during the live phase (the window cannot be closed via Alt+F4 — already swallowed — or any other means — already swallowed — but the handler is defensive). In any post-phase or pre-phase state the handler triggers an orderly shutdown via the same finally block.

---

## 7. Honest Statement of Limits

A determined adversary can defeat any user-mode software lockdown given enough preparation. The components in §4 raise the cost of cheating to a level most students will not pay; they do not make cheating impossible. Specifically:

- **Print Screen suppression via low-level keyboard hook does not stop hardware Print Screen scancodes on every keyboard.** Some keyboards generate the screenshot via a firmware-level mechanism that does not flow through the standard input stack. Some screen-capture utilities listen on a separate hotkey channel registered with `RegisterHotKey` that, depending on the registration order, may fire ahead of our hook. The blacklist of capture utilities is the second line of defense for these cases.
- **Stealth VM detection is heuristic, not proof.** Every signal can be defeated individually by a sufficiently sophisticated adversary, and edge-case real hardware can occasionally fire false positives. The two-soft-signal policy (§3) mitigates false positives but does not eliminate them. Threshold tuning during development is a hard requirement before production rollout.
- **A signed driver loaded by the adversary defeats everything.** A ring-0 component can hide processes, forge CPUID, intercept `SetWindowsHookEx`, and lie to WMI. We do not defend against this; see `docs/THREAT_MODEL.md` §3.
- **A second physical device is invisible.** A phone next to the keyboard leaves no software trace; mitigation is human invigilation.
- **The `SKIP_VM_CHECK` flag exists in the source.** It is intended for developer use only and emits a critical incident when set so its use is auditable. Production builds must verify the flag-reading code is not active before signing.

These limits are documented so contributors understand what we promise and what we do not. We promise: a layered defense that catches the median attacker; an evidence trail for the non-median ones; and a clean-shutdown contract that respects the student's machine when the exam ends. We do not promise: bypass-proofness.
