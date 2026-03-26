@echo off
:LOOP
echo [%DATE% %TIME%] Starting ARB backend...
cd /d C:\Users\scott\ARB\backend
.venv\Scripts\python.exe run.py >> C:\Users\scott\ARB\backend.log 2>&1
echo [%DATE% %TIME%] Backend exited (code %ERRORLEVEL%) — restarting in 5s...
timeout /t 5 /nobreak >nul
goto LOOP
