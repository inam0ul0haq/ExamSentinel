# ExamSentinel OS Lockdown — Runbook

Reference for debugging, demo prep, and post-demo consultation.

## Architecture

The **LockdownManager** (`client/app/lockdown/manager.py`) coordinates 8 subsystems.
It registers them in a fixed order at startup and stops them in reverse order.

The **IncidentPipeline** (`client/app/services/incident_pipeline.py`) handles reliable
incident shipping with an in-memory queue, background flusher (every 5s), exponential
backoff, and synchronous `flush_now()` for submit/abort.

## Subsystem Registration Order

| # | Subsystem | File | Why This Position |
|---|-----------|------|-------------------|
| 1 | MultiMonitorSubsystem | `multi_monitor.py` | Abort before going fullscreen |
| 2 | KeyboardLockdown | `keyboard.py` | Block keys before fullscreen |
| 3 | ProcessKillSubsystem | `process_kill.py` | Kill blacklisted apps |
| 4 | ClipboardScrubSubsystem | `clipboard_scrub.py` | Clear clipboard |
| 5 | RightClickSuppressSubsystem | `right_click_suppress.py` | Bind handlers |
| 6 | FullscreenSubsystem | `fullscreen.py` | Go fullscreen + hide taskbar |
| 7 | FocusMonitorSubsystem | `focus_monitor.py` | Monitor focus |
| 8 | MouseBoundarySubsystem | `mouse_boundary.py` | Clip cursor (after fullscreen) |

Shutdown order is **reversed**: mouse boundary released → focus monitor stopped →
fullscreen reverted + taskbar restored → ... → multi-monitor stopped.

## Subsystem Details

### 1. MultiMonitorSubsystem
- **What**: Detects multiple monitors via `screeninfo` / `EnumDisplayMonitors`
- **When**: On start + polls every 3s for hot-plug
- **Action**: Posts `MULTI_MONITOR_DETECTED` (critical), triggers `request_abort`
- **Incident types**: `MULTI_MONITOR_DETECTED`

### 2. KeyboardLockdown
- **What**: Low-level keyboard hook (`WH_KEYBOARD_LL`) via `SetWindowsHookExW`
- **Blocks**: Alt+Tab, Alt+F4, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc, Win key, PrintScreen, Win+any, Ctrl+Win+any
- **Allows**: All typing keys, plain Tab, arrows, backspace, enter
- **Incident types**: `KEYBOARD_BLOCKED` (warning, throttled 2s), `KEYBOARD_HOOK_UNAVAILABLE`
- **Requires**: Administrator privileges for reliable operation
- **Thread**: Dedicated thread with Windows message loop

### 3. ProcessKillSubsystem
- **What**: Kills blacklisted processes (browsers, editors, messaging, remote desktop, screen capture, system tools)
- **Blacklist**: 40 executables — see `BLACKLISTED_PROCESSES` constant in `process_kill.py`
- **Poll**: Every 2s via `psutil.process_iter`
- **Kill**: `terminate()` → wait 200ms → `kill()` if still alive
- **Incident types**: `BLACKLISTED_PROCESS_KILLED` (critical)
- **Throttle**: One incident per (process_name, pid) pair

### 4. ClipboardScrubSubsystem
- **What**: Clears system clipboard every 500ms
- **Uses**: `win32clipboard` (pywin32)
- **Incident types**: `CLIPBOARD_SCRUB` (warning)
- **Throttle**: One incident per 10s
- **Resilience**: Catches clipboard-locked errors, retries next tick

### 5. RightClickSuppressSubsystem
- **What**: Blocks right-click context menus in the exam window
- **Binds**: `<Button-3>` and `<Control-Button-1>` → returns "break"
- **Exposes**: `bind_for_widget(widget)` for dynamic widgets
- **Incident types**: `RIGHT_CLICK_BLOCKED` (warning)
- **Throttle**: One per 5s
- **No thread**: Runs on the main Tk event loop

### 6. FullscreenSubsystem
- **What**: Borderless fullscreen covering entire primary monitor including taskbar
- **Removes**: `WS_CAPTION`, `WS_THICKFRAME`, `WS_SYSMENU`, `WS_MINIMIZEBOX`, `WS_MAXIMIZEBOX`
- **Sets**: `HWND_TOPMOST`, uses `overrideredirect(True)` for Tk compatibility
- **Hides**: Taskbar (`Shell_TrayWnd`) + Win11 Start button (`Button` / `Start`)
- **Re-engage**: Polls every 1s, reapplies if window moved/resized
- **Incident types**: `FULLSCREEN_BREACH` (warning, throttled 5s)
- **Critical stop**: Taskbar restoration wrapped in own try block

### 7. FocusMonitorSubsystem
- **What**: Polls `GetForegroundWindow` every 500ms
- **Action**: On mismatch, yanks focus back via `SetForegroundWindow` + `AttachThreadInput`
- **Incident types**: `FOCUS_LOST` (warning, throttled 2s)
- **Includes**: Foreign window title in incident description

### 8. MouseBoundarySubsystem
- **What**: Confines cursor to exam window via `ClipCursor`
- **Re-applies**: Every 500ms (Windows can release clip on certain events)
- **Incident types**: `MOUSE_ESCAPE` (warning, throttled 2s)
- **Stop**: `ClipCursor(NULL)` to release

## Incident Types Summary

| Type | Severity | Source | Throttle |
|------|----------|--------|----------|
| `LOCKDOWN_ENGAGED` | info | Manager | Once |
| `LOCKDOWN_DISENGAGED` | info | Manager | Once |
| `STARTUP_PARTIAL_FAILURE` | warning | Manager | Once |
| `KEYBOARD_BLOCKED` | warning | KeyboardLockdown | 2s |
| `KEYBOARD_HOOK_UNAVAILABLE` | warning | KeyboardLockdown | Once |
| `BLACKLISTED_PROCESS_KILLED` | critical | ProcessKillSubsystem | Per (name, pid) |
| `CLIPBOARD_SCRUB` | warning | ClipboardScrubSubsystem | 10s |
| `RIGHT_CLICK_BLOCKED` | warning | RightClickSuppressSubsystem | 5s |
| `FULLSCREEN_BREACH` | warning | FullscreenSubsystem | 5s |
| `FOCUS_LOST` | warning | FocusMonitorSubsystem | 2s |
| `MOUSE_ESCAPE` | warning | MouseBoundarySubsystem | 2s |
| `MULTI_MONITOR_DETECTED` | critical | MultiMonitorSubsystem | Once (aborts) |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SKIP_VM_CHECK` | `0` | Skip VM detection gates |
| `SKIP_STEALTH_CHECK` | `0` | Skip RDTSC timing gate (Version A build) |
| `SKIP_LOCKDOWN` | `0` | Skip entire OS lockdown (dev only) |

**None of these should be set for the actual demo.**

## Windows Compatibility

All Win32 APIs used are stable across Windows 10 and 11:
- `SetWindowsHookExW` (WH_KEYBOARD_LL)
- `SetWindowLongPtrW`, `SetWindowPos`, `ShowWindow`
- `GetForegroundWindow`, `SetForegroundWindow`, `AttachThreadInput`
- `ClipCursor`, `GetCursorPos`
- `FindWindowW` (Shell_TrayWnd)
- `psutil` and `pywin32`

**Windows 11 divergence**: The Start button is a separate HWND (`Button` / `Start`)
which doesn't exist on Windows 10. The code tries both patterns and tolerates null.

## Exception Handling

The manager installs:
- `sys.excepthook` override → calls `manager.stop()` on unhandled exceptions
- `Tk.report_callback_exception` override → same for Tk event loop errors

This ensures the taskbar is always restored even on crashes.

## Dependencies

- `psutil==6.1.1` — process enumeration and killing
- `pywin32==308` — clipboard access (`win32clipboard`)
- `screeninfo==0.8.1` — monitor detection (fallback: `EnumDisplayMonitors`)
