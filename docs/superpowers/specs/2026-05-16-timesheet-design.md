# Timesheet Tracking App — Design Spec

**Date:** 2026-05-16  
**Status:** Approved

---

## Overview

A localhost timesheet tracking app for a solo freelancer. Tracks time by project, logs expenses, generates PDF invoices with Canadian GST, and emails them via Gmail SMTP. No JavaScript framework, no build step — Flask + Jinja2 with server-rendered HTML.

---

## Architecture

**Stack:**
- Python 3.11+
- Flask (web framework + Jinja2 templates)
- WeasyPrint (HTML → PDF generation)
- smtplib / email (stdlib, Gmail SMTP)
- python-dotenv (SMTP credentials from `.env`)

**Storage:** JSON files in `data/`. No database, no ORM, no migrations. Suitable for a solo user with hundreds of entries.

**Project structure:**
```
timesheet/
├── app.py                  # Flask app, all routes
├── .env                    # SMTP credentials (not committed)
├── data/
│   ├── projects.json
│   ├── time_entries.json
│   ├── expenses.json
│   ├── invoices.json
│   └── settings.json
├── templates/
│   ├── base.html           # Layout, nav (Dashboard, Projects, Time, Expenses, Invoices, Reports, Settings)
│   ├── dashboard.html      # Quick time entry form + today's entries
│   ├── projects.html       # Manage projects
│   ├── time.html           # Time entry list/edit
│   ├── expenses.html       # Expense list/edit
│   ├── invoices.html       # Generate & send invoices
│   ├── invoice_pdf.html    # PDF template (WeasyPrint)
│   ├── report_monthly.html # Monthly totals report
│   ├── report_uninvoiced.html # Uninvoiced hours report
│   └── settings.html       # Business info + SMTP config
└── requirements.txt
```

---

## Data Models

All data stored as JSON arrays. IDs are UUIDs generated via Python's `uuid` module.

### projects.json
```json
[
  {
    "id": "uuid",
    "name": "Client ABC Website",
    "rate": 125.00,
    "currency": "CAD",
    "active": true
  }
]
```

### time_entries.json
```json
[
  {
    "id": "uuid",
    "project_id": "uuid",
    "date": "2026-05-16",
    "hours": 2.5,
    "description": "Homepage design",
    "invoiced": false
  }
]
```

### expenses.json
```json
[
  {
    "id": "uuid",
    "project_id": "uuid",
    "date": "2026-05-16",
    "amount": 49.99,
    "description": "Stock photos",
    "invoiced": false
  }
]
```

### invoices.json
```json
[
  {
    "id": "uuid",
    "invoice_number": "INV-001",
    "project_id": "uuid",
    "client_name": "Client ABC",
    "issued_date": "2026-05-16",
    "subtotal": 362.49,
    "gst": 18.12,
    "total": 380.61,
    "sent": true,
    "line_items": [
      { "type": "time", "date": "2026-05-16", "description": "Homepage design", "hours": 2.5, "rate": 125.00, "amount": 312.50 },
      { "type": "expense", "date": "2026-05-16", "description": "Stock photos", "amount": 49.99 }
    ]
  }
]
```

Line items are snapshot at the time of invoice generation and stored in `invoices.json`. PDFs are regenerated on demand from this stored snapshot (not from the live `time_entries.json` / `expenses.json` data), ensuring past invoices always render consistently even if entries are later edited or deleted.

### settings.json
```json
{
  "business_name": "Scott Consulting",
  "gst_number": "123456789RT0001",
  "gst_rate": 0.05,
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "",
  "smtp_password": ""
}
```

**Note:** SMTP credentials can also be set in `.env` as `SMTP_USER` and `SMTP_PASSWORD`, which override `settings.json` values at startup. `.env` is gitignored.

**Invoiced flag:** The `invoiced: true` flag on time entries and expenses prevents double-billing. Once entries are included on a generated invoice they are locked from appearing on future invoices.

---

## Pages & Routes

