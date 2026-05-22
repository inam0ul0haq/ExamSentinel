@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   ExamSentinel — Windows Build Pipeline
echo ============================================================
echo.

:: ---------- 1. Locate and activate venv -----------------------
set "VENV=%~dp0..\.venv"
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at %VENV%
    echo         Run:  python -m venv client\.venv
    exit /b 1
)
call "%VENV%\Scripts\activate.bat"
echo [OK] Activated venv at %VENV%
echo.

:: ---------- 2. Install / update requirements ------------------
echo [STEP 2] Installing requirements...
pip install -r "%~dp0..\requirements.txt" --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    exit /b 1
)
echo [OK] Requirements up to date.
echo.

:: ---------- 3. Generate icon if missing -----------------------
if not exist "%~dp0icon.ico" (
    echo [STEP 2b] Generating icon...
    pip install Pillow --quiet
    python "%~dp0gen_icon.py"
)

:: ---------- 4. Run PyInstaller --------------------------------
echo [STEP 3] Running PyInstaller...
pushd "%~dp0"
pyinstaller --clean ExamSentinel.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd
    exit /b 1
)
popd
echo [OK] PyInstaller build succeeded.
echo.

:: ---------- 5. Copy to release folder -------------------------
echo [STEP 4] Copying to release folder...
set "DIST=%~dp0dist\ExamSentinel.exe"
if not exist "%DIST%" (
    echo [ERROR] Expected output not found: %DIST%
    exit /b 1
)

:: Create release dir
if not exist "%~dp0release" mkdir "%~dp0release"

:: Get ISO date (YYYY-MM-DD)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
set "ISO_DATE=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%"
set "RELEASE_NAME=ExamSentinel_%ISO_DATE%.exe"

copy /Y "%DIST%" "%~dp0release\%RELEASE_NAME%" >nul
echo [OK] Release: client\build\release\%RELEASE_NAME%
echo.

:: ---------- 6. Summary ----------------------------------------
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo   Output:    client\build\dist\ExamSentinel.exe
echo   Release:   client\build\release\%RELEASE_NAME%
echo.
echo   NEXT STEPS:
echo   -----------
echo   1. The exe REQUIRES Administrator privileges (UAC prompt).
echo   2. Examiners need internet access to reach the backend.
echo   3. API_BASE_URL was loaded from client\.env at build time.
echo      To change it, edit .env and rebuild, or set the env var
echo      on the target machine.
echo   4. Antivirus may flag single-file PyInstaller binaries.
echo      Workaround: right-click → Properties → Unblock.
echo      Or add a Windows Defender exclusion for the demo folder.
echo   5. Copy the exe to any Windows 10/11 machine — no Python
echo      install required.
echo ============================================================

endlocal
