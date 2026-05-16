import copy
import json
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

DEFAULTS = {
    "projects.json": [],
    "time_entries.json": [],
    "expenses.json": [],
    "invoices.json": [],
    "settings.json": {
        "business_name": "",
        "gst_number": "",
        "gst_rate": 0.05,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
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
