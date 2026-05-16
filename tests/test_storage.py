import json
import pytest
from pathlib import Path


def test_load_projects_returns_empty_list_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    assert storage.load_projects() == []


def test_save_and_load_projects(tmp_path, monkeypatch):
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    project = {"id": "abc", "name": "Test", "rate": 100.0, "currency": "CAD", "active": True}
    storage.save_projects([project])
    loaded = storage.load_projects()
    assert loaded == [project]


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    settings = storage.load_settings()
    assert settings["gst_rate"] == 0.05
    assert settings["smtp_host"] == "smtp.gmail.com"


def test_save_and_load_time_entries(tmp_path):
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    entry = {"id": "e1", "project_id": "p1", "date": "2026-05-16",
              "hours": 2.5, "description": "Work", "invoiced": False}
    storage.save_time_entries([entry])
    assert storage.load_time_entries() == [entry]


def test_save_and_load_expenses(tmp_path):
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    expense = {"id": "x1", "project_id": "p1", "date": "2026-05-16",
                "amount": 49.99, "description": "Supplies", "invoiced": False}
    storage.save_expenses([expense])
    assert storage.load_expenses() == [expense]


def test_save_and_load_invoices(tmp_path):
    from timesheet import storage
    storage.DATA_DIR = tmp_path
    invoice = {"id": "i1", "invoice_number": "INV-001", "project_id": "p1",
                "client_name": "ACME", "issued_date": "2026-05-16",
                "subtotal": 100.0, "gst": 5.0, "total": 105.0,
                "sent": False, "line_items": []}
    storage.save_invoices([invoice])
    assert storage.load_invoices() == [invoice]
