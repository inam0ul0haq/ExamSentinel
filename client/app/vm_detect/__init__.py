"""VM detection package — standard and stealth gates."""

from client.app.vm_detect.standard import detect_standard_vm
from client.app.vm_detect.stealth import detect_stealth_vm

__all__ = ["detect_standard_vm", "detect_stealth_vm"]
