@echo off
setlocal EnableDelayedExpansion

echo ================================================
echo  Timesheet App -- Fresh Install / Repair
echo ================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install, then re-run this script.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found.

:: ── 2. Check Git ─────────────────────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Git not found. You will not be able to pull updates automatically.
    echo Install Git from https://git-scm.com/download/win if you want auto-updates.
    echo Continuing without Git...
    echo.
) else (
    for /f "tokens=3" %%g in ('git --version 2^>^&1') do set GITVER=%%g
    echo [OK] Git %GITVER% found.
)

:: ── 3. Install Python packages ───────────────────────────────────────────────
echo.
echo Installing required Python packages...
python -m pip install --upgrade pip --quiet
python -m pip install flask xhtml2pdf pypdf python-dotenv openpyxl
if errorlevel 1 (
    echo.
    echo ERROR: Package install failed. Check your internet connection and try again.
    pause
    exit /b 1
)
echo [OK] Packages installed.

:: ── 4. Figure out install directory ─────────────────────────────────────────
set INSTALL_DIR=%~dp0
if "%INSTALL_DIR:~-1%"=="\" set INSTALL_DIR=%INSTALL_DIR:~0,-1%
echo [OK] App directory: %INSTALL_DIR%

:: ── 5. Create Desktop shortcut ───────────────────────────────────────────────
echo.
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT=%DESKTOP%\Start Timesheet.bat

(
echo @echo off
echo taskkill /f /im pythonw.exe ^>nul 2^>^&1
echo if exist "%INSTALL_DIR%\timesheet\__pycache__" rmdir /s /q "%INSTALL_DIR%\timesheet\__pycache__"
echo echo Pulling latest updates...
echo cd /d "%INSTALL_DIR%"
echo git pull
echo echo Starting Timesheet...
echo start "" /D "%INSTALL_DIR%" pythonw -m flask --app timesheet.app:create_app run --host 0.0.0.0 --port 5000
echo echo Timesheet started at http://127.0.0.1:5000
echo timeout /t 3
) > "%SHORTCUT%"

echo [OK] Desktop shortcut created: Start Timesheet.bat

:: ── 6. Set up weekly backup scheduled task ───────────────────────────────────
echo.
echo Setting up weekly backup (every Sunday at 8:00 AM)...
set BACKUP_CMD=cmd /c "cd /d "%INSTALL_DIR%" && python send_backup.py >> send_backup.log 2>&1"
schtasks /create /tn "Timesheet Weekly Backup" /tr "%BACKUP_CMD%" /sc weekly /d SUN /st 08:00 /rl highest /f >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not create scheduled task automatically.
    echo See SETUP.md -- Step 6 for manual instructions.
) else (
    echo [OK] Scheduled task "Timesheet Weekly Backup" set for Sundays at 8:00 AM.
)

:: ── 7. Create local data directory if none configured ────────────────────────
if not exist "%INSTALL_DIR%\timesheet\data" mkdir "%INSTALL_DIR%\timesheet\data"

echo.
echo ================================================
echo  Setup complete!
echo ================================================
echo.
echo IMPORTANT -- Before your first use:
echo   1. Double-click "Start Timesheet" on your Desktop.
echo   2. Visit http://127.0.0.1:5000 in your browser.
echo   3. Go to Settings and fill in:
echo        - Business name, address, GST number
echo        - SMTP email details (for weekly backup emails)
echo        - Data folder path (default: Z:\My Drive\TIMESHEET\data)
echo.
echo If you are restoring from a backup ZIP:
echo   - Copy the "data\" folder from the ZIP into:
echo     %INSTALL_DIR%\timesheet\data\
echo   - OR mount Google Drive as Z: and set the data path in Settings.
echo.
pause
