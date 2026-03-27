@echo off
set NODE=C:\Users\scott\AppData\Local\node\node-v20.14.0-win-x64\node.exe
set VITE=C:\Users\scott\ARB\frontend\node_modules\vite\bin\vite.js
cd /d C:\Users\scott\ARB\frontend
"%NODE%" "%VITE%" >> C:\Users\scott\ARB\frontend.log 2>&1
