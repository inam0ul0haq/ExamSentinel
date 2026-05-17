@echo off
setlocal

set "VENV_DIR=%~dp0.venv"
set "REQ_FILE=%~dp0requirements.txt"
set "ENV_EXAMPLE=%~dp0.env.example"
set "ENV_FILE=%~dp0.env"
set "PROJECT_ROOT=%~dp0.."

:: Create virtual environment if it doesn't exist
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ExamSentinel] Creating virtual environment ...
    python -m venv "%VENV_DIR%"
)

:: Activate venv
call "%VENV_DIR%\Scripts\activate.bat"

:: Install / update dependencies
echo [ExamSentinel] Installing dependencies ...
pip install -q -r "%REQ_FILE%"

:: Copy .env.example -> .env if missing
if not exist "%ENV_FILE%" (
    if exist "%ENV_EXAMPLE%" (
        echo [ExamSentinel] Creating .env from .env.example ...
        copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
    )
)

:: Run the client
echo [ExamSentinel] Launching client ...
cd /d "%PROJECT_ROOT%"
python -m client.app.main

endlocal
