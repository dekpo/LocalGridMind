@echo off
REM Copy the current app into gitignored release\ChatWithExcelFile.
REM Testers receive THAT folder only. Do not put tester files at the repo root.
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "DEST=release\ChatWithExcelFile"
if not exist "%DEST%" mkdir "%DEST%"

robocopy src "%DEST%\src" /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1
robocopy assets "%DEST%\assets" /E /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1
robocopy .streamlit "%DEST%\.streamlit" /E /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1

copy /Y requirements.txt "%DEST%\requirements.txt" >nul
copy /Y "tools\beta\setup.bat" "%DEST%\setup.bat" >nul
copy /Y "tools\beta\start.bat" "%DEST%\start.bat" >nul
copy /Y "tools\beta\README.md" "%DEST%\README.md" >nul
copy /Y "tools\beta\TEST_CASES.md" "%DEST%\TEST_CASES.md" >nul

if not exist "%DEST%\models" mkdir "%DEST%\models"
if exist "models\README.md" copy /Y "models\README.md" "%DEST%\models\README.md" >nul
if not exist "%DEST%\data\uploads" mkdir "%DEST%\data\uploads"
if not exist "%DEST%\data\chats" mkdir "%DEST%\data\chats"
if not exist "%DEST%\outputs" mkdir "%DEST%\outputs"

echo.
echo Tester pack: %CD%\%DEST%
echo Zip that folder for testers. Do not zip the Git repo root.
echo Rebuild keeps models\ and data\ already in the pack.
exit /b 0
