# Timesheet App — Full Installation Guide

Use this guide to install the app on a new PC, or to restore after a PC failure.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Install the App](#2-install-the-app)
3. [Restore Your Data](#3-restore-your-data)
4. [Configure Settings](#4-configure-settings)
5. [Set Up Gmail App Password (SMTP)](#5-set-up-gmail-app-password-smtp)
6. [Set Up Google Drive Sync](#6-set-up-google-drive-sync)
7. [Set Up the Weekly Backup](#7-set-up-the-weekly-backup)
8. [Set Up a Second PC](#8-set-up-a-second-pc)
9. [Starting and Stopping the App](#9-starting-and-stopping-the-app)
10. [Updating the App](#10-updating-the-app)
11. [Troubleshooting](#11-troubleshooting)
12. [What's in the Weekly Backup ZIP](#12-whats-in-the-weekly-backup-zip)

---

## 1. Prerequisites

Install these two programs before anything else.

### Python 3.11 or newer

1. Go to https://www.python.org/downloads/
2. Click **Download Python 3.x.x** (the big yellow button)
3. Run the installer
4. **IMPORTANT:** On the first screen, check **"Add Python to PATH"** before clicking Install
5. Click **Install Now**
6. When it finishes, open Command Prompt and verify:
   ```
   python --version
   ```
   You should see `Python 3.11.x` or higher.

### Git

1. Go to https://git-scm.com/download/win
2. Download and run the installer
3. Accept all defaults — the default options are fine
4. Verify in Command Prompt:
   ```
   git --version
   ```

---

## 2. Install the App

### Option A — Automated (recommended)

1. Create a folder for the app, e.g. `C:\Timesheet`
2. Open Command Prompt in that folder:
   - In File Explorer, navigate to the folder
   - Click the address bar, type `cmd`, press Enter
3. Clone the repository:
   ```
   git clone https://github.com/BASECAMP70/BASECAMPARB.git .
   ```
   (The `.` at the end means "clone into this folder")
4. When it finishes, you'll see all the app files in the folder
5. Double-click **SETUP.bat**
6. A black window will open — let it run until you see "Setup complete!"
7. Press any key to close it

SETUP.bat automatically:
- Installs all required Python packages
- Creates a **Start Timesheet** shortcut on your Desktop
- Sets up the weekly backup in Windows Task Scheduler

### Option B — Manual (if SETUP.bat fails)

**Step 1:** Open Command Prompt in the app folder and install packages:
```
pip install flask xhtml2pdf pypdf python-dotenv openpyxl
```

**Step 2:** Create `Start Timesheet.bat` on your Desktop.
Right-click your Desktop → New → Text Document, rename it to `Start Timesheet.bat`, then open it in Notepad and paste this (replace `C:\Timesheet` with your actual folder):

```bat
@echo off
taskkill /f /im pythonw.exe >nul 2>&1
if exist "C:\Timesheet\timesheet\__pycache__" rmdir /s /q "C:\Timesheet\timesheet\__pycache__"
cd /d "C:\Timesheet"
git pull
start "" /D "C:\Timesheet" pythonw -m flask --app timesheet.app:create_app run --host 0.0.0.0 --port 5000
timeout /t 3
```

Save and close Notepad.

**Step 3:** Set up the weekly backup manually — see [Section 7](#7-set-up-the-weekly-backup).

---

## 3. Restore Your Data

If you are setting up a fresh PC after a failure, you need to restore your data from the latest backup.

**The full backup ZIP is saved on Google Drive every Sunday.** Look in `Z:\My Drive\TIMESHEET\` for the most recent file, e.g. `timesheet-backup-2026-09-13.zip`.

### Restore steps

1. Open the backup ZIP file
2. Inside you'll see a `data/` folder containing JSON files
3. Copy all files from `data/` into:
   ```
   C:\Timesheet\timesheet\data\
   ```
   After copying you should have files like:
   - `C:\Timesheet\timesheet\data\clients.json`
   - `C:\Timesheet\timesheet\data\time_entries.json`
   - `C:\Timesheet\timesheet\data\projects.json`
   - etc.

4. Copy the `expense_receipts/` PDFs into:
   ```
   C:\Timesheet\timesheet\data\expense_pdfs\
   ```
   Note: the receipt files in the backup have readable names (e.g. `expense-2026-09-01-ClientName.pdf`) but the app stores them with UUID filenames. The expense records in the JSON already reference the correct UUID filenames — the receipts in the backup are a readable reference copy only.

### If you use Google Drive as your data folder

If your app is configured to read data from Google Drive (`Z:\My Drive\TIMESHEET\data`):
1. Install and sign in to **Google Drive for Desktop** — https://www.google.com/drive/download/
2. Mount it as drive `Z:` (this is the default)
3. The app will automatically read your data from there — no manual copy needed
4. See [Section 6](#6-set-up-google-drive-sync) for full Google Drive setup

---

## 4. Configure Settings

After installing and restoring data:

1. Double-click **Start Timesheet** on your Desktop
2. Wait 3 seconds, then open your browser and go to:
   ```
   http://127.0.0.1:5000
   ```
3. Click **Settings** in the top navigation
4. Fill in the following sections:

### Business Information
- **Business Name** — appears on invoices (e.g. Basecamp Consulting Inc.)
- **Address** — your full mailing address, appears on invoices
- **GST/HST Number** — your CRA registration number
- **GST Rate** — typically 0.05 (5%) for Alberta

### Email / SMTP
These settings are needed for the weekly backup email and for emailing invoices.
- **SMTP Host**: `smtp.gmail.com`
- **SMTP Port**: `587`
- **SMTP Username**: your full Gmail address (e.g. `scott@gmail.com`)
- **SMTP Password**: your Gmail App Password — **not your regular Gmail password**
  (See [Section 5](#5-set-up-gmail-app-password-smtp) for how to create one)

### Data Folder
- Leave blank to use the default local folder (`timesheet\data\` inside the app folder)
- Or enter `Z:\My Drive\TIMESHEET\data` to use Google Drive (recommended for multi-PC use)

### Appearance
- **Business Logo** — upload your logo (shown on invoices)
- **App Colors** — customize the navigation bar colour

Click **Save Settings** when done.

---

## 5. Set Up Gmail App Password (SMTP)

Gmail requires an "App Password" instead of your real password when sending email from scripts. Your regular Gmail password will not work.

**Note:** App Passwords require 2-Step Verification to be enabled on your Google account.

### Step 1 — Enable 2-Step Verification (if not already on)
1. Go to https://myaccount.google.com/security
2. Under "How you sign in to Google", click **2-Step Verification**
3. Follow the prompts to turn it on

### Step 2 — Create an App Password
1. Go to https://myaccount.google.com/apppasswords
   (If you don't see this option, 2-Step Verification is not enabled)
2. Under "App name", type `Timesheet Backup`
3. Click **Create**
4. Google shows a 16-character password like `abcd efgh ijkl mnop`
5. **Copy this password** — you won't see it again

### Step 3 — Enter it in the app
1. Open http://127.0.0.1:5000/settings
2. Paste the App Password into the **SMTP Password** field
3. Remove any spaces from the password before saving
4. Click **Save Settings**

---

## 6. Set Up Google Drive Sync

Google Drive lets your data be shared between two PCs and backed up automatically.

1. Download **Google Drive for Desktop**: https://www.google.com/drive/download/
2. Install and sign in with your Google account
3. In the Google Drive system tray icon → Settings → confirm it mounts as drive `Z:`
   - If it mounts as a different letter, you can change it in Google Drive settings
4. In the Timesheet app → Settings → Data Folder, enter:
   ```
   Z:\My Drive\TIMESHEET\data
   ```
5. Click **Save Settings**
6. The app immediately starts reading and writing to Google Drive

The weekly backup also saves the ZIP file to `Z:\My Drive\TIMESHEET\` automatically.

---

## 7. Set Up the Weekly Backup

SETUP.bat creates the scheduled task automatically. This section is for manual setup or verification.

### Verify the scheduled task exists

1. Search for **Task Scheduler** in the Start menu and open it
2. In the left panel, click **Task Scheduler Library**
3. Look for **Timesheet Weekly Backup** in the list
4. If it's there, right-click → **Run** to test it manually

### Create the task manually (if it's missing)

1. Open Task Scheduler
2. Click **Create Basic Task** in the right panel
3. **Name**: `Timesheet Weekly Backup`
4. Click Next → **Trigger**: Weekly
5. Click Next → Check **Sunday**, Start time: **8:00 AM**
6. Click Next → **Action**: Start a program
7. Fill in:
   - **Program/script**: `cmd`
   - **Add arguments**: `/c "cd /d "C:\Timesheet" && python send_backup.py >> send_backup.log 2>&1"`
   - **Start in**: `C:\Timesheet`
   (Replace `C:\Timesheet` with your actual install folder)
8. Click Next → check **Open the Properties dialog** → Finish
9. In Properties → **General** tab → check **Run with highest privileges**
10. Click OK

### What the backup does each Sunday at 8 AM
- Generates an Excel export of all time, expenses, and invoices
- Builds a full ZIP with JSON data, PDFs, and app source code
- Saves the ZIP to Google Drive (`Z:\My Drive\TIMESHEET\`)
- Emails the Excel spreadsheet to scott@basecampinc.ca
- Logs progress to `send_backup.log` in the app folder

---

## 8. Set Up a Second PC

To access the timesheet from a second computer on the same network:

### Option A — Access the main PC's app over the network

1. On the **main PC**, double-click **Start Timesheet** to launch
2. Find the main PC's local IP address:
   - Open Command Prompt and run `ipconfig`
   - Look for **IPv4 Address** under your network adapter (e.g. `192.168.1.100`)
3. On the **second PC**, open a browser and go to:
   ```
   http://192.168.1.100:5000
   ```
   (Replace with the actual IP of the main PC)

This means the main PC must be running for the second PC to access the app.

### Option B — Install the app on the second PC too

Both PCs can run their own copy of the app, both reading from Google Drive:

1. Follow [Section 2](#2-install-the-app) on the second PC
2. In Settings, set the data folder to `Z:\My Drive\TIMESHEET\data`
3. Both PCs read and write the same data files via Google Drive

**Important:** Do not have both apps writing to the same data at exactly the same time — edits made on one PC appear on the other after Google Drive syncs (usually within seconds).

The second PC uses `start_timesheet.bat` (in the app folder) instead of the Desktop shortcut. It automatically runs `git pull` to get the latest code updates when launched.

---

## 9. Starting and Stopping the App

### Start
Double-click **Start Timesheet** on the Desktop.
- Kills any old running instance first
- Pulls the latest code from GitHub
- Starts Flask in the background (no console window)
- Open http://127.0.0.1:5000 in your browser

### Stop
The app runs silently in the background. To stop it:
- Open Task Manager (Ctrl+Shift+Esc)
- Find **pythonw.exe** under Background Processes
- Right-click → **End Task**

Or open Command Prompt and run:
```
taskkill /f /im pythonw.exe
```

### Restart (after a code update)
Just double-click **Start Timesheet** again — it kills the old instance automatically.

---

## 10. Updating the App

Updates are pulled automatically every time you launch via the Desktop shortcut (it runs `git pull`).

To update manually:
1. Open Command Prompt in the app folder
2. Run:
   ```
   git pull
   ```
3. Restart the app (double-click **Start Timesheet**)

---

## 11. Troubleshooting

### "Page not found" or browser can't connect
- The app may not be running. Double-click **Start Timesheet**
- Wait 3–5 seconds after launching before opening the browser
- Make sure you're going to `http://127.0.0.1:5000` (not https)

### Changes to the app aren't showing up
An old version of Flask may still be running. Fix:
1. Open Command Prompt and run:
   ```
   taskkill /f /im pythonw.exe
   ```
2. Double-click **Start Timesheet** again

### "Access is denied" when killing the old process
Run Command Prompt as Administrator and try again, or use PowerShell:
```powershell
(Get-WmiObject Win32_Process -Filter "Name='pythonw.exe'").Terminate()
```

### Backup email not arriving
1. Check `send_backup.log` in the app folder for error details
2. Verify SMTP settings in Settings — use an App Password, not your Gmail password
3. Make sure 2-Step Verification is enabled on your Google account
4. Run the backup manually to test:
   ```
   python send_backup.py
   ```

### Google Drive not mounting as Z:
1. Open Google Drive for Desktop settings (system tray icon → gear icon)
2. Go to **Google Drive** tab → ensure **Mirror files** or **Stream files** is selected
3. Under drive letter, change to Z: if needed
4. Restart Google Drive

### Python packages missing after update
```
pip install flask xhtml2pdf pypdf python-dotenv openpyxl
```

### Port 5000 already in use
Another program is using port 5000. Kill all pythonw.exe instances (see above), then restart.

---

## 12. What's in the Weekly Backup ZIP

The full backup ZIP is saved to Google Drive every Sunday. The email contains only the Excel file (Google blocks script files in email attachments).

| Path in ZIP | Contents |
|---|---|
| `timesheet-backup-YYYY-MM-DD.xlsx` | All time, expenses, and invoices in Excel (3 tabs) |
| `data/clients.json` | Client records |
| `data/projects.json` | Project and subproject records |
| `data/time_entries.json` | All time entries |
| `data/expenses.json` | All expense records |
| `data/invoices.json` | All invoice records |
| `data/settings.json` | App settings (SMTP, GST rate, business info) |
| `expense_receipts/` | Uploaded receipt PDFs, renamed to readable filenames |
| `invoices/` | Generated invoice PDFs for every invoice |
| `app/timesheet/` | Full app source code (Python, templates, static files) |
| `app/send_backup.py` | The backup script itself |
| `app/SETUP.md` | This guide |

**To do a full restore:** Install Python + Git → clone from GitHub → run SETUP.bat → copy `data/` from ZIP into `timesheet\data\`.
