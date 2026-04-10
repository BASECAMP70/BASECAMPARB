' Launches Arbiter backend and frontend silently at login (no CMD window)
Dim wsh : Set wsh = CreateObject("WScript.Shell")

' Backend — uses restart_backend.bat which already has correct paths
wsh.Run "cmd /c C:\Users\scott\ARB\backend\restart_backend.bat", 0, False

' Wait 15 seconds for backend to fully start
WScript.Sleep 15000

' Frontend — full absolute paths, no cd needed
wsh.Run """C:\Users\scott\AppData\Local\node\node-v20.14.0-win-x64\node.exe"" ""C:\Users\scott\ARB\frontend\node_modules\vite\bin\vite.js"" --config ""C:\Users\scott\ARB\frontend\vite.config.js""", 0, False
