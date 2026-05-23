@echo off
:: ================================================================
:: ExamSentinel — VirtualBox Stealth Script
:: ================================================================
:: Run this INSIDE the Windows 11 VirtualBox VM as Administrator.
::
:: What it does (bypasses Standard VM detection):
::   1. Kills VirtualBox Guest Addition processes
::   2. Deletes VirtualBox registry keys
::   3. Changes MAC address to a non-VM OUI
::   4. Spoofs WMI BIOS/System strings (via VBoxManage on HOST)
::
:: What it CANNOT hide (Stealth detection still catches):
::   - RDTSC timing (hypervisor trap latency)
::   - Thermal zone absence (no thermal sensors in VMs)
::   - SCSI disk identifier ("VBOX HARDDISK" in hardware layer)
:: ================================================================

echo =============================================
echo  ExamSentinel VM Stealth Script (VirtualBox)
echo =============================================
echo.

:: ---- Step 1: Kill VirtualBox Guest Addition Processes ----
echo [1/4] Killing VirtualBox processes...
taskkill /F /IM VBoxService.exe 2>nul
taskkill /F /IM VBoxTray.exe 2>nul
taskkill /F /IM VBoxClient.exe 2>nul

:: Stop VirtualBox services
net stop VBoxService 2>nul
sc config VBoxService start=disabled 2>nul
echo       Done.
echo.

:: ---- Step 2: Delete VirtualBox Registry Keys ----
echo [2/4] Removing VirtualBox registry keys...
reg delete "HKLM\SOFTWARE\Oracle\VirtualBox Guest Additions" /f 2>nul
reg delete "HKLM\SYSTEM\ControlSet001\Services\VBoxGuest" /f 2>nul
reg delete "HKLM\SYSTEM\ControlSet001\Services\VBoxMouse" /f 2>nul
reg delete "HKLM\SYSTEM\ControlSet001\Services\VBoxSF" /f 2>nul
reg delete "HKLM\SYSTEM\ControlSet001\Services\VBoxVideo" /f 2>nul
echo       Done.
echo.

:: ---- Step 3: Change MAC Address (remove VirtualBox OUI 08:00:27) ----
echo [3/4] Changing MAC address to non-VM OUI...
:: Find the VirtualBox network adapter name and change its MAC
:: Uses a Dell OUI (D4:BE:D9) to look like real hardware
for /f "tokens=1,2,* delims==" %%a in ('wmic nic where "MACAddress like '08:00:27%%'" get NetConnectionID /value 2^>nul ^| findstr /i "NetConnectionID"') do (
    set "ADAPTER=%%b"
)
if defined ADAPTER (
    echo       Found adapter: %ADAPTER%
    :: Set a random-looking real hardware MAC via registry
    for /f "tokens=*" %%i in ('wmic nic where "NetConnectionID='%ADAPTER%'" get GUID /value 2^>nul ^| findstr "GUID"') do (
        for /f "tokens=2 delims==" %%g in ("%%i") do (
            reg add "HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}\0001" /v NetworkAddress /t REG_SZ /d "D4BED9A1B2C3" /f 2>nul
        )
    )
    :: Restart adapter to apply
    netsh interface set interface "%ADAPTER%" disable 2>nul
    timeout /t 2 >nul
    netsh interface set interface "%ADAPTER%" enable 2>nul
    echo       MAC changed to D4:BE:D9:A1:B2:C3 (Dell OUI)
) else (
    echo       No VirtualBox MAC adapter found, skipping.
)
echo.

:: ---- Step 4: Reminder for WMI Spoofing (must be done on HOST) ----
echo [4/4] WMI Spoofing reminder...
echo.
echo =============================================
echo  IMPORTANT: Run these on the HOST machine
echo  (in CMD where VBoxManage is available)
echo  BEFORE starting the VM:
echo =============================================
echo.
echo   VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVendor" "American Megatrends Inc."
echo   VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiBIOSVersion" "1.0.0"
echo   VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemVendor" "Dell Inc."
echo   VBoxManage setextradata "YOUR_VM_NAME" "VBoxInternal/Devices/pcbios/0/Config/DmiSystemProduct" "OptiPlex 7090"
echo   VBoxManage modifyvm "YOUR_VM_NAME" --macaddress1 D4BED9A1B2C3
echo.
echo =============================================
echo.
echo  Standard VM detection should now show: NOT DETECTED
echo  Stealth VM detection will still catch:
echo    - RDTSC timing (hypervisor trap)
echo    - Thermal zone (no sensors)
echo    - SCSI disk (VBOX HARDDISK)
echo =============================================
echo.
pause
