"""
Stealth VM Detection Module - Heuristic Triangulation
======================================================
Advanced detection of virtualized/stealth environments through three attack vectors:

1. CPU TIMING ATTACKS (RDTSC Analysis)
   - Measure CPU cycle consistency
   - VMs have exaggerated variance or patterns
   - Uses RDTSC (Read TimeStamp Counter) instruction

2. THERMAL ZONE ANALYSIS (ACPI Thermal Devices)
   - Physical machines typically have multiple thermal zones
   - VMs often have zero or minimal thermal zones
   - Queries Windows WMI for thermal device info

3. HARDWARE ARTIFACT SCANNING
   - MAC addresses (virtual MAC prefixes)
   - Registry keys (hypervisor signatures)
   - Driver presence (VMware, VirtualBox, etc.)
   - BIOS information

HEURISTIC TRIANGULATION:
Combines all three checks with weighted scoring (0.0 to 1.0).
Scores above threshold indicate high VM probability.

RESEARCH NOTES:
This is a foundational implementation. Real-world VM detection requires:
- Timing side-channel analysis
- Privilege escalation for kernel-level checks
- Analysis of CPU cache behavior
- Memory isolation pattern detection
- Interrupt latency analysis
"""

import os
import sys
import ctypes
import logging
import subprocess
from typing import Dict, List, Tuple
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from client.utils.config import (
    WEIGHT_CPU_TIMING,
    WEIGHT_THERMAL_ZONES,
    WEIGHT_HARDWARE_ARTIFACTS,
    VM_DETECTION_THRESHOLD,
    CRITICAL_VM_THRESHOLD,
    RDTSC_SAMPLES,
    RDTSC_VARIANCE_BASELINE,
    RDTSC_ANOMALY_THRESHOLD,
    VIRTUAL_MAC_PREFIXES,
    SUSPICIOUS_DRIVERS,
    HYPERVISOR_REGISTRY_KEYS,
    SKIP_SECURITY_CHECKS,
)