### Dashboard — `GET/POST /`
- Quick time entry form: project dropdown (active projects only), date (default today), hours, description.
- POST creates a new time entry and redirects back.
- Lists today's entries below the form with edit/delete links.

### Projects — `GET /projects`, `POST /projects/add`, `POST /projects/<id>/edit`, `POST /projects/<id>/deactivate`
- List all projects (name, hourly rate, active status).
- Add new project via inline form.
- Edit existing project (name, rate).
- Deactivate project — hidden from entry forms but preserved in historical data.

### Time Entries — `GET /time`, `POST /time/add`, `GET /time/<id>/edit`, `POST /time/<id>/edit`, `POST /time/<id>/delete`
- Table of all time entries, filterable by project and date range.
- Manual add via form on the `/time` page (for corrections outside of the dashboard quick-entry form), plus edit and delete.
- Invoiced entries shown with a lock indicator; editing blocked.

### Expenses — `GET /expenses`, `POST /expenses/add`, `GET /expenses/<id>/edit`, `POST /expenses/<id>/edit`, `POST /expenses/<id>/delete`
- Table of all expenses, filterable by project and date range.
- Add/edit/delete: project, date, amount (CAD), description.
- Invoiced expenses locked from editing.

### Invoices — `GET /invoices`, `POST /invoices/generate`, `GET /invoices/<id>/pdf`, `POST /invoices/<id>/send`
- Select a project → see all uninvoiced time entries and expenses.
- Preview: subtotal (hours × rate + expenses), GST (5%), total (CAD).
- "Generate Invoice": creates PDF in memory via WeasyPrint, saves invoice record to `invoices.json`, marks included entries as `invoiced: true`. Auto-increments invoice number (INV-001, INV-002, …).
- Invoice list: past invoices with "Download PDF" and "Email Invoice" buttons.
- Email flow: modal with recipient email, pre-filled subject (`Invoice INV-001 from [Business Name]`), short body, sends via Gmail SMTP with PDF attached.

### Reports — `GET /reports/monthly`, `GET /reports/uninvoiced`

**Monthly Totals** (`/reports/monthly`)
- Filter by month/year (defaults to current month).
- Table grouped by project showing: total hours, billable amount (hours × rate), total expenses, and combined total.
- Grand total row across all projects for the selected month.
- Includes both invoiced and uninvoiced entries (full picture of work done).

**Uninvoiced Hours** (`/reports/uninvoiced`)
- Lists all time entries and expenses where `invoiced: false`, grouped by project.
- Per-project subtotal: hours, billable amount, expenses, combined.
- Grand total at the bottom.
- Quick-link to the invoices page to generate an invoice for that project.

### Settings — `GET/POST /settings`
- Business name, GST number, GST rate (default 5%).
- SMTP host, port, Gmail address, App Password.
- Saved to `settings.json`. Credentials also loadable from `.env`.

---

## Invoice PDF

Generated from `invoice_pdf.html` by WeasyPrint. Contains:
- Business name
- Client name
- Invoice number and issue date
- Line items: time entries (date, description, hours, rate, amount) and expenses (date, description, amount)
- Subtotal
- GST (5% — rate configurable in settings)
- **Total (CAD)**

No logo, no payment terms, no due date in initial version.

---

## Email Delivery

- Library: Python stdlib `smtplib` + `email.mime`
- Auth: Gmail App Password (not account password)
- PDF attached as `invoice_XXX.pdf`
- TLS via `STARTTLS` on port 587
- Errors surfaced as a flash message on the invoices page

---

## Error Handling

- Missing/corrupt JSON files: app creates empty defaults on startup.
- SMTP send failure: flash error message, invoice not marked as sent.
- WeasyPrint failure: flash error, no invoice record created.
- Invalid form input: re-render form with validation messages.

---

## Out of Scope (v1)

- Multi-user / authentication
- Recurring invoices
- Payment tracking / "paid" status
- Logo on invoice
- Due dates / payment terms
- Currency conversion
- PostgreSQL / SQLite migration
