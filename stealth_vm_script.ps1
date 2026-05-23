#Requires -RunAsAdministrator
<#
.SYNOPSIS
    ExamSentinel — VirtualBox Stealth Script (run INSIDE the VM)

.DESCRIPTION
    Hides all 4 standard VM detection indicators:
      1. Processes — kills VBoxService/VBoxTray
      2. Registry  — deletes Guest Addition keys
      3. WMI       — spoofed via VBoxManage on HOST (see instructions below)
      4. MAC       — changes to Dell OUI

    Stealth detection STILL catches the VM via:
      - RDTSC timing (hypervisor CPUID trap latency)
      - Thermal zone absence (no MSAcpi_ThermalZoneTemperature)
      - SCSI disk ID ("VBOX HARDDISK" in hardware layer)
#>

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " ExamSentinel VM Stealth Script (VirtualBox)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Kill VirtualBox Processes ----
Write-Host "[1/4] Killing VirtualBox processes..." -ForegroundColor Yellow
$vboxProcesses = @("VBoxService", "VBoxTray", "VBoxClient")
foreach ($proc in $vboxProcesses) {
    $p = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($p) {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-Host "      Killed $proc" -ForegroundColor Green
    }
}
# Disable VBoxService so it doesn't restart
Stop-Service -Name "VBoxService" -Force -ErrorAction SilentlyContinue
Set-Service -Name "VBoxService" -StartupType Disabled -ErrorAction SilentlyContinue
Write-Host "      VBoxService disabled." -ForegroundColor Green
Write-Host ""

# ---- 2. Delete VirtualBox Registry Keys ----
Write-Host "[2/4] Removing VirtualBox registry keys..." -ForegroundColor Yellow
$regKeys = @(
    "HKLM:\SOFTWARE\Oracle\VirtualBox Guest Additions",
    "HKLM:\SYSTEM\ControlSet001\Services\VBoxGuest",
    "HKLM:\SYSTEM\ControlSet001\Services\VBoxMouse",
    "HKLM:\SYSTEM\ControlSet001\Services\VBoxSF",
    "HKLM:\SYSTEM\ControlSet001\Services\VBoxVideo"
)
foreach ($key in $regKeys) {
    if (Test-Path $key) {
        Remove-Item -Path $key -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "      Deleted $key" -ForegroundColor Green
    } else {
        Write-Host "      Already gone: $key" -ForegroundColor DarkGray
    }
}
Write-Host ""

# ---- 3. Change MAC Address ----
Write-Host "[3/4] Changing MAC address to non-VM OUI..." -ForegroundColor Yellow
$newMAC = "D4BED9A1B2C3"  # Dell OUI

# Find VirtualBox network adapters (OUI 08:00:27 or 0A:00:27)
$adapters = Get-NetAdapter | Where-Object {
    $mac = $_.MacAddress -replace "-", ":"
    $mac -like "08:00:27*" -or $mac -like "0A:00:27*"
}

if ($adapters) {
    foreach ($adapter in $adapters) {
        Write-Host "      Found: $($adapter.Name) [$($adapter.MacAddress)]" -ForegroundColor Green
        # Set new MAC via registry
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
        Get-ChildItem $regPath -ErrorAction SilentlyContinue | ForEach-Object {
            $driverDesc = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DriverDesc
            if ($driverDesc -and $driverDesc -match "VirtualBox|VBox") {
                Set-ItemProperty -Path $_.PSPath -Name "NetworkAddress" -Value $newMAC -ErrorAction SilentlyContinue
                Write-Host "      Set NetworkAddress=$newMAC on $driverDesc" -ForegroundColor Green
            }
        }
        # Restart adapter to apply
        Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "      Adapter restarted with new MAC" -ForegroundColor Green
    }
} else {
    Write-Host "      No VirtualBox MAC adapters found." -ForegroundColor DarkGray
}
Write-Host ""

# ---- 4. Host-side WMI Spoofing Instructions ----
Write-Host "[4/4] WMI spoofing (run on HOST before starting VM):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  On your HOST machine, open CMD and run:" -ForegroundColor White
Write-Host '  (Replace YOUR_VM_NAME with your VirtualBox VM name)' -ForegroundColor DarkGray
Write-Host ""
Write-Host '  VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVendor" "American Megatrends Inc."' -ForegroundColor Cyan
Write-Host '  VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVersion" "F.40"' -ForegroundColor Cyan
Write-Host '  VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemVendor" "Dell Inc."' -ForegroundColor Cyan
Write-Host '  VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemProduct" "OptiPlex 7090"' -ForegroundColor Cyan
Write-Host '  VBoxManage modifyvm "YOUR_VM_NAME" --macaddress1 D4BED9A1B2C3' -ForegroundColor Cyan
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " After running this script + HOST commands:" -ForegroundColor White
Write-Host "   Standard VM detection  ->  NOT DETECTED" -ForegroundColor Green
Write-Host "   Stealth VM detection   ->  DETECTED via:" -ForegroundColor Red
Write-Host "     - RDTSC timing (CPUID trap latency)" -ForegroundColor Red
Write-Host "     - Thermal zone (no sensors in VM)" -ForegroundColor Red
Write-Host "     - SCSI disk (VBOX HARDDISK)" -ForegroundColor Red
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
