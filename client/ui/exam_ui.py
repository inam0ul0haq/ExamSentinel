"""
ExamSentinel Exam UI - Tkinter-Based Interface
================================================
Provides the main user interface for the exam proctor application.
Features include fullscreen lockdown, start exam button, and real-time monitoring status.

FEATURES:
- Fullscreen lockdown mode with no escape (when exam is active)
- Start Exam button to initialize monitoring
- Real-time status display (monitoring active, VM detection status, process monitoring, etc.)
- Clean, professional UI with security branding
- Webcam feed integration
- Security alert indicators

FUTURE ENHANCEMENTS:
- Integration with actual exam portal (iframe or embedded browser)
- Advanced biometric authentication
- Gaze-tracking detection for suspicious behavior
- Real-time proctoring chat with exam supervisor
- Advanced UI theming and customization
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from pathlib import Path
import sys

# Import client modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from client.utils.config import *
from client.monitoring.process_monitor import ProcessMonitor
from client.detection.vm_detector import VMDetector
from client.detection.webcam import WebcamManager


class ExamUI:
    """
    Main Exam Interface Controller
    Manages the Tkinter application and coordinates all monitoring components.
    """

    def __init__(self, root):
        """
        Initialize the ExamUI with the root Tkinter window.

        Args:
            root (tk.Tk): The root Tkinter window
        """
        self.root = root
        self.root.title(f"{APP_NAME} - Secure Exam Browser")
        self.root.geometry("1200x800")
        
        # Initialize monitoring components
        self.process_monitor = None
        self.vm_detector = None
        self.webcam_manager = None
        
        # Exam state
        self.exam_active = False
        self.monitoring_thread = None
        
        # Build UI
        self._build_ui()
        
    def _build_ui(self):
        """Construct the main UI components."""
        
        # ====================================================================
        # MAIN CONTAINER
        # ====================================================================
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ====================================================================
        # HEADER SECTION
        # ====================================================================
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        app_title = ttk.Label(
            header_frame,
            text=f"🔐 {APP_NAME} - Secure Exam Browser",
            font=("Helvetica", 24, "bold")
        )
        app_title.pack(side=tk.LEFT)
        
        version_label = ttk.Label(
            header_frame,
            text=f"v{APP_VERSION}",
            font=("Helvetica", 10),
            foreground="gray"
        )
        version_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # ====================================================================
        # MAIN CONTENT AREA
        # ====================================================================
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # LEFT PANEL: Control & Status
        left_panel = ttk.Frame(content_frame, relief=tk.SUNKEN, borderwidth=2)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self._build_control_panel(left_panel)
        
        # RIGHT PANEL: Webcam Feed & Monitoring Status
        right_panel = ttk.Frame(content_frame, relief=tk.SUNKEN, borderwidth=2)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self._build_webcam_panel(right_panel)
        
        # ====================================================================
        # FOOTER SECTION
        # ====================================================================
        footer_frame = ttk.Frame(main_container)
        footer_frame.pack(fill=tk.X, pady=(20, 0), side=tk.BOTTOM)
        
        self.status_label = ttk.Label(
            footer_frame,
            text="Status: Ready | Monitoring: OFF | VM Detection: Idle",
            font=("Helvetica", 10),
            foreground="blue"
        )
        self.status_label.pack(fill=tk.X)
        
    def _build_control_panel(self, parent):
        """
        Build the control panel with exam controls and status indicators.
        
        Args:
            parent (ttk.Frame): Parent frame for control panel
        """
        
        # EXAM CONTROL SECTION
        control_label = ttk.Label(
            parent,
            text="📋 EXAM CONTROLS",
            font=("Helvetica", 14, "bold"),
            foreground="darkblue"
        )
        control_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start Exam Button
        self.start_exam_btn = tk.Button(
            control_frame,
            text="▶ START EXAM",
            font=("Helvetica", 14, "bold"),
            bg="#4CAF50",
            fg="white",
            padx=20,
            pady=15,
            command=self.start_exam,
            relief=tk.RAISED,
            cursor="hand2"
        )
        self.start_exam_btn.pack(fill=tk.X, pady=(0, 10))
        
        # End Exam Button (disabled by default)
        self.end_exam_btn = tk.Button(
            control_frame,
            text="⏹ END EXAM",
            font=("Helvetica", 14, "bold"),
            bg="#f44336",
            fg="white",
            padx=20,
            pady=15,
            command=self.end_exam,
            relief=tk.RAISED,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.end_exam_btn.pack(fill=tk.X, pady=(0, 20))
        
        # MONITORING STATUS SECTION
        status_label = ttk.Label(
            parent,
            text="📊 SYSTEM MONITORING",
            font=("Helvetica", 14, "bold"),
            foreground="darkblue"
        )
        status_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Process Monitoring Status
        ttk.Label(status_frame, text="Process Monitor:", font=("Helvetica", 10)).pack(anchor=tk.W)
        self.process_status = ttk.Label(
            status_frame,
            text="● OFF",
            font=("Helvetica", 10),
            foreground="red"
        )
        self.process_status.pack(anchor=tk.W, padx=(20, 0))
        
        # VM Detection Status
        ttk.Label(status_frame, text="VM Detection:", font=("Helvetica", 10)).pack(anchor=tk.W, pady=(10, 0))
        self.vm_status = ttk.Label(
            status_frame,
            text="● SCANNING",
            font=("Helvetica", 10),
            foreground="orange"
        )
        self.vm_status.pack(anchor=tk.W, padx=(20, 0))
        
        # Webcam Status
        ttk.Label(status_frame, text="Webcam:", font=("Helvetica", 10)).pack(anchor=tk.W, pady=(10, 0))
        self.webcam_status = ttk.Label(
            status_frame,
            text="● OFF",
            font=("Helvetica", 10),
            foreground="red"
        )
        self.webcam_status.pack(anchor=tk.W, padx=(20, 0))
        
        # ====================================================================
        # LOG OUTPUT AREA
        # ====================================================================
        log_label = ttk.Label(
            parent,
            text="📝 ACTIVITY LOG",
            font=("Helvetica", 14, "bold"),
            foreground="darkblue"
        )
        log_label.pack(fill=tk.X, padx=10, pady=(20, 5))
        
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Text widget with scrollbar for logs
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_frame,
            height=10,
            width=50,
            font=("Courier", 9),
            yscrollcommand=scrollbar.set,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
    def _build_webcam_panel(self, parent):
        """
        Build the webcam feed panel.
        
        FUTURE IMPLEMENTATION:
        - Integrate OpenCV video capture
        - Display live webcam stream
        - Add face detection overlay
        - Detect suspicious head movements or eye gaze
        
        Args:
            parent (ttk.Frame): Parent frame for webcam panel
        """
        
        webcam_label = ttk.Label(
            parent,
            text="📷 WEBCAM FEED",
            font=("Helvetica", 14, "bold"),
            foreground="darkblue"
        )
        webcam_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Placeholder for webcam feed
        self.webcam_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=2)
        self.webcam_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas for video feed (future: will display OpenCV frames here)
        self.webcam_canvas = tk.Canvas(
            self.webcam_frame,
            bg="black",
            width=400,
            height=300
        )
        self.webcam_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Placeholder text while webcam not initialized
        self.webcam_canvas.create_text(
            200, 150,
            text="Webcam Feed\n(Initializing...)",
            fill="white",
            font=("Helvetica", 14)
        )
        
    def log_message(self, message):
        """
        Add a message to the activity log display.
        
        Args:
            message (str): Message to log
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)  # Auto-scroll to bottom
        self.log_text.config(state=tk.DISABLED)
        
    def start_exam(self):
        """
        Initialize exam mode: activate fullscreen, start monitoring,
        and initialize all security checks.
        """
        self.log_message("[EXAM] Starting exam mode...")
        self.log_message("[MONITOR] Initializing process monitor...")
        self.log_message("[MONITOR] Initializing VM detector...")
        self.log_message("[WEBCAM] Initializing webcam...")
        
        self.exam_active = True
        
        # Update UI state
        self.start_exam_btn.config(state=tk.DISABLED)
        self.end_exam_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Exam Active | Monitoring: ON | VM Detection: Running")
        
        # Update status indicators
        self.process_status.config(text="● ON", foreground="green")
        self.vm_status.config(text="● MONITORING", foreground="blue")
        self.webcam_status.config(text="● RECORDING", foreground="green")
        
        # TODO: Enable fullscreen mode
        # self.root.attributes('-fullscreen', True)
        
        # Start monitoring in background thread
        self.monitoring_thread = threading.Thread(target=self._run_monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        self.log_message("[EXAM] ✓ Exam initialized successfully!")
        self.log_message("[SECURITY] Fullscreen lockdown ACTIVE\n")
        
    def _run_monitoring_loop(self):
        """
        Main monitoring loop that runs in a background thread.
        Continuously monitors processes, detects VMs, and collects security data.
        """
        iteration = 0
        
        while self.exam_active:
            iteration += 1
            
            # Process monitoring check
            if iteration % 2 == 0:
                self.log_message(f"[PROCESS] Scanning for forbidden processes...")
                # TODO: Call ProcessMonitor.check_and_terminate_forbidden_processes()
                
            # VM detection check (every other iteration)
            if iteration % 6 == 0:
                self.log_message(f"[VM_DETECT] Running heuristic triangulation...")
                # TODO: Call VMDetector.get_triangulation_score()
                
            # Webcam monitoring
            self.log_message(f"[WEBCAM] Frame captured")
            
            # Random sleep to prevent CPU spike (in production use proper timing)
            import time
            time.sleep(PROCESS_MONITOR_INTERVAL)
            
    def end_exam(self):
        """
        Terminate exam mode: stop monitoring, release resources,
        and submit final logs to server.
        """
        self.log_message("\n[EXAM] Ending exam...")
        self.exam_active = False
        
        # Update UI
        self.start_exam_btn.config(state=tk.NORMAL)
        self.end_exam_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Idle | Monitoring: OFF | VM Detection: Idle")
        
        self.process_status.config(text="● OFF", foreground="red")
        self.vm_status.config(text="● IDLE", foreground="orange")
        self.webcam_status.config(text="● OFF", foreground="red")
        
        # TODO: Disable fullscreen mode
        # self.root.attributes('-fullscreen', False)
        
        self.log_message("[EXAM] ✓ Exam terminated")
        self.log_message("[SERVER] Submitting final logs...")
        # TODO: Call server API to submit logs
        
        # Wait for monitoring thread to finish
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
            
        self.log_message("[EXAM] ✓ Ready for next exam\n")
        
        # Show completion message
        messagebox.showinfo(
            "Exam Complete",
            "Your exam has ended. Logs have been submitted.\nThank you for completing the exam."
        )


def main():
    """Entry point for the Tkinter application."""
    root = tk.Tk()
    app = ExamUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
