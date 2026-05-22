# ExamSentinel — VM Detection Guide

> Simple, demo-ready documentation for the VM detection system.
> This replaces the complex architecture in `SECURITY_DESIGN.md` with our actual implementation.

---

## Overview

Our VM detection has **two gates** that run sequentially before every exam:

```
Student clicks "Start Exam"
    → Session created (status: pre_check)
    → Integrity Check Screen opens
    → Gate 1: Standard VM Detection (runs first)
    → Gate 2: Stealth VM Detection (runs second)
    → Both pass? → Continue button enables → Exam begins
    → Either fails? → Incident logged + Session aborted
```

---

## Gate 1: Standard VM Detection

**File:** `client/app/vm_detect/standard.py`
**Function:** `detect_standard_vm()`

Catches **default/unmodified** VMs with Guest Additions installed.

| Check | What It Does | Catches |
|-------|-------------|---------|
| **Process scan** | Scans running processes via `psutil` for VM guest tool processes | `VBoxService.exe`, `VBoxTray.exe`, `vmtoolsd.exe` |
| **Registry keys** | Checks `HKLM\SOFTWARE\Oracle\VirtualBox Guest Additions` and similar | Guest Additions installed |
| **WMI strings** | Queries `Win32_ComputerSystem` and `Win32_BIOS` for manufacturer names | "innotek GmbH", "VirtualBox", "VMware" |
| **MAC OUI** | Checks first 3 bytes of network MAC address against known VM vendor ranges | `08:00:27` (VirtualBox), `00:0c:29` (VMware), `00:15:5d` (Hyper-V) |

**Return format:**
```python
{
    "is_vm": True/False,
    "vm_type": "virtualbox" | "vmware" | "hyperv" | None,
    "indicators": [{"category": "process", "name": "VBoxService.exe", "evidence": "PID 1234", "vm_type": "virtualbox"}, ...]
}
```

---

## Gate 2: Stealth VM Detection

**File:** `client/app/vm_detect/stealth.py`
**Function:** `detect_stealth_vm()`

Catches **hardened VMs** where Guest Additions are removed and BIOS strings are spoofed.

| Check | What It Does | Why It Can't Be Faked |
|-------|-------------|----------------------|
| **Thermal zone** | Queries `MSAcpi_ThermalZoneTemperature` via WMI | Real PCs always have temp sensors. VMs have zero thermal zones. No VBoxManage command adds thermal sensors. |
| **SCSI disk ID** | Reads `HKLM\HARDWARE\DEVICEMAP\Scsi\...\Identifier` | The virtual disk controller firmware reports "VBOX HARDDISK". This is set by the virtual storage controller, NOT by Guest Additions or BIOS strings. |
| **RDTSC timing** | Measures CPU cycle cost of CPUID instruction using assembly shellcode | Hypervisors must trap CPUID → adds 1000+ cycles vs ~100 on bare metal. This is a fundamental hardware property that cannot be hidden from user-mode code. |

**Return format:**
```python
{
    "is_vm": True/False,
    "vm_type": "virtualbox" | "unknown_hypervisor" | None,
    "indicators": [...],
    "cpu_thermal_value": 26.85 | None,
    "timing_latency_cycles": 5432 | None
}
```

---

## How to Make the VM "Stealth" (For Demo)

These 5 commands defeat Gate 1 (standard detection) but NOT Gate 2 (stealth detection):

### Step 1: Inside the VM
- Control Panel → Uninstall "Oracle VM VirtualBox Guest Additions"
- Reboot the VM

### Step 2: On your HOST PC (PowerShell, VM powered off)
```powershell
cd "C:\Program Files\Oracle\VirtualBox"
.\VBoxManage setextradata "YourVMName" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemVendor" "Dell Inc."
.\VBoxManage setextradata "YourVMName" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemProduct" "Latitude 5520"
.\VBoxManage setextradata "YourVMName" "VBoxInternal/Devices/pcbios/0/Config/DmiBoardVendor" "Dell Inc."
.\VBoxManage setextradata "YourVMName" "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVendor" "Dell Inc."
.\VBoxManage modifyvm "YourVMName" --macaddress1 D4BED91A2C3F
```

> Replace `"YourVMName"` with your actual VM name in VirtualBox.

### Result After Stealth:
- ❌ VBoxService.exe → GONE
- ❌ Registry GA key → GONE
- ❌ WMI says "Dell Inc." → Spoofed
- ❌ MAC starts with D4:BE:D9 → Spoofed
- ✅ Thermal zones → Still ZERO (caught by stealth)
- ✅ SCSI disk → Still says "VBOX HARDDISK" (caught by stealth)
- ✅ RDTSC timing → Still 1000+ cycles (caught by stealth)

---

## Demo Flow (3 Steps for Evaluators)

### Demo 1: "Normal VM detected easily"
Run the .exe on a **default VirtualBox** (GA installed) → Standard gate catches it immediately.

### Demo 2: "I hardened it — basic detection fails"
On the **stealth VM**, show proof:
- Task Manager → No VBox processes
- PowerShell: `Get-WmiObject Win32_ComputerSystem | Select Manufacturer, Model` → Shows "Dell Inc."
- `ipconfig /all` → MAC starts with D4-BE-D9

Run **Version A** (standard-only detection) → All checks pass → Exam starts.

> **How to make Version A:** Set `SKIP_STEALTH_CHECK=1` in `client/.env` (or we can create a separate build — see below)

### Demo 3: "Our innovation catches it anyway"
Same stealth VM, run **Version B** (full detection) → Standard passes, stealth catches it via thermal + SCSI + RDTSC → Session aborted.

