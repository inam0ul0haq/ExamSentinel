"""
Stealth VM Detection Module.

Catches hardened/sanitized VMs where standard guest-tool indicators have
been removed or spoofed. Uses hardware-level signals that cannot be faked
from user-mode:

  1. Thermal zone absence — real PCs always have temp sensors; VMs don't
  2. SCSI disk identifier — virtual disk name survives GA removal + BIOS spoofing
  3. RDTSC timing around CPUID — hypervisors trap CPUID and add cycle latency

Returns a structured verdict: {is_vm, vm_type, indicators[]}.
"""

from __future__ import annotations

import logging
import platform
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


def _check_thermal_zone() -> List[Dict[str, Any]]:
    """Check for thermal sensor presence via WMI.

    Real machines always expose at least one thermal zone with varying
    temperature readings. VMs typically have zero thermal zones or return
    a constant junk value (e.g. exactly 300K / 26.85C).
    """
    indicators = []
    if platform.system() != "Windows":
        return indicators
    try:
        import wmi
        w = wmi.WMI(namespace="root\\WMI")
        zones = w.MSAcpi_ThermalZoneTemperature()

        if not zones:
            # No thermal zones at all — strong VM signal
            indicators.append({
                "category": "thermal",
                "name": "no_thermal_zone",
                "evidence": "No MSAcpi_ThermalZoneTemperature instances found",
                "vm_type": "unknown_hypervisor",
                "cpu_thermal_value": None,
            })
        else:
            # Check if temperature is constant/implausible
            temps = []
            for zone in zones:
                try:
                    # WMI returns temperature in tenths of Kelvin
                    temp_k = zone.CurrentTemperature / 10.0
                    temp_c = temp_k - 273.15
                    temps.append(temp_c)
                except (AttributeError, TypeError):
                    continue

            if temps:
                # Check for implausibly constant value (exactly 26.85C = 300K)
                # or all temps identical (no variation)
                all_same = len(set(round(t, 1) for t in temps)) == 1
                known_stub = any(abs(t - 26.85) < 0.5 for t in temps)

                if all_same and known_stub:
                    indicators.append({
                        "category": "thermal",
                        "name": "constant_thermal_stub",
                        "evidence": f"Temperature constant at {temps[0]:.1f}C (stub value)",
                        "vm_type": "unknown_hypervisor",
                        "cpu_thermal_value": temps[0],
                    })

    except ImportError:
        logger.debug("wmi module not available, skipping thermal check")
    except Exception as e:
        # Common: "Access denied" if not admin, or namespace doesn't exist
        # On VMs, this exception itself is evidence (no thermal WMI provider)
        error_msg = str(e).lower()
        if "not supported" in error_msg or "invalid namespace" in error_msg or "not found" in error_msg:
            indicators.append({
                "category": "thermal",
                "name": "thermal_wmi_unavailable",
                "evidence": f"Thermal WMI query failed: {e}",
                "vm_type": "unknown_hypervisor",
                "cpu_thermal_value": None,
            })
        else:
            logger.debug(f"Thermal check error: {e}")
    return indicators


def _check_scsi_disk() -> List[Dict[str, Any]]:
    """Check SCSI disk identifier in registry.

    Virtual disk controllers report identifiers like 'VBOX HARDDISK' or
    'VMware Virtual disk' in the registry. These survive Guest Additions
    removal and BIOS string spoofing because they come from the virtual
    storage controller firmware, not from installed tools.
    """
    indicators = []
    if platform.system() != "Windows":
        return indicators

    VM_DISK_STRINGS = {
        "vbox": "virtualbox",
        "virtualbox": "virtualbox",
        "vmware": "vmware",
        "virtual disk": "vmware",
        "qemu": "qemu",
        "virtio": "qemu",
    }

    try:
        import winreg

        # Scan SCSI device map
        scsi_base = r"HARDWARE\DEVICEMAP\Scsi"
        try:
            scsi_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, scsi_base)
        except (FileNotFoundError, OSError):
            return indicators

        # Walk through Scsi Port X\Scsi Bus Y\Target Id Z\Logical Unit Id W
        def _scan_key(key, path=""):
            try:
                # Check values at this level
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        if isinstance(value, str):
                            val_lower = value.lower()
                            for pattern, vm_type in VM_DISK_STRINGS.items():
                                if pattern in val_lower:
                                    indicators.append({
                                        "category": "scsi_disk",
                                        "name": name,
                                        "evidence": f"{path}\\{name} = {value}",
                                        "vm_type": vm_type,
                                    })
                                    break
                        i += 1
                    except OSError:
                        break

                # Recurse into subkeys
                j = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, j)
                        subkey = winreg.OpenKey(key, subkey_name)
                        _scan_key(subkey, f"{path}\\{subkey_name}")
                        winreg.CloseKey(subkey)
                        j += 1
                    except OSError:
                        break
            except Exception:
                pass

        _scan_key(scsi_key, scsi_base)
        winreg.CloseKey(scsi_key)

    except ImportError:
        logger.debug("winreg not available, skipping SCSI check")
    except Exception as e:
        logger.debug(f"SCSI disk check error: {e}")
    return indicators


