# Timesheet App — Installation Guide

Fresh install on a new PC, or restoring after a PC failure.

---

## Quick Install (Automated)

1. Install **Python 3.11+** from https://www.python.org/downloads/
   - During install, check **"Add Python to PATH"**
2. Install **Git** from https://git-scm.com/download/win
3. Open a folder where you want the app to live (e.g. `C:\Users\YourName\Timesheet`)
4. Right-click → **Open in Terminal** and run:
   ```
   git clone https://github.com/BASECAMP70/BASECAMPARB.git .
   ```
5. Double-click **SETUP.bat** in that folder.
6. Follow the on-screen prompts.

That's it — SETUP.bat installs all packages, creates the Desktop shortcut, and sets up the weekly backup schedule.

---

## Restoring Your Data

After running SETUP.bat, restore your data from the latest backup ZIP:

- Open the ZIP file (e.g. `timesheet-backup-2026-09-13.zip`)
- Copy the **`data/`** folder contents into:
  ```
  <app folder>\timesheet\data\
  ```
  (So you end up with `timesheet\data\clients.json`, `timesheet\data\time_entries.json`, etc.)

- Copy **`expense_receipts/`** PDFs back if you need them
  (rename them back to UUID filenames — see the expenses list in the app)

If you use **Google Drive** (mounted as `Z:`):
- Mount Google Drive first
- In the app go to **Settings → Data Folder** and set it to `Z:\My Drive\TIMESHEET\data`
- The app will read/write there automatically

---

## What's in the Weekly Backup ZIP

| Folder/File | Contents |
|---|---|
| `timesheet-backup-YYYY-MM-DD.xlsx` | All time, expenses, invoices in Excel |
| `data/` | All JSON data files (clients, projects, time entries, etc.) |
| `expense_receipts/` | Uploaded expense receipt PDFs (renamed to be readable) |
| `invoices/` | Generated invoice PDFs |
| `app/` | Full app source code (Python, templates, static files) |

---

## Manual Steps (if SETUP.bat fails)

### Step 1 — Install Python 3.11+
Download from https://www.python.org/downloads/ and check "Add Python to PATH".

### Step 2 — Install Git
Download from https://git-scm.com/download/win.

### Step 3 — Clone the repo
```
git clone https://github.com/BASECAMP70/BASECAMPARB.git C:\Timesheet
cd C:\Timesheet
```

### Step 4 — Install Python packages
```
pip install flask xhtml2pdf pypdf python-dotenv openpyxl
```

### Step 5 — Create Desktop shortcut
Create `Start Timesheet.bat` on your Desktop with this content
(replace `C:\Timesheet` with your actual install path):
```bat
@echo off
taskkill /f /im pythonw.exe >nul 2>&1
if exist "C:\Timesheet\timesheet\__pycache__" rmdir /s /q "C:\Timesheet\timesheet\__pycache__"
git -C "C:\Timesheet" pull
start "" /D "C:\Timesheet" pythonw -m flask --app timesheet.app:create_app run --host 0.0.0.0 --port 5000
timeout /t 3
```

### Step 6 — Weekly backup scheduled task
Open Task Scheduler (search "Task Scheduler" in Start menu):
- **Create Basic Task** → name it "Timesheet Weekly Backup"
- **Trigger**: Weekly, Sunday, 8:00 AM
- **Action**: Start a program
  - Program: `python`
  - Arguments: `send_backup.py >> send_backup.log 2>&1`
  - Start in: `C:\Timesheet` (your install path)

### Step 7 — Configure Settings
Open http://127.0.0.1:5000/settings and fill in:
- Business name, address, GST number
- SMTP email settings (Gmail: smtp.gmail.com, port 587, use an App Password)
- Data folder path

---

## Accessing the App from Another PC on Your Network

The app listens on all network interfaces. From another PC:
```
http://<your-PC-IP>:5000
```
Find your IP: open Command Prompt and run `ipconfig`, look for IPv4 Address.