class VMDetector:
    """
    Multi-vector Stealth VM Detection Engine
    Uses heuristic triangulation to identify virtual environments.
    """
    
    def __init__(self):
        """Initialize VM detector with logging."""
        self.logger = logging.getLogger(__name__)
        self.detection_history = []
        
    # ========================================================================
    # CPU TIMING ATTACK DETECTION (RDTSC)
    # ========================================================================
    
    def rdtsc(self) -> int:
        """
        Read the CPU timestamp counter directly.
        
        On physical hardware: Consistent, predictable increments
        On VMs: Often shows anomalous patterns or excessive variance
        
        Returns:
            int: CPU cycle count (may be virtualized)
        """
        # RDTSC assembly instruction: opcode 0x310F
        # This uses ctypes to call a C function that executes RDTSC
        
        try:
            # Define a simple inline assembly function
            # In a real implementation, you would use ctypes and kernel support
            # For now, use a stub that measures time precision
            
            import time
            return int(time.perf_counter() * 1e9)
        except Exception:
            return 0
    
    def measure_cpu_timing_variance(self) -> Tuple[float, List[int]]:
        """
        Measure CPU timing variance through multiple RDTSC samples.
        
        High variance or periodic patterns indicate VM emulation.
        
        Returns:
            Tuple[float, List[int]]: (variance, list of sample deltas)
        """
        samples = []
        
        try:
            # Take multiple RDTSC samples
            for _ in range(RDTSC_SAMPLES):
                t1 = self.rdtsc()
                # Small arithmetic loop to measure consistency
                for i in range(100):
                    _ = i * i
                t2 = self.rdtsc()
                samples.append(t2 - t1)
            
            # Calculate variance
            if samples:
                mean = sum(samples) / len(samples)
                variance = sum((x - mean) ** 2 for x in samples) / len(samples)
                return variance, samples
        except Exception as e:
            self.logger.error(f"RDTSC measurement failed: {e}")
        
        return 0.0, []
    
    def detect_cpu_timing_anomalies(self) -> Tuple[float, Dict]:
        """
        Analyze CPU timing to detect VM emulation.
        
        Returns:
            Tuple[float, Dict]: (confidence score 0-1, analysis details)
        """
        variance, samples = self.measure_cpu_timing_variance()
        
        if not samples:
            return 0.5, {'error': 'Could not measure CPU timing'}
        
        mean = sum(samples) / len(samples)
        
        # Check for anomalies
        anomaly_count = 0
        for sample in samples:
            # Check if sample deviates significantly from mean
            deviation = abs(sample - mean)
            if deviation > (mean * 0.5):  # 50% threshold
                anomaly_count += 1
        
        # Detection heuristics
        anomaly_ratio = anomaly_count / len(samples)
        
        # In a VM, timing is often suspiciously regular or erratic
        # Physical hardware has natural variance but within bounds
        
        details = {
            'mean_cycles': mean,
            'variance': variance,
            'anomaly_ratio': anomaly_ratio,
            'sample_count': len(samples),
            'baseline_cycles': RDTSC_VARIANCE_BASELINE
        }
        
        # Scoring:
        # - High anomaly ratio = likely VM
        # - Variance too low = likely VM (emulation compensates)
        # - Variance baseline mismatch = likely VM
        
        if variance < (RDTSC_VARIANCE_BASELINE * 0.1):
            # Suspiciously low variance
            score = 0.7
        elif anomaly_ratio > 0.5:
            # High anomaly ratio
            score = 0.6
        elif variance > (RDTSC_VARIANCE_BASELINE * 5):
            # Suspiciously high variance
            score = 0.5
        else:
            # Normal variance
            score = 0.2
        
        self.logger.info(f"CPU Timing Analysis - Score: {score:.2f}")
        
        return score, details
    
    # ========================================================================
    # THERMAL ZONE ANALYSIS
    # ========================================================================
    
    def detect_thermal_zones(self) -> Tuple[float, Dict]:
        """
        Analyze ACPI thermal zones to detect VM environment.
        
        LOGIC:
        - Physical hardware: 1-5+ thermal zones
        - VMs: Often 0 or 1 minimal zone
        
        Returns:
            Tuple[float, Dict]: (confidence score 0-1, thermal device info)
        """
        thermal_info = {
            'zone_count': 0,
            'zones': [],
            'method': 'wmi_query',
            'error': None
        }
        
        try:
            # Try WMI query for thermal information
            # This requires elevated privileges
            
            thermal_zones = self._query_wmi_thermal_zones()
            thermal_info['zone_count'] = len(thermal_zones)
            thermal_info['zones'] = thermal_zones
            
            if not thermal_zones:
                self.logger.warning("⚠ No thermal zones detected (VM indicator)")
                score = 0.8
            elif len(thermal_zones) == 1:
                self.logger.warning("⚠ Only 1 thermal zone (possible VM)")
                score = 0.5
            else:
                self.logger.info(f"✓ {len(thermal_zones)} thermal zones detected (physical hardware likely)")
                score = 0.1
        
        except Exception as e:
            self.logger.error(f"Thermal zone detection failed: {e}")
            thermal_info['error'] = str(e)
            # Default to moderate suspicion if detection fails
            score = 0.4
        
        self.logger.info(f"Thermal Analysis - Score: {score:.2f}")
        
        return score, thermal_info
    
    def _query_wmi_thermal_zones(self) -> List[str]:
        """
        Query Windows WMI for thermal zone devices.
        
        FUTURE IMPLEMENTATION:
        Use pywin32's WMI module to query:
        - Win32_SystemEnclosure
        - Win32_TemperatureProbe
        - ACPI thermal devices
        
        Returns:
            List[str]: Detected thermal zones
        """
        zones = []
        
        try:
            # Attempt to import WMI
            try:
                import wmi
            except ImportError:
                # WMI not available, try registry audit
                return self._audit_thermal_registry()
            
            # Query WMI for thermal devices
            # TODO: Implement WMI queries when pywin32 is available
            # c = wmi.WMI()
            # for thermal in c.query("SELECT * FROM Win32_TemperatureProbe"):
            #     zones.append(thermal.Description)
            
            self.logger.debug("WMI thermal query (stub)")
            
        except Exception as e:
            self.logger.error(f"WMI thermal query error: {e}")
        
        return zones
    
    def _audit_thermal_registry(self) -> List[str]:
        """
        Query Windows Registry for thermal zone information.
        
        FUTURE IMPLEMENTATION:
        - Check HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Enum\\
        - Look for thermal device entries
        - Build thermal zone list from registry
        
        Returns:
            List[str]: Registry-based thermal zones
        """
        # TODO: Implement registry queries using winreg module
        return []
    
    # ========================================================================
    # HARDWARE ARTIFACT SCANNING
    # ========================================================================
    
    def detect_hardware_artifacts(self) -> Tuple[float, Dict]:
        """
        Scan for virtual hardware artifacts (MAC addresses, drivers, BIOS).
        
        Returns:
            Tuple[float, Dict]: (confidence score 0-1, detected artifacts)
        """
        artifacts = {
            'virtual_mac_addresses': [],
            'suspicious_drivers': [],
            'hypervisor_registry_keys': [],
            'bios_info': {},
            'total_artifacts': 0
        }
        
        # Check MAC addresses
        mac_artifacts = self._scan_mac_addresses()
        artifacts['virtual_mac_addresses'] = mac_artifacts
        
        # Check for suspicious drivers
        driver_artifacts = self._scan_drivers()
        artifacts['suspicious_drivers'] = driver_artifacts
        
        # Check hypervisor registry keys
        registry_artifacts = self._scan_hypervisor_registry()
        artifacts['hypervisor_registry_keys'] = registry_artifacts
        
        # Get BIOS info
        bios_info = self._get_bios_info()
        artifacts['bios_info'] = bios_info
        
        # Count total artifacts
        total_artifacts = (
            len(mac_artifacts) +
            len(driver_artifacts) +
            len(registry_artifacts)
        )
        artifacts['total_artifacts'] = total_artifacts
        
        # Scoring
        # Each artifact is a strong indicator of virtualization
        if total_artifacts >= 3:
            score = 0.9
        elif total_artifacts == 2:
            score = 0.7
        elif total_artifacts == 1:
            score = 0.4
        else:
            score = 0.1
        
        self.logger.info(
            f"Hardware Artifacts - Found {total_artifacts} artifacts - Score: {score:.2f}"
        )
        
        return score, artifacts
    
    def _scan_mac_addresses(self) -> List[str]:
        """
        Scan network adapters for virtual MAC address prefixes.
        
        Returns:
            List[str]: Detected virtual MAC addresses
        """
        virtual_macs = []
        
        try:
            import uuid
            
            for mac in uuid.getnode():
                # Convert MAC to standard format
                mac_str = ':'.join(f'{byte:02x}' for byte in mac.to_bytes(6, 'big'))
                
                # Check against known virtual prefixes
                for virtual_prefix in VIRTUAL_MAC_PREFIXES:
                    if mac_str.startswith(virtual_prefix.lower()):
                        virtual_macs.append(mac_str)
                        self.logger.warning(f"🚨 Virtual MAC detected: {mac_str}")
        
        except Exception as e:
            self.logger.error(f"MAC address scan failed: {e}")
        
        return virtual_macs
    
    def _scan_drivers(self) -> List[str]:
        """
        Scan system drivers for known hypervisor/VM drivers.
        
        Returns:
            List[str]: Detected suspicious drivers
        """
        suspicious = []
        
        try:
            # Check Windows System32\\drivers directory
            drivers_dir = Path("C:\\Windows\\System32\\drivers")
            
            if drivers_dir.exists():
                for driver_name in SUSPICIOUS_DRIVERS:
                    driver_path = drivers_dir / driver_name
                    if driver_path.exists():
                        suspicious.append(driver_name)
                        self.logger.warning(f"🚨 Suspicious driver found: {driver_name}")
        
        except Exception as e:
            self.logger.error(f"Driver scan failed: {e}")
        
        return suspicious
    
    def _scan_hypervisor_registry(self) -> List[str]:
        """
        Scan Windows Registry for hypervisor signatures.
        
        FUTURE IMPLEMENTATION:
        - Use winreg module to query registry keys
        - Check for VMware, VirtualBox, Hyper-V identifiers
        - Verify BIOS and system manufacturer values
        
        Returns:
            List[str]: Detected hypervisor registry keys
        """
        detected_keys = []
        
        try:
            import winreg
            
            for reg_key in HYPERVISOR_REGISTRY_KEYS:
                try:
                    # Parse registry key
                    parts = reg_key.split('\\')
                    hive = getattr(winreg, parts[0].split('_')[1].upper() + "_LOCAL_MACHINE")
                    path = '\\'.join(parts[1:])
                    
                    with winreg.OpenKey(hive, path) as key:
                        value, _ = winreg.QueryValueEx(key, parts[-1])
                        
                        # Check for VM signatures in the value
                        if self._is_vm_signature(value):
                            detected_keys.append(reg_key)
                            self.logger.warning(f"🚨 VM signature in registry: {value}")
                except (FileNotFoundError, OSError):
                    pass
        
        except Exception as e:
            self.logger.error(f"Registry scan failed: {e}")
        
        return detected_keys
    
    def _is_vm_signature(self, value: str) -> bool:
        """
        Check if a registry value contains VM signatures.
        
        Args:
            value (str): Registry value to check
            
        Returns:
            bool: True if VM signature detected
        """
        vm_signatures = [
            'vmware', 'virtualbox', 'qemu', 'xen', 'hyper-v',
            'parallels', 'virtual', 'hypervisor'
        ]
        
        value_lower = str(value).lower()
        return any(sig in value_lower for sig in vm_signatures)
    
    def _get_bios_info(self) -> Dict:
        """
        Retrieve BIOS and system information.
        
        Returns:
            Dict: BIOS information
        """
        bios_info = {}
        
        try:
            import platform
            
            bios_info = {
                'system': platform.system(),
                'processor': platform.processor(),
                'machine': platform.machine(),
                'platform': platform.platform(),
                'hostname': os.environ.get('COMPUTERNAME', 'UNKNOWN')
            }
        
        except Exception as e:
            self.logger.error(f"BIOS info retrieval failed: {e}")
        
        return bios_info
    
    # ========================================================================
    # HEURISTIC TRIANGULATION SCORE
    # ========================================================================
    
    def get_triangulation_score(self) -> Tuple[float, Dict]:
        """
        Combine all three detection vectors into unified VM probability score.
        
        METHODOLOGY:
        1. Run CPU timing analysis → score 0-1
        2. Run thermal zone analysis → score 0-1
        3. Run hardware artifact scan → score 0-1
        4. Weighted average: (CPU*0.4) + (Thermal*0.35) + (Hardware*0.25)
        
        Result Interpretation:
        - 0.0-0.33: Physical hardware likely
        - 0.34-0.65: Uncertain or mixed results
        - 0.66-0.85: VM suspected
        - 0.86-1.0: VM detected with high confidence
        
        Returns:
            Tuple[float, Dict]: (final_score, detailed_results)
        """
        
        self.logger.info("\\n" + "="*60)
        self.logger.info("STARTING HEURISTIC TRIANGULATION ANALYSIS")
        self.logger.info("="*60)
        
        # Component 1: CPU Timing
        cpu_score, cpu_details = self.detect_cpu_timing_anomalies()
        
        # Component 2: Thermal Zones
        thermal_score, thermal_details = self.detect_thermal_zones()
        
        # Component 3: Hardware Artifacts
        hw_score, hw_details = self.detect_hardware_artifacts()
        
        # Calculate weighted triangulation score
        final_score = (
            cpu_score * WEIGHT_CPU_TIMING +
            thermal_score * WEIGHT_THERMAL_ZONES +
            hw_score * WEIGHT_HARDWARE_ARTIFACTS
        )
        
        results = {
            'final_score': final_score,
            'cpu_timing': {
                'score': cpu_score,
                'details': cpu_details
            },
            'thermal_zones': {
                'score': thermal_score,
                'details': thermal_details
            },
            'hardware_artifacts': {
                'score': hw_score,
                'details': hw_details
            },
            'analysis_timestamp': __import__('time').time(),
            'recommendation': self._score_interpretation(final_score)
        }
        
        # Log results
        self._log_triangulation_results(final_score, results)
        
        # Store in history
        self.detection_history.append(results)
        
        return final_score, results
    
    def _score_interpretation(self, score: float) -> str:
        """
        Interpret the triangulation score with actionable recommendation.
        
        Args:
            score (float): Triangulation score (0-1)
            
        Returns:
            str: Interpretation and recommendation
        """
        if score >= CRITICAL_VM_THRESHOLD:
            return "CRITICAL: VM DETECTED - Exam MUST be terminated"
        elif score >= VM_DETECTION_THRESHOLD:
            return "WARNING: VM suspected - Proceed with caution"
        elif score >= 0.5:
            return "CAUTION: Mixed indicators - Monitor closely"
        else:
            return "OK: Physical hardware likely - Exam can proceed"
    
    def _log_triangulation_results(self, final_score: float, results: Dict):
        """
        Log triangulation analysis results in readable format.
        
        Args:
            final_score (float): Final triangulation score
            results (Dict): Detailed results dictionary
        """
        cpu_score = results['cpu_timing']['score']
        thermal_score = results['thermal_zones']['score']
        hw_score = results['hardware_artifacts']['score']
        
        self.logger.info("\\n" + "-"*60)
        self.logger.info("TRIANGULATION RESULTS:")
        self.logger.info("-"*60)
        self.logger.info(f"CPU Timing Score:      {cpu_score:.2f} (weight: {WEIGHT_CPU_TIMING})")
        self.logger.info(f"Thermal Zones Score:   {thermal_score:.2f} (weight: {WEIGHT_THERMAL_ZONES})")
        self.logger.info(f"Hardware Artifacts:    {hw_score:.2f} (weight: {WEIGHT_HARDWARE_ARTIFACTS})")
        self.logger.info("-"*60)
        self.logger.info(f"FINAL TRIANGULATION:   {final_score:.2f}")
        self.logger.info(f"THRESHOLD (WARNING):   {VM_DETECTION_THRESHOLD:.2f}")
        self.logger.info(f"THRESHOLD (CRITICAL):  {CRITICAL_VM_THRESHOLD:.2f}")
        self.logger.info("-"*60)
        self.logger.info(f"RECOMMENDATION: {results['recommendation']}")
        self.logger.info("="*60 + "\\n")


# ============================================================================
# UTILITY FUNCTIONS FOR VM DETECTION
# ============================================================================

def is_likely_vm(score: float) -> bool:
    """
    Simple boolean VM detection based on score.
    
    Args:
        score (float): Triangulation score
        
    Returns:
        bool: True if VM is likely
    """
    return score >= VM_DETECTION_THRESHOLD


def get_detection_confidence(score: float) -> str:
    """
    Get human-readable confidence level.
    
    Args:
        score (float): Triangulation score
        
    Returns:
        str: Confidence description
    """
    if score >= 0.9:
        return "VERY HIGH"
    elif score >= 0.75:
        return "HIGH"
    elif score >= 0.6:
        return "MODERATE"
    elif score >= 0.4:
        return "LOW"
    else:
        return "VERY LOW"


if __name__ == "__main__":
    # Test the VM detector
    detector = VMDetector()
    
    print("\\n=== Stealth VM Detection Self-Test ===\\n")
    
    # Run triangulation analysis
    final_score, results = detector.get_triangulation_score()
    
    print(f"Final Score: {final_score:.2f}")
    print(f"Confidence: {get_detection_confidence(final_score)}")
    print(f"Is VM: {is_likely_vm(final_score)}")
