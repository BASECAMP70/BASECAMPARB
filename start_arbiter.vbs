' Launches Arbiter backend and frontend silently at login (no CMD window)
Dim wsh : Set wsh = CreateObject("WScript.Shell")

' Backend
wsh.Run "cmd /c ""cd /d C:\Users\scott\ARB\backend && .venv\Scripts\python.exe run.py >> C:\Users\scott\ARB\backend.log 2>&1""", 0, False

' Wait 12 seconds for backend to start
WScript.Sleep 12000

' Frontend
wsh.Run "cmd /c ""cd /d C:\Users\scott\ARB\frontend && C:\Users\scott\AppData\Local\node\node-v20.14.0-win-x64\node.exe node_modules\vite\bin\vite.js >> C:\Users\scott\ARB\frontend.log 2>&1""", 0, False
