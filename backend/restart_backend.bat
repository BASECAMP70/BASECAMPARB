@echo off
:LOOP
echo [%DATE% %TIME%] Killing any orphan processes on ports 8000 and 8001...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr LISTENING') do (
    echo Killing PID %%a on port 8000
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 " ^| findstr LISTENING') do (
    echo Killing PID %%a on port 8001
    taskkill /PID %%a /F >nul 2>&1
)
echo [%DATE% %TIME%] Starting ARB backend...
cd /d C:\Users\scott\ARB\backend
.venv\Scripts\python.exe run.py >> C:\Users\scott\ARB\backend.log 2>&1
echo [%DATE% %TIME%] Backend exited (code %ERRORLEVEL%) — restarting in 5s...
timeout /t 5 /nobreak >nul
goto LOOP
