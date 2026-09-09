@echo off
REM Assemble release\LocalGridMind with official embeddable CPython.
REM The thin exe only starts runtime\python.exe so Windows can load ggml.dll.
setlocal EnableExtensions
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\activate.bat" (
    echo Create the venv first. See README.md
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install -q "pyinstaller>=6.11,<7"
if errorlevel 1 exit /b 1

python "tools\portable\fetch_embed.py" "tools\portable\cache"
if errorlevel 1 exit /b 1

for %%F in ("tools\portable\cache\python-*-embed-amd64.zip") do set "PY_ZIP=%%~fF"
if not defined PY_ZIP (
    echo Embeddable CPython zip not found in tools\portable\cache
    exit /b 1
)

pyinstaller "tools\portable\localgridmind.spec" --noconfirm --clean --distpath dist --workpath build
if errorlevel 1 exit /b 1

set "SRC_DIST=dist\LocalGridMind"
set "DEST=release\LocalGridMind"

if not exist "%SRC_DIST%\LocalGridMind.exe" (
    echo Build failed: %SRC_DIST%\LocalGridMind.exe not found.
    exit /b 1
)

if not exist "%DEST%" mkdir "%DEST%"

if exist "%DEST%\_internal" rmdir /s /q "%DEST%\_internal"
if exist "%DEST%\runtime" rmdir /s /q "%DEST%\runtime"
copy /Y "%SRC_DIST%\LocalGridMind.exe" "%DEST%\LocalGridMind.exe" >nul
if exist "%SRC_DIST%\_internal" xcopy /E /I /Y "%SRC_DIST%\_internal" "%DEST%\_internal" >nul

mkdir "%DEST%\runtime"
tar -xf "%PY_ZIP%" -C "%DEST%\runtime"
if errorlevel 1 exit /b 1
python "tools\portable\enable_embed_site.py" "%DEST%\runtime"
if errorlevel 1 exit /b 1

robocopy ".venv\Lib\site-packages" "%DEST%\runtime\Lib\site-packages" /E /XD __pycache__ PyInstaller pyinstaller _pyinstaller_hooks_contrib pytest _pytest /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1

robocopy src "%DEST%\src" /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1
robocopy assets "%DEST%\assets" /E /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1
robocopy .streamlit "%DEST%\.streamlit" /E /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 exit /b 1

copy /Y "tools\portable\LocalGridMind.cmd" "%DEST%\LocalGridMind.cmd" >nul
if exist "tools\portable\START_HERE.txt" copy /Y "tools\portable\START_HERE.txt" "%DEST%\START_HERE.txt" >nul

if not exist "%DEST%\models" mkdir "%DEST%\models"
if not exist "%DEST%\data\uploads" mkdir "%DEST%\data\uploads"
if not exist "%DEST%\data\chats" mkdir "%DEST%\data\chats"
if not exist "%DEST%\outputs" mkdir "%DEST%\outputs"

if exist "models\README.md" copy /Y "models\README.md" "%DEST%\models\README.md" >nul
if exist "models\*.gguf" copy /Y "models\*.gguf" "%DEST%\models\" >nul

echo.
echo Portable folder: %CD%\%DEST%
echo Double-click LocalGridMind.exe. Leave the console open.
exit /b 0
