@echo off
cd /d "%~dp0"
python send_backup.py >> send_backup.log 2>&1
