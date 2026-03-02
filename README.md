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

## 📦 Installation

### Prerequisites
- Python 3.8+
- Windows OS (uses Windows APIs)
- MySQL 8.0+

### Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configure Database

```bash
set DB_HOST=localhost
set DB_USER=exam_user
set DB_PASSWORD=secure_password
set DB_NAME=exam_sentinel_db
```

### Run Application

```bash
# Terminal 1: Start Server
cd server
python main.py --host 0.0.0.0 --port 5000 --debug

# Terminal 2: Start Client
cd client
python main.py
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

## 🔐 Client Application Features

### Exam UI (Tkinter)
- Start/End exam controls
- Real-time security status dashboard
- Process monitoring indicators
- VM detection progress
- Webcam feed display
- Activity logging console

### Process Monitoring
```python
# Detects and terminates forbidden processes
FORBIDDEN_PROCESSES = [
    "cmd.exe", "powershell.exe",
    "vmware.exe", "virtualbox.exe",
    "burp.exe", "wireshark.exe"
]
```

### Webcam Management
- OpenCV camera initialization
- Real-time frame capture
- Face detection (cascades)
- Multiple person detection
- Frame quality analysis

---

## 🔌 Server REST API

### Authentication Endpoints

**Login**
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "student@exam.com",
  "password": "password",
  "machine_id": "DESKTOP-ABC123",
  "exam_code": "CS101_MIDTERM"
}

Response (200):
{
  "success": true,
  "session_token": "jwt_...",
  "student_id": 123
}
```

**Validate Token**
```http
GET /api/auth/validate?token=jwt_...

Response (200):
{ "valid": true, "message": "Token is valid" }
```

### Logging Endpoints

**Submit Logs**
```http
POST /api/logs/submit
Content-Type: application/json

{
  "session_token": "jwt_...",
  "logs": [
    {
      "type": "PROCESS_TERMINATION",
      "severity": "WARNING",
      "message": "Terminated cmd.exe",
      "data": { "process_name": "cmd.exe", "pid": 1234 }
    }
  ]
}

Response (200):
{
  "success": true,
  "logs_received": 1,
  "logs_stored": 1
}
```

**Submit VM Detection Results**
```http
POST /api/logs/vm-detection
Content-Type: application/json

{
  "session_token": "jwt_...",
  "final_score": 0.72,
  "cpu_score": 0.75,
  "thermal_score": 0.65,
  "hardware_score": 0.80,
  "recommendation": "VM suspected"
}

Response (200):
{
  "success": true,
  "action": "WARN"  # or "ALLOW", "BLOCK"
}
```

### Health Check

```http
GET /health
GET /api/status

Response:
{
  "status": "healthy",
  "database": "connected"
}
```

---

## 🗄️ Database Schema

### students
```sql
CREATE TABLE students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### exam_sessions
```sql
CREATE TABLE exam_sessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    exam_name VARCHAR(100),
    start_time TIMESTAMP,
    end_time TIMESTAMP NULL,
    machine_id VARCHAR(100),
    ip_address VARCHAR(45),
    session_token VARCHAR(255) UNIQUE,
    status ENUM('ACTIVE', 'COMPLETED', 'TERMINATED'),
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);
```

### security_logs
```sql
CREATE TABLE security_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    log_type VARCHAR(50),
    severity ENUM('INFO', 'WARNING', 'CRITICAL'),
    message VARCHAR(500),
    data JSON,
    vm_score FLOAT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id)
);
```

### vm_detection_results
```sql
CREATE TABLE vm_detection_results (
    result_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    detection_time TIMESTAMP,
    final_score FLOAT NOT NULL,
    cpu_score FLOAT,
    thermal_score FLOAT,
    hardware_score FLOAT,
    recommendation VARCHAR(200),
    raw_data JSON,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id)
);
```

---

## 📝 Configuration

Key settings in `client/utils/config.py`:

```python
# Exam settings
FULLSCREEN_MODE = True
ALLOW_ALT_TAB = False
ALLOW_TASKBAR = False

# VM detection thresholds
VM_DETECTION_THRESHOLD = 0.65      # Warning threshold
CRITICAL_VM_THRESHOLD = 0.85        # Block threshold

# Monitoring intervals
PROCESS_MONITOR_INTERVAL = 2        # seconds
VM_DETECTION_INTERVAL = 30          # seconds
LOG_SUBMIT_INTERVAL = 30            # seconds

# Webcam
WEBCAM_ENABLED = True
WEBCAM_RESOLUTION = (1280, 720)
WEBCAM_FPS = 30
ENABLE_FACE_DETECTION = True
```

---

## 🔐 Security Best Practices

✅ Never enable DEBUG in production  
✅ Use HTTPS for all API endpoints  
✅ Implement bcrypt for password hashing  
✅ Use parameterized SQL queries  
✅ Rate limiting on auth endpoints  
✅ Token expiration enforcement  
✅ Database encryption at rest  
✅ Comprehensive audit logging  
✅ Input validation on server  
✅ Regular security audits  

---

## 📝 Logging

**Client logs**: `logs/ExamSentinel_*.log`  
**Server logs**: `logs/exam_sentinel_server.log`  

Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

---

## 🧪 Testing Components

```python
# Test VM Detector
from client.detection.vm_detector import VMDetector
detector = VMDetector()
score, results = detector.get_triangulation_score()

# Test Process Monitor
from client.monitoring.process_monitor import ProcessMonitor
monitor = ProcessMonitor()
detected = monitor.detect_forbidden_processes()

# Test Webcam
from client.detection.webcam import WebcamManager
webcam = WebcamManager()
if webcam.initialize_camera():
    webcam.start_streaming()
```

---

## 🚀 Quick Start

```bash
# 1. Install
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure database
set DB_HOST=localhost
set DB_USER=exam_user
set DB_PASSWORD=secure_password

# 3. Run server
cd server && python main.py --debug

# 4. Run client (new terminal)
cd client && python main.py
```

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

---

## 📚 Technical References

- **CPU Timing**: RDTSC analysis, cache behavior, instruction pipelines
- **ACPI**: Thermal zone enumeration, WMI queries, registry inspection
- **Hypervisors**: VMware, VirtualBox, Hyper-V, Xen, QEMU signatures
- **OWASP**: SQL injection, XSS, authentication best practices
- **Security**: Bcrypt, JWT, parameterized queries, rate limiting

---

## 📄 License

MIT License - See LICENSE file

---

## 👥 Authors

ExamSentinel Research Team  
Final Year Project  
Version: 0.1.0  
Last Updated: March 2026

---

## ⚠️ Important Disclaimers

- **Educational Use**: This project is for educational and research purposes
- **Heuristic Nature**: VM detection is heuristic-based; false positives/negatives possible
- **Not Absolute**: Combine with human proctors for critical exams
- **Legal Compliance**: Users must comply with institution policies and local laws
- **No Guarantees**: Authors are not liable for misuse or unauthorized access
- **Development**: Some features are stubs; implement production-grade versions before deployment

---

## 🤝 Contributing

This is a Final Year Project. Contributions should follow academic integrity guidelines.

---

## 📧 Support

For questions or issues, refer to the project documentation or contact the development team.