---

## Integration with Server (Parts 1-18)

### Flow Diagram
```
CLIENT                                   SERVER
──────                                   ──────
Student Dashboard
  └─ Click "Start Exam"
       └─ POST /sessions {exam_id}  ──→  Creates session (status: pre_check)
                                          Returns session_id
       
Integrity Check Screen
  └─ detect_standard_vm()
  └─ detect_stealth_vm()
  
  IF FAILED:
       └─ POST /sessions/{id}/incidents ──→  Creates IncidentLog row
          {type: "VM_DETECTED",               (incident_type, severity,
           severity: "critical",               cpu_thermal_value,
           cpu_thermal_value: ...,             timing_latency_ms)
           timing_latency_ms: ...}
       └─ POST /sessions/{id}/abort     ──→  Transitions session to
          {reason: "vm"|"stealth_vm"}         aborted_vm / aborted_stealth_vm
                                              Sets ended_at
  
  IF PASSED:
       └─ PATCH /sessions/{id}          ──→  Transitions pre_check → in_progress
          {status: "in_progress"}             Sets started_at, deadline_at
       └─ Navigate to Exam Taking Screen

Teacher Dashboard
  └─ GET /teacher/sessions/{id}/detail  ──→  Returns full session with
                                              incidents array showing
                                              VM_DETECTED / STEALTH_VM_DETECTED
                                              incidents with forensic data
```

### Server Endpoints Used

| Endpoint | Method | Purpose | File |
|----------|--------|---------|------|
| `/sessions` | POST | Create session (pre_check) | `server/app/routes/sessions.py` |
| `/sessions/{id}` | PATCH | Transition pre_check → in_progress | `server/app/routes/sessions.py` |
| `/sessions/{id}/abort` | POST | Abort session (vm/stealth_vm/user) | `server/app/routes/sessions.py` |
| `/sessions/{id}/incidents` | POST | Bulk post incidents | `server/app/routes/incidents.py` |
| `/teacher/sessions/{id}/detail` | GET | Teacher views session + incidents | `server/app/routes/teacher_reports.py` |

### Database Tables Involved

| Table | What Gets Written |
|-------|-------------------|
| `exam_sessions` | `status` → `aborted_vm` or `aborted_stealth_vm`, `ended_at` set |
| `incident_logs` | Row with `incident_type=VM_DETECTED/STEALTH_VM_DETECTED`, `severity=critical`, forensic columns |

### Client Files

| File | Purpose |
|------|---------|
| `client/app/vm_detect/__init__.py` | Exports both detection functions |
| `client/app/vm_detect/standard.py` | Standard detection (4 checks) |
| `client/app/vm_detect/stealth.py` | Stealth detection (3 checks) |
| `client/app/screens/exam_integrity_check.py` | UI screen running both gates |
| `client/app/config.py` | `SKIP_VM_CHECK` flag for dev mode |

---

## Dev Mode / Testing

Set in `client/.env`:
```
SKIP_VM_CHECK=1
```

When enabled:
- Both gates show "⚠ Skipped (dev mode)" in the UI
- Continue button enables immediately
- No incidents posted, no abort called
- Useful for testing on your own VM during development

---

## Verified Integration Points (Cross-Check)

| What | Status | Evidence |
|------|--------|----------|
| Standard detection on bare metal | ✅ Pass | Returns `is_vm=False`, 0 indicators |
| Stealth detection on bare metal | ✅ Pass | Returns `is_vm=False`, 0 indicators, no RDTSC trigger |
| Incident schema matches server | ✅ | Server expects `type`, `severity`, `description`, `cpu_thermal_value`, `timing_latency_ms` — we send all of these |
| Abort endpoint exists | ✅ | `POST /sessions/{id}/abort` added to `sessions.py` |
| Session status enums exist | ✅ | `aborted_vm`, `aborted_stealth_vm` defined in `server/app/models/enums.py` |
| Incident types registered | ✅ | `VM_DETECTED`, `STEALTH_VM_DETECTED` in `server/app/utils/incident_types.py` |
| Student dashboard handles aborted | ✅ | Shows "Retry Exam" button for `aborted_vm`/`aborted_stealth_vm` |
| Teacher can see incidents | ✅ | `get_session_detail()` returns incidents with `cpu_thermal_value`, `timing_latency_ms` |
| Server accepts incidents on aborted sessions | ✅ | Only `submitted` status rejects incidents (per `incident_service.py` line 31) |
| SKIP_VM_CHECK config exists | ✅ | Defined in `client/app/config.py` |

---

## For Version A vs Version B Builds

For the demo, you need two versions:
- **Version A** = Standard detection only (stealth check disabled)
- **Version B** = Both gates active (full detection)

**Simplest approach:** In `exam_integrity_check.py`, after standard passes and before stealth runs, check an env var:

```python
# In client/.env for Version A:
SKIP_STEALTH_CHECK=1

# In client/.env for Version B (or just don't set it):
SKIP_STEALTH_CHECK=0
```

Or just build two .exe files with different `.env` values baked in. We'll handle this in Part 28 (PyInstaller).

---

## Summary

| Layer | What We Did | Lines of Code |
|-------|-------------|---------------|
| `standard.py` | 4 detection checks | ~220 |
| `stealth.py` | 3 detection checks (thermal + SCSI + RDTSC) | ~330 |
| `exam_integrity_check.py` | Full UI with live status + server integration | ~400 |
| `sessions.py` (abort endpoint) | New POST endpoint | ~50 |
| **Total** | | **~1000 lines** |

All tested on bare metal. Zero false positives. Ready for lockdown (Parts 23-27).
