# ExamSentinel - Secure Exam Desktop Browser with Stealth VM Detection

A comprehensive Final Year Project designed to detect cheating during remote exams through advanced security monitoring and stealth/hardened virtual machine detection using heuristic triangulation.

## 📋 Project Overview

**ExamSentinel** is a dual-component system:

1. **Client-Side Desktop Browser**: Tkinter-based secure exam application with fullscreen lockdown, process monitoring, and webcam proctoring
2. **Server-Side REST API Backend**: Flask application for authentication, session management, security logging, and VM detection

---

## ✨ Key Features

### Client-Side
✅ Tkinter fullscreen lockdown mode  
✅ Forbidden process detection & termination  
✅ Live webcam monitoring for proctoring  
✅ Real-time security event logging  
✅ Comprehensive system monitoring  

### VM Detection (Core Research)
✅ CPU Timing Attack Analysis (RDTSC)  
✅ Thermal Zone Detection (ACPI)  
✅ Hardware Artifact Scanning (MAC, drivers, registry)  
✅ Heuristic Triangulation Scoring (0-1 scale)  
✅ Weighted confidence calculation  

### Server-Side
✅ RESTful API for client communication  
✅ Student authentication with JWT tokens  
✅ MySQL database integration  
✅ Real-time security log collection  
✅ VM detection result processing  

---

## 🏗️ Project Structure

```
ExamSentinel/
├── client/
│   ├── main.py                      # Entry point
│   ├── ui/
│   │   └── exam_ui.py               # Tkinter UI
│   ├── monitoring/
│   │   └── process_monitor.py       # Process management
│   ├── detection/
│   │   ├── vm_detector.py           # Heuristic triangulation
│   │   └── webcam.py                # OpenCV webcam
│   └── utils/
│       └── config.py                # Configuration
│
├── server/
│   ├── main.py                      # Flask entry point
│   ├── routes/
│   │   ├── auth.py                  # Authentication
│   │   └── logs.py                  # Logging
│   └── database/
│       └── db.py                    # MySQL connection
│
├── requirements.txt
├── README.md
└── LICENSE
```

---

## 🧠 Stealth VM Detection Architecture

### Heuristic Triangulation Score

The system combines three independent detection vectors with weighted averaging:

```
Final Score = (CPU × 0.40) + (Thermal × 0.35) + (Hardware × 0.25)
```

### Vector 1: CPU Timing Analysis (40%)
- **Method**: RDTSC (Read TimeStamp Counter) consistency analysis
- **Logic**: Physical CPUs have natural variance; VMs show anomalies
- **Implementation**: 100 samples, measure cycle deltas, detect patterns
- **Detection**: High variance drift or suspicious regularity = VM

### Vector 2: Thermal Zone Detection (35%)
- **Method**: Query Windows WMI for ACPI thermal devices
- **Logic**: Physical hardware: 1-5 zones; VMs: 0-1 minimal zones
- **Implementation**: Win32_TemperatureProbe queries, registry audit
- **Detection**: Zero/minimal zones = strong VM indicator

### Vector 3: Hardware Artifacts (25%)
- **Method**: Scan for virtual hardware signatures
- **Logic**: VMs leave fingerprints (MAC addresses, drivers, registry)
- **Implementation**: 
  - Virtual MAC prefixes: 00:0C:29 (VMware), 08:00:27 (VirtualBox), etc.
  - Suspicious drivers: vmci.sys, VBoxGuest.sys, VBoxMouse.sys
  - Registry keys: SystemManufacturer, BIOS information
- **Detection**: Each artifact increases score by ~0.2

### Scoring Interpretation

| Score Range | Status | Action |
|-------------|--------|--------|
| 0.00-0.33 | Physical Hardware | ✅ Exam Allowed |
| 0.34-0.65 | Uncertain/Mixed | ⚠️ Monitor Closely |
| 0.66-0.85 | VM Suspected | ⚠️ Proceed with Caution |
| 0.86-1.00 | VM Detected | 🚫 Block Exam |

---

## 🔄 Typical Exam Flow

1. **Student launches** exam_ui.py
2. **Enters credentials** and exam code
3. **Client sends** login request to server
4. **Server validates** and returns session token
5. **Student clicks** "Start Exam"
6. **Client initializes**:
   - Fullscreen lockdown
   - Process monitoring (checks every 2 seconds)
   - VM detection (runs every 30 seconds)
   - Webcam streaming
7. **Continuous monitoring**:
   - Forbidden processes auto-terminated
   - VM score continuously updated
   - Webcam feed being recorded
   - Logs buffered locally
8. **Every 30 seconds**: Logs submitted to server
9. **Student clicks** "End Exam"
10. **System sends** final logs and VM results
11. **Server processes** and stores all data
12. **Proctors review** logs and VM detection results