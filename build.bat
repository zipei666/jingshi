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

echo [INFO] Removing local runtime data from previous builds...
if exist "dist\Jin10FlashMonitor\data" rmdir /s /q "dist\Jin10FlashMonitor\data"
if exist "dist\Jin10FlashMonitor\settings.json" del /f /q "dist\Jin10FlashMonitor\settings.json"
if exist "dist\Jin10FlashMonitor\.env" del /f /q "dist\Jin10FlashMonitor\.env"
if exist "dist\Jin10FlashMonitor\config.local.py" del /f /q "dist\Jin10FlashMonitor\config.local.py"

echo [INFO] Building executable with PyInstaller...
pyinstaller --noconfirm --clean jin10_flash_monitor.spec
if errorlevel 1 exit /b 1

echo [INFO] Checking output for local secrets...
if exist "dist\Jin10FlashMonitor\data" (
    echo [ERROR] Refusing to publish: dist\Jin10FlashMonitor\data exists.
    exit /b 1
)
if exist "dist\Jin10FlashMonitor\settings.json" (
    echo [ERROR] Refusing to publish: settings.json exists in output.
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$patterns='oapi.dingtalk.com','access_token=','webhook_url','webhook_secret'; $files=Get-ChildItem -Path 'dist\Jin10FlashMonitor' -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.json','.txt','.ini','.cfg','.env','.py','.log' -or $_.Name -eq 'settings.json' }; foreach ($pattern in $patterns) { $hit=$files | Select-String -SimpleMatch $pattern -List -ErrorAction SilentlyContinue | Select-Object -First 1; if ($hit) { Write-Host ('[ERROR] Sensitive pattern found in output: ' + $pattern + ' -> ' + $hit.Path); exit 1 } }"
if errorlevel 1 exit /b 1

echo.
echo [DONE] Output folder: dist\Jin10FlashMonitor

endlocal
