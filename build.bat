@echo off
setlocal
chcp 65001 >nul

set "VENV_DIR=.venv"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.11+ was not found in PATH.
    echo [HINT] Install Python and enable "Add Python to PATH", then run this script again.
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo [INFO] Installing requirements...
pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [INFO] Building executable with PyInstaller...
pyinstaller --noconfirm --clean jin10_flash_monitor.spec
if errorlevel 1 exit /b 1

echo.
echo [DONE] Output folder: dist\Jin10FlashMonitor

endlocal
