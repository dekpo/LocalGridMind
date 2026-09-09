@echo off
REM Start the ChatWithExcelFile prototype. CMD only. Not PowerShell.
REM Use python -m streamlit, never streamlit.exe: Device Guard blocks venv stubs.
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Run setup.bat once before start.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
echo Starting ChatWithExcelFile. Leave this window open. The browser should open on its own.
echo To stop: close this window, or Ctrl+C.
python -m streamlit run src\app.py
