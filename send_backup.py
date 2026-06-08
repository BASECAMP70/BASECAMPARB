"""
Weekly timesheet backup emailer.
Generates the Excel export and emails it to the configured recipient.
Run via Windows Task Scheduler every Sunday.
"""
import sys
import smtplib
from io import BytesIO
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Allow running from any directory
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from timesheet import storage

RECIPIENT = "scott@basecampinc.ca"


def build_excel():
    wb = Workbook()

    def style_header(ws, headers):
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1D3557")
            cell.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"

    def autofit(ws):
        for col in ws.columns:
            width = max((len(str(c.value or "")) for c in col), default=10) + 2
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 50)

    projects = {p["id"]: p for p in storage.load_projects()}
    clients  = {c["id"]: c for c in storage.load_clients()}

    # Time entries
    ws = wb.active
    ws.title = "Time"
    style_header(ws, ["Date", "Client", "Project", "Hours", "Rate", "Amount", "Description", "Invoiced"])
    all_entries = sorted(storage.load_time_entries(), key=lambda x: x["date"])
    for e in all_entries:
        p = projects.get(e.get("project_id", ""), {})
        c = clients.get(p.get("client_id", ""), {})
        rate = e.get("rate", p.get("rate", 0))
        ws.append([
            e["date"], c.get("name", ""), p.get("name", ""),
            e["hours"], rate, round(e["hours"] * rate, 2),
            e.get("description", ""), "Yes" if e.get("invoiced") else "No",
        ])
    autofit(ws)

    # Expenses
    ws2 = wb.create_sheet("Expenses")
    style_header(ws2, ["Date", "Client", "Description", "Amount", "Invoiced", "Receipt"])
    all_expenses = sorted(storage.load_expenses(), key=lambda x: x["date"])
    for x in all_expenses:
        c = clients.get(x.get("client_id", ""), {})
        ws2.append([
            x["date"], c.get("name", ""), x.get("description", ""),
            x["amount"], "Yes" if x.get("invoiced") else "No",
            x.get("pdf_filename", ""),
        ])
    autofit(ws2)

    # Invoices
    ws3 = wb.create_sheet("Invoices")
    style_header(ws3, ["Invoice #", "Type", "Client", "Issue Date", "Subtotal", "GST", "Total", "Status"])
    for inv in sorted(storage.load_invoices(), key=lambda x: x.get("invoice_number", "")):
        ws3.append([
            inv.get("invoice_number", ""), inv.get("invoice_type", "time"),
            inv.get("client_name", ""), inv.get("issued_date", ""),
            inv.get("subtotal", 0), inv.get("gst", 0), inv.get("total", 0),
            inv.get("status", "draft"),
        ])
    autofit(ws3)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue(), all_entries, all_expenses


def date_range_label(all_entries, all_expenses):
    dates = (
        [e["date"] for e in all_entries] +
        [x["date"] for x in all_expenses]
    )
    if not dates:
        return date.today().strftime("%Y-%m-%d")
    return f"{min(dates)} to {max(dates)}"


def send_backup():
    settings = storage.load_settings()
    smtp_host = settings.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_user = settings.get("smtp_user", "")
    smtp_password = settings.get("smtp_password", "")

    if not smtp_user or not smtp_password:
        print("ERROR: SMTP credentials not configured in Settings.")
        sys.exit(1)

    excel_bytes, all_entries, all_expenses = build_excel()
    dr = date_range_label(all_entries, all_expenses)
    today = date.today().strftime("%Y-%m-%d")
    filename = f"timesheet-backup-{today}.xlsx"
    subject = f"Timesheet Backup {dr}"

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(f"Weekly timesheet backup attached.\n\nDate range: {dr}", "plain"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(excel_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, RECIPIENT, msg.as_string())

    print(f"Backup sent to {RECIPIENT} — subject: {subject}")


if __name__ == "__main__":
    send_backup()
