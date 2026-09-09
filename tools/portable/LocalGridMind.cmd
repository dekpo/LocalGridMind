@echo off
cd /d "%~dp0"
if not exist "runtime\python.exe" (
    echo Missing runtime\python.exe. Run tools\portable\build.bat from the repo.
    exit /b 1
)
runtime\python.exe -m streamlit run src\app.py --global.developmentMode=false --browser.gatherUsageStats=false --server.headless=false
