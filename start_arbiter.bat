@echo off
REM Start Arbiter backend and frontend on login

REM ── Backend ──────────────────────────────────────────────────────────────────
echo Starting Arbiter backend...
start "Arbiter Backend" /MIN cmd /c "cd /d C:\Users\scott\ARB\backend && .venv\Scripts\python.exe run.py >> C:\Users\scott\ARB\backend.log 2>&1"

REM Wait 12 seconds for backend to fully start before launching frontend
timeout /t 12 /nobreak >nul

REM ── Frontend ─────────────────────────────────────────────────────────────────
echo Starting Arbiter frontend...
start "Arbiter Frontend" /MIN cmd /c "cd /d C:\Users\scott\ARB\frontend && C:\Users\scott\AppData\Local\node\node-v20.14.0-win-x64\node.exe node_modules\vite\bin\vite.js >> C:\Users\scott\ARB\frontend.log 2>&1"

echo Arbiter started. Backend: http://localhost:8000  Frontend: http://localhost:5173
