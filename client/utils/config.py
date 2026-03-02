"""
Configuration Module for ExamSentinel Client
==============================================
Centralized configuration management for the exam client application.
Includes system settings, thresholds, and hardcoded security parameters.
"""

import os
from pathlib import Path

# ============================================================================
# APPLICATION SETTINGS
# ============================================================================

APP_NAME = "ExamSentinel"
APP_VERSION = "0.1.0"
DEBUG_MODE = False

# ============================================================================
# SERVER CONFIGURATION
# ============================================================================

# Backend server URL for API communication
SERVER_BASE_URL = os.getenv("SERVER_URL", "http://localhost:5000")
SERVER_AUTH_ENDPOINT = f"{SERVER_BASE_URL}/api/auth/login"
SERVER_LOG_ENDPOINT = f"{SERVER_BASE_URL}/api/logs/submit"

# Request timeouts (in seconds)
REQUEST_TIMEOUT = 10
LOG_SUBMIT_INTERVAL = 30  # Submit logs every 30 seconds

# ============================================================================
# EXAM LOCKDOWN SETTINGS
# ============================================================================

# Fullscreen mode configuration
FULLSCREEN_MODE = True
ALLOW_TASKBAR = False
ALLOW_ALT_TAB = False
ALLOW_SCREENSHOT = False

# Forbidden processes that trigger immediate termination
FORBIDDEN_PROCESSES = [
    "cmd.exe",
    "powershell.exe",
    "notepad.exe",
    "regedit.exe",
    "taskmgr.exe",
    "vmware.exe",
    "virtualbox.exe",
    "hyperv.exe",
    "qemu.exe",
    "vbox.exe",
    "vmx.exe",
    "wireshark.exe",
    "burp.exe",
    "chrome.exe",  # Browsers other than exam browser
    "firefox.exe",
    "opera.exe",
]

# ============================================================================
# VM DETECTION THRESHOLDS
# ============================================================================

# Heuristic Triangulation scoring configuration
# Scores range from 0.0 (definitely not a VM) to 1.0 (definitely a VM)

# Individual check weightings
WEIGHT_CPU_TIMING = 0.4      # CPU timing attacks (RDTSC)
WEIGHT_THERMAL_ZONES = 0.35  # Thermal zone analysis
WEIGHT_HARDWARE_ARTIFACTS = 0.25  # Hardware artifact scanning

# Decision thresholds
VM_DETECTION_THRESHOLD = 0.65  # Score above this = suspected VM
CRITICAL_VM_THRESHOLD = 0.85   # Score above this = definitely VM

# CPU Timing Attack Detection
RDTSC_VARIANCE_BASELINE = 1000  # Expected variance in CPU cycles (baseline system)
RDTSC_SAMPLES = 100            # Number of RDTSC samples to collect
RDTSC_ANOMALY_THRESHOLD = 2.5  # Standard deviation multiplier for anomaly

# Thermal Zone Analysis
MIN_THERMAL_ZONES = 1  # Minimum expected thermal zones on physical hardware
THERMAL_ZONE_CHECK_ENABLED = True

# Hardware Artifact Scanning
HYPERVISOR_REGISTRY_KEYS = [
    r"HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\BIOS\SystemManufacturer",
    r"HKEY_LOCAL_MACHINE\SYSTEM\HardwareConfig\LastConfig",
]

VIRTUAL_MAC_PREFIXES = [
    "00:0C:29",  # VMware
    "00:1C:42",  # Parallels
    "52:54:00",  # QEMU
    "08:00:27",  # VirtualBox
    "00:16:3E",  # Xen
]

SUSPICIOUS_DRIVERS = [
    "vmci.sys",      # VMware
    "vmmouse.sys",   # VMware
    "vmxnet3.sys",   # VMware
    "VBoxVideoGuest", # VirtualBox
    "VBoxMouse.sys",  # VirtualBox
    "VBoxGuest.sys",  # VirtualBox
    "xenfilt.sys",   # Xen
]

# ============================================================================
# WEBCAM CONFIGURATION
# ============================================================================

WEBCAM_ENABLED = True
WEBCAM_INDEX = 0  # Default camera device index
WEBCAM_RESOLUTION = (1280, 720)
WEBCAM_FPS = 30
WEBCAM_CHECK_INTERVAL = 5  # Check for webcam every 5 seconds
ENABLE_FACE_DETECTION = True  # Requires advanced implementation

# ============================================================================
# LOGGING AND MONITORING
# ============================================================================

LOG_DIRECTORY = Path.cwd() / "logs"
LOG_DIRECTORY.mkdir(exist_ok=True)

# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = "INFO"

# Monitoring intervals (in seconds)
PROCESS_MONITOR_INTERVAL = 2
SYSTEM_MONITOR_INTERVAL = 5  # Monitor CPU, memory, etc.
VM_DETECTION_INTERVAL = 30   # Run full VM detection check every 30 seconds

# Store logs locally before sending to server
MAX_LOCAL_LOGS = 500
LOG_RETENTION_DAYS = 30

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

# Whether to require authentication before starting exam
REQUIRE_AUTHENTICATION = True

# Session token validation
SESSION_TIMEOUT = 3600  # 1 hour in seconds
TOKEN_VALIDATION_INTERVAL = 60  # Re-validate every 60 seconds

# Crash if VM is detected (set to False for development/testing)
CRASH_ON_VM_DETECTION = True

# ============================================================================
# DEVELOPMENT/TESTING MODE
# ============================================================================

# Enable this to bypass strict security checks (DO NOT use in production)
DEVELOPMENT_MODE = False

# Disables VM detection and process termination for testing
SKIP_SECURITY_CHECKS = False

# Print debug information to console
VERBOSE_LOGGING = False

print(f"[CONFIG] {APP_NAME} v{APP_VERSION} configuration loaded.")
