@echo off
REM ---------------------------------------------------------------------------
REM ExamSentinel — Windows dev bootstrap.
REM
REM 1. Creates server\.venv if missing.
REM 2. Activates the venv.
REM 3. Installs/updates dependencies from requirements.txt.
REM 4. Copies .env.example -> .env if .env is absent.
REM 5. Launches the Flask dev server via run_dev.py.
REM
REM Run from the repository root or from server\:
REM     server\dev.bat
REM ---------------------------------------------------------------------------

setlocal ENABLEEXTENSIONS
cd /d "%~dp0"

set VENV_DIR=.venv
set PYTHON_EXE=python

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [dev] Creating virtual environment in %VENV_DIR% ...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [dev] Failed to create virtual environment. Is Python on PATH?
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [dev] Failed to activate virtual environment.
    exit /b 1
)

echo [dev] Installing dependencies ...
python -m pip install --disable-pip-version-check --upgrade pip >nul
REM requirements.txt lives at the repo root (alongside Procfile and
REM runtime.txt) so Railway's Nixpacks builder detects this as a
REM Python project. dev.bat reaches up one level to use it.
python -m pip install -r ..\requirements.txt
if errorlevel 1 (
    echo [dev] Dependency install failed.
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        echo [dev] .env not found; copying from .env.example ...
        copy /Y ".env.example" ".env" >nul
    ) else (
        echo [dev] WARNING: neither .env nor .env.example found.
    )
)

echo [dev] Starting Flask dev server ...
python run_dev.py
endlocal