def _check_rdtsc_timing() -> List[Dict[str, Any]]:
    """Measure RDTSC timing around CPUID to detect hypervisor trap overhead.

    On bare metal, CPUID takes ~50-150 cycles. On a hypervisor it traps
    and takes 1000-10000+ cycles. We run multiple iterations, take the
    median, and compare against a threshold of 500 cycles.

    This works on x86-64 Windows 10/11 in VirtualBox/VMware/Hyper-V.
    The VBoxManage stealth commands cannot hide this — it's a fundamental
    property of how CPU virtualization works.
    """
    indicators = []
    if platform.system() != "Windows" or platform.machine() not in ("AMD64", "x86_64"):
        return indicators

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.VirtualAlloc.argtypes = [
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        kernel32.VirtualAlloc.restype = wintypes.LPVOID
        kernel32.VirtualFree.argtypes = [
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.DWORD,
        ]
        kernel32.VirtualFree.restype = wintypes.BOOL

        # Constants for VirtualAlloc
        MEM_COMMIT = 0x1000
        MEM_RESERVE = 0x2000
        MEM_RELEASE = 0x8000
        PAGE_EXECUTE_READWRITE = 0x40

        # x86-64 machine code:
        # RDTSC; SHL RDX,32; OR RAX,RDX; MOV R8,RAX  (save start TSC in R8)
        # PUSH RBX; XOR EAX,EAX; CPUID; POP RBX        (CPUID leaf 0 — triggers trap)
        # RDTSC; SHL RDX,32; OR RAX,RDX               (end TSC in RAX)
        # SUB RAX,R8                                    (delta = end - start)
        # RET
        shellcode = bytes([
            0x0F, 0x31,                         # RDTSC
            0x48, 0xC1, 0xE2, 0x20,             # SHL RDX, 32
            0x48, 0x09, 0xD0,                   # OR RAX, RDX
            0x49, 0x89, 0xC0,                   # MOV R8, RAX
            0x53,                               # PUSH RBX (nonvolatile on Win64)
            0x31, 0xC0,                         # XOR EAX, EAX
            0x0F, 0xA2,                         # CPUID
            0x5B,                               # POP RBX
            0x0F, 0x31,                         # RDTSC
            0x48, 0xC1, 0xE2, 0x20,             # SHL RDX, 32
            0x48, 0x09, 0xD0,                   # OR RAX, RDX
            0x4C, 0x29, 0xC0,                   # SUB RAX, R8
            0xC3,                               # RET
        ])

        # Allocate executable memory
        buf = kernel32.VirtualAlloc(
            None, len(shellcode), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
        )
        if not buf:
            return indicators

        try:
            # Write shellcode
            ctypes.memmove(buf, shellcode, len(shellcode))

            # Cast to callable function (returns uint64)
            func_type = ctypes.CFUNCTYPE(ctypes.c_uint64)
            measure_fn = func_type(buf)

            # Run multiple iterations and collect deltas
            deltas = []
            for _ in range(200):
                delta = measure_fn()
                if delta > 0 and delta < 1000000:  # sanity check
                    deltas.append(delta)

            if deltas:
                # Take the median
                deltas.sort()
                median_delta = deltas[len(deltas) // 2]

                # Threshold: bare metal ~50-2000 cycles (varies widely by CPU
                # microarch — Intel Alder/Raptor Lake hybrid cores and AMD
                # Zen4 can hit 1500-2000 on real hardware due to P/E core
                # scheduling and power-state transitions).
                # VMs are consistently 3000-50000+.
                # Use 2500 to avoid false positives on modern CPUs.
                THRESHOLD = 2500

                if median_delta > THRESHOLD:
                    indicators.append({
                        "category": "rdtsc_timing",
                        "name": "cpuid_trap_latency",
                        "evidence": f"Median CPUID cycle cost: {median_delta} cycles (threshold: {THRESHOLD})",
                        "vm_type": "unknown_hypervisor",
                        "timing_latency_cycles": median_delta,
                    })

        finally:
            # Free the allocated memory
            kernel32.VirtualFree(buf, 0, MEM_RELEASE)

    except Exception as e:
        logger.debug(f"RDTSC timing check error: {e}")

    return indicators


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_stealth_vm() -> Dict[str, Any]:
    """Run all stealth VM detection checks.

    Returns:
        {
            "is_vm": bool,
            "vm_type": str or None,
            "indicators": [{"category", "name", "evidence", "vm_type", ...}, ...],
            "cpu_thermal_value": float or None  (from thermal check if present)
        }
    """
    all_indicators: List[Dict[str, Any]] = []

    all_indicators.extend(_check_thermal_zone())
    all_indicators.extend(_check_scsi_disk())
    all_indicators.extend(_check_rdtsc_timing())

    # Determine VM type
    vm_type: Optional[str] = None
    if all_indicators:
        type_counts: Dict[str, int] = {}
        for ind in all_indicators:
            t = ind.get("vm_type", "unknown_hypervisor")
            type_counts[t] = type_counts.get(t, 0) + 1
        vm_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]

    is_vm = len(all_indicators) > 0

    # Extract thermal value if present
    cpu_thermal_value: Optional[float] = None
    for ind in all_indicators:
        if "cpu_thermal_value" in ind and ind["cpu_thermal_value"] is not None:
            cpu_thermal_value = ind["cpu_thermal_value"]
            break

    # Extract timing latency if present
    timing_latency_cycles: Optional[int] = None
    for ind in all_indicators:
        if "timing_latency_cycles" in ind:
            timing_latency_cycles = ind["timing_latency_cycles"]
            break

    return {
        "is_vm": is_vm,
        "vm_type": vm_type,
        "indicators": all_indicators,
        "cpu_thermal_value": cpu_thermal_value,
        "timing_latency_cycles": timing_latency_cycles,
    }
