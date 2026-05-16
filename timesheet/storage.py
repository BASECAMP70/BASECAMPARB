import copy
import json
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

DEFAULTS = {
    "clients.json": [],
    "projects.json": [],
    "time_entries.json": [],
    "expenses.json": [],
    "invoices.json": [],
    "settings.json": {
        "business_name": "",
        "business_address": "",
        "gst_number": "",
        "gst_rate": 0.05,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "invoice_brand_color": "#1D1E1C",
        "invoice_bg_color": "#FFFFFF",
        "invoice_logo_filename": None,
        "app_nav_color": "#1a1a2e",
        "app_accent_color": "#4f8ef7",
    },
}


def _load(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return copy.deepcopy(DEFAULTS[filename])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULTS[filename])


def _save(filename, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / filename).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def new_id():
    return str(uuid.uuid4())


def load_clients():
    return _load("clients.json")

def save_clients(data):
    _save("clients.json", data)

def load_projects():
    return _load("projects.json")

def save_projects(data):
    _save("projects.json", data)

def load_time_entries():
    return _load("time_entries.json")

def save_time_entries(data):
    _save("time_entries.json", data)

def load_expenses():
    return _load("expenses.json")

def save_expenses(data):
    _save("expenses.json", data)

def load_invoices():
    return _load("invoices.json")

def save_invoices(data):
    _save("invoices.json", data)

def load_settings():
    return _load("settings.json")

def save_settings(data):
    _save("settings.json", data)
