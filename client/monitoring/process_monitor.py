"""
Process Monitor Module - Forbidden Process Detection & Termination
===================================================================
Monitors running processes and immediately terminates any forbidden applications.
This ensures exam integrity by preventing code sharing, communication, or assistance.

ARCHITECTURE:
- Periodic polling of running processes using psutil
- Comparison against forbidden process list from config
- Immediate termination of detected processes
- Logging of all termination events

FUTURE ENHANCEMENTS:
- Kernel-level process hooking (via pywin32)
- Prevention of forbidden process startup (before they run)
- Heuristic detection of renamed executables
- Process lineage analysis (detect child processes of forbidden apps)
- Advanced anti-evasion techniques
"""

import psutil
import logging
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from client.utils.config import FORBIDDEN_PROCESSES, SKIP_SECURITY_CHECKS, DEVELOPMENT_MODE


class ProcessMonitor:
    """
    Monitor and enforce process restrictions during exam.
    Continuously scans for and terminates forbidden processes.
    """
    
    def __init__(self):
        """Initialize the process monitor."""
        self.forbidden_processes = [p.lower() for p in FORBIDDEN_PROCESSES]
        self.terminated_processes = []
        self.logger = logging.getLogger(__name__)
        
    def get_running_processes(self) -> List[str]:
        """
        Retrieve list of all currently running process names.
        
        Returns:
            List[str]: List of process executable names (lowercase)
        """
        running = []
        try:
            for proc in psutil.process_iter(['name']):
                try:
                    running.append(proc.info['name'].lower())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            self.logger.error(f"Error retrieving process list: {e}")
        
        return running
    
    def detect_forbidden_processes(self) -> List[Dict]:
        """
        Scan for any forbidden processes currently running.
        
        Returns:
            List[Dict]: List of detected forbidden processes with details
                       Format: [{'name': str, 'pid': int, 'detected_at': timestamp}, ...]
        """
        detected = []
        running = self.get_running_processes()
        
        for forbidden in self.forbidden_processes:
            if forbidden in running:
                # Get the actual process object for more details
                try:
                    for proc in psutil.process_iter(['name', 'pid', 'create_time']):
                        if proc.info['name'].lower() == forbidden:
                            detected.append({
                                'name': proc.info['name'],
                                'pid': proc.info['pid'],
                                'create_time': proc.info['create_time'],
                                'status': 'DETECTED'
                            })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        return detected
    
    def terminate_process(self, process_name: str) -> bool:
        """
        Terminate a process by name.
        
        Args:
            process_name (str): Name of the process to terminate
            
        Returns:
            bool: True if termination successful, False otherwise
        """
        if SKIP_SECURITY_CHECKS and DEVELOPMENT_MODE:
            self.logger.info(f"[DEV] Would terminate: {process_name}")
            return True
        
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == process_name.lower():
                    # First try graceful termination
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                        self.logger.warning(f"✓ Gracefully terminated: {process_name} (PID: {proc.pid})")
                        return True
                    except psutil.TimeoutExpired:
                        # Force kill if graceful termination fails
                        proc.kill()
                        self.logger.warning(f"✓ Force-killed: {process_name} (PID: {proc.pid})")
                        return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self.logger.error(f"Error terminating {process_name}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error terminating {process_name}: {e}")
            return False
        
        return False
    
    def check_and_terminate_forbidden_processes(self) -> Dict:
        """
        Main monitoring function: Detect and immediately terminate forbidden processes.
        
        Returns:
            Dict: Summary of actions taken
                  Format: {
                      'processes_detected': int,
                      'processes_terminated': int,
                      'details': [list of terminated process info]
                  }
        """
        detected = self.detect_forbidden_processes()
        terminated = []
        
        for process_info in detected:
            if self.terminate_process(process_info['name']):
                terminated.append(process_info)
                self.terminated_processes.append(process_info)
        
        summary = {
            'processes_detected': len(detected),
            'processes_terminated': len(terminated),
            'details': terminated,
            'timestamp': __import__('time').time()
        }
        
        if terminated:
            self.logger.critical(
                f"🚨 SECURITY ALERT: Terminated {len(terminated)} forbidden process(es)"
            )
        
        return summary
    
    def get_system_resource_usage(self) -> Dict:
        """
        Get overall system resource usage statistics.
        Useful for detecting resource-intensive monitoring tools.
        
        Returns:
            Dict: System resource statistics
        """
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'process_count': len(psutil.pids()),
            'timestamp': __import__('time').time()
        }
    
    def get_process_info(self, proc_name: str) -> Dict:
        """
        Get detailed information about a specific process.
        
        Args:
            proc_name (str): Name of the process
            
        Returns:
            Dict: Process information or empty dict if not found
        """
        try:
            for proc in psutil.process_iter([
                'name', 'pid', 'status', 'create_time',
                'memory_percent', 'cpu_percent'
            ]):
                if proc.info['name'].lower() == proc_name.lower():
                    return {
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'status': proc.info['status'],
                        'memory_mb': proc.memory_info().rss / (1024 * 1024),
                        'cpu_percent': proc.info['cpu_percent'],
                        'create_time': proc.info['create_time']
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        return {}
    
    def whitelist_check(self, process_name: str) -> bool:
        """
        Check if a process is explicitly whitelisted (always safe).
        
        FUTURE IMPLEMENTATION:
        - Load whitelist from configuration file
        - Only allow essential system processes
        - Reduce false positives with verified safe processes
        
        Args:
            process_name (str): Name of the process to check
            
        Returns:
            bool: True if whitelisted, False otherwise
        """
        # TODO: Implement whitelist configuration
        whitelist = [
            "svchost.exe",
            "explorer.exe",
            "windows_explorer.exe",
            "dwm.exe",  # Desktop Window Manager
            "taskhostw.exe",
            "winlogon.exe",
        ]
        
        return process_name.lower() in whitelist


# ============================================================================
# ADVANCED MONITORING STUBS FOR FUTURE IMPLEMENTATION
# ============================================================================

class AdvancedProcessMonitor(ProcessMonitor):
    """
    Advanced process monitoring with kernel-level hooks.
    
    FUTURE FEATURES:
    - WMI process creation event monitoring
    - Registry key monitoring (new executable registrations)
    - Window title analysis (detect renamed executables)
    - Process lineage tree construction and analysis
    """
    
    def setup_process_creation_hook(self):
        """
        Setup real-time process creation monitoring via WMI.
        Intercepts processes before they fully initialize.
        
        FUTURE IMPLEMENTATION:
        - Use WMI Win32_ProcessStartTrace
        - Catch process at creation time
        - Compare against blocklist before resource allocation
        """
        pass
    
    def analyze_process_lineage(self, process_name: str) -> List[str]:
        """
        Build process family tree to detect suspicious child processes.
        
        Example: If browser.exe spawns cmd.exe, this is suspicious.
        
        Args:
            process_name (str): Root process to analyze
            
        Returns:
            List[str]: Hierarchical list of parent/child processes
        """
        # TODO: Implement full process tree analysis
        pass


if __name__ == "__main__":
    # Test the process monitor
    monitor = ProcessMonitor()
    
    print("\\n=== Process Monitor Self-Test ===\\n")
    
    running = monitor.get_running_processes()
    print(f"Running processes: {len(running)}")
    
    detected = monitor.detect_forbidden_processes()
    print(f"Forbidden processes detected: {len(detected)}")
    if detected:
        for proc in detected:
            print(f"  - {proc['name']} (PID: {proc['pid']})")
    
    resources = monitor.get_system_resource_usage()
    print(f"\\nSystem Resources:")
    print(f"  CPU: {resources['cpu_percent']:.1f}%")
    print(f"  Memory: {resources['memory_percent']:.1f}%")
    print(f"  Processes: {resources['process_count']}")
