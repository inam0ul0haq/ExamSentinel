"""
Standard VM Detection Module.

Checks for obvious virtualization indicators that are present on default
VirtualBox/VMware/Hyper-V guests:
  1. Running processes (VBoxService.exe, vmtoolsd.exe, etc.)
  2. Registry keys (Guest Additions, VMware Tools)
  3. WMI hardware strings (Win32_ComputerSystem, Win32_BIOS)
  4. MAC address OUI prefixes

Returns a structured verdict: {is_vm, vm_type, indicators[]}.
"""

from __future__ import annotations

import logging
import platform
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Known signatures
# ---------------------------------------------------------------------------

VM_PROCESSES = {
    # VirtualBox
    "vboxservice.exe": "virtualbox",
    "vboxtray.exe": "virtualbox",
    "vboxclient.exe": "virtualbox",
    # VMware
    "vmtoolsd.exe": "vmware",
    "vmwaretray.exe": "vmware",
    "vmwareuser.exe": "vmware",
    "vmacthlp.exe": "vmware",
    # Hyper-V
    "vmcompute.exe": "hyperv",
    "vmms.exe": "hyperv",
    # QEMU
    "qemu-ga.exe": "qemu",
    # Parallels
    "prl_tools.exe": "parallels",
}

VM_REGISTRY_KEYS = [
    (r"SOFTWARE\Oracle\VirtualBox Guest Additions", "virtualbox"),
    (r"SOFTWARE\VMware, Inc.\VMware Tools", "vmware"),
    (r"SOFTWARE\Microsoft\Virtual Machine\Guest\Parameters", "hyperv"),
    (r"SYSTEM\ControlSet001\Services\VBoxGuest", "virtualbox"),
    (r"SYSTEM\ControlSet001\Services\VBoxMouse", "virtualbox"),
    (r"SYSTEM\ControlSet001\Services\VBoxSF", "virtualbox"),
    (r"SYSTEM\ControlSet001\Services\VBoxVideo", "virtualbox"),
    (r"SYSTEM\ControlSet001\Services\vmtools", "vmware"),
    (r"SYSTEM\ControlSet001\Services\vmhgfs", "vmware"),
]

WMI_VM_STRINGS = {
    "virtualbox": ["virtualbox", "vbox", "innotek"],
    "vmware": ["vmware", "vmw"],
    "hyperv": ["microsoft corporation"],
    "qemu": ["qemu"],
    "parallels": ["parallels"],
}

MAC_OUI_MAP = {
    "08:00:27": "virtualbox",
    "0a:00:27": "virtualbox",
    "00:05:69": "vmware",
    "00:0c:29": "vmware",
    "00:1c:14": "vmware",
    "00:50:56": "vmware",
    "00:15:5d": "hyperv",
    "52:54:00": "qemu",
    "00:1c:42": "parallels",
}


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


def _check_processes() -> List[Dict[str, Any]]:
    """Check running processes against known VM process names."""
    indicators = []
    try:
        import psutil
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in VM_PROCESSES:
                    indicators.append({
                        "category": "process",
                        "name": name,
                        "evidence": f"PID {proc.info['pid']}",
                        "vm_type": VM_PROCESSES[name],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        logger.debug("psutil not available, skipping process check")
    except Exception as e:
        logger.debug(f"Process check error: {e}")
    return indicators


def _check_registry() -> List[Dict[str, Any]]:
    """Check for VM-related registry keys."""
    indicators = []
    if platform.system() != "Windows":
        return indicators
    try:
        import winreg
        for key_path, vm_type in VM_REGISTRY_KEYS:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                winreg.CloseKey(key)
                indicators.append({
                    "category": "registry",
                    "name": key_path.split("\\")[-1],
                    "evidence": f"HKLM\\{key_path}",
                    "vm_type": vm_type,
                })
            except (FileNotFoundError, OSError):
                continue
    except ImportError:
        logger.debug("winreg not available, skipping registry check")
    except Exception as e:
        logger.debug(f"Registry check error: {e}")
    return indicators


def _check_wmi() -> List[Dict[str, Any]]:
    """Check WMI hardware strings for VM indicators."""
    indicators = []
    if platform.system() != "Windows":
        return indicators
    try:
        import wmi
        c = wmi.WMI()

        # Win32_ComputerSystem
        for item in c.Win32_ComputerSystem():
            manufacturer = (item.Manufacturer or "").lower()
            model = (item.Model or "").lower()
            for vm_type, patterns in WMI_VM_STRINGS.items():
                for pattern in patterns:
                    if pattern in manufacturer or pattern in model:
                        indicators.append({
                            "category": "wmi",
                            "name": "Win32_ComputerSystem",
                            "evidence": f"Manufacturer={item.Manufacturer}, Model={item.Model}",
                            "vm_type": vm_type,
                        })
                        break

        # Win32_BIOS
        for item in c.Win32_BIOS():
            version = (item.SMBIOSBIOSVersion or "").lower()
            manufacturer = (item.Manufacturer or "").lower()
            combined = version + " " + manufacturer
            for vm_type, patterns in WMI_VM_STRINGS.items():
                for pattern in patterns:
                    if pattern in combined:
                        indicators.append({
                            "category": "wmi",
                            "name": "Win32_BIOS",
                            "evidence": f"Version={item.SMBIOSBIOSVersion}, Mfr={item.Manufacturer}",
                            "vm_type": vm_type,
                        })
                        break

    except ImportError:
        logger.debug("wmi module not available, skipping WMI check")
    except Exception as e:
        logger.debug(f"WMI check error: {e}")
    return indicators


def _check_mac() -> List[Dict[str, Any]]:
    """Check MAC address OUI against known VM vendor ranges."""
    indicators = []
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                raw = addr.address
                if not raw or ("-" not in raw and ":" not in raw):
                    continue

                mac = raw.lower().replace("-", ":")
                if len(mac) != 17:  # full MAC XX:XX:XX:XX:XX:XX
                    continue

                oui = mac[:8]
                if oui in MAC_OUI_MAP:
                    indicators.append({
                        "category": "mac_oui",
                        "name": name,
                        "evidence": f"MAC={mac}, OUI={oui}",
                        "vm_type": MAC_OUI_MAP[oui],
                    })
    except ImportError:
        logger.debug("psutil not available, skipping MAC check")
    except Exception as e:
        logger.debug(f"MAC check error: {e}")
    return indicators


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_standard_vm() -> Dict[str, Any]:
    """Run all standard VM detection checks.

    Returns:
        {
            "is_vm": bool,
            "vm_type": str or None,
            "indicators": [{"category", "name", "evidence", "vm_type"}, ...]
        }
    """
    all_indicators: List[Dict[str, Any]] = []

    all_indicators.extend(_check_processes())
    all_indicators.extend(_check_registry())
    all_indicators.extend(_check_wmi())
    all_indicators.extend(_check_mac())

    # Determine VM type by majority vote
    vm_type: Optional[str] = None
    if all_indicators:
        type_counts: Dict[str, int] = {}
        for ind in all_indicators:
            t = ind.get("vm_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        vm_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]

    is_vm = len(all_indicators) > 0

    return {
        "is_vm": is_vm,
        "vm_type": vm_type,
        "indicators": all_indicators,
    }
