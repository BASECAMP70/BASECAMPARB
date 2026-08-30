@echo off
echo Killing any Python processes on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    echo Killing PID %%a
    taskkill /PID %%a /F /T
)
echo Killing all python.exe processes...
taskkill /IM python.exe /F /T 2>nul
echo Waiting 3 seconds...
timeout /t 3 /nobreak >nul
echo Starting backend...
cd /d C:\Users\scott\ARB\backend
start "ARB Backend" cmd /k ".venv\Scripts\python.exe run.py >> C:\Users\scott\ARB\backend.log 2>&1"
echo Done.
