@echo off
REM First-time install inside release\ChatWithExcelFile. CMD only.
REM Use python -m pip, never pip.exe: Device Guard blocks the venv stub.
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not on PATH.
    echo Install Python 3.11 from https://www.python.org/downloads/windows/
    echo Tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)

if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 (
    echo Could not create .venv
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 (
    pause
    exit /b 1
)
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if errorlevel 1 (
    echo llama-cpp-python CPU wheel failed. If Python is 3.13, install 3.11 from python.org, then run setup.bat again.
    pause
    exit /b 1
)
python -m pip install -r requirements.txt
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo Setup finished. Put Qwen3.5-9B-Q5_K_M.gguf in the models folder, then double-click start.bat
pause
exit /b 0
