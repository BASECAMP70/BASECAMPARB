def test_settings_get(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"Business Name" in r.data


def test_settings_post_saves(client):
    r = client.post("/settings", data={
        "business_name": "ACME Co",
        "gst_number": "123RT",
        "gst_rate": "0.05",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_user": "a@b.com",
        "smtp_password": "secret",
    }, follow_redirects=True)
    assert r.status_code == 200
    import timesheet.storage as storage
    s = storage.load_settings()
    assert s["business_name"] == "ACME Co"


def test_projects_empty(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert b"No projects" in r.data


def test_add_project(client):
    r = client.post("/projects/add", data={
        "name": "Client Alpha", "rate": "150.00"
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Client Alpha" in r.data


def test_deactivate_project(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Old", "rate": 100.0, "currency": "CAD", "active": True}])
    r = client.post("/projects/p1/deactivate", follow_redirects=True)
    assert r.status_code == 200
    assert storage.load_projects()[0]["active"] is False


def test_dashboard_post_creates_entry(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Alpha", "rate": 100.0, "currency": "CAD", "active": True}])
    r = client.post("/", data={
        "project_id": "p1", "date": "2026-05-16", "hours": "3.0", "description": "Design work"
    }, follow_redirects=True)
    assert r.status_code == 200
    entries = storage.load_time_entries()
    assert len(entries) == 1
    assert entries[0]["hours"] == 3.0
    assert entries[0]["invoiced"] is False


def test_time_entries_page(client):
    r = client.get("/time")
    assert r.status_code == 200


def test_time_add(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Alpha", "rate": 100.0, "currency": "CAD", "active": True}])
    r = client.post("/time/add", data={
        "project_id": "p1", "date": "2026-05-16", "hours": "1.5", "description": "Review"
    }, follow_redirects=True)
    assert r.status_code == 200
    assert len(storage.load_time_entries()) == 1


def test_time_delete_blocks_invoiced(client):
    import timesheet.storage as storage
    storage.save_time_entries([{
        "id": "e1", "project_id": "p1", "date": "2026-05-16",
        "hours": 1.0, "description": "Done", "invoiced": True
    }])
    r = client.post("/time/e1/delete", follow_redirects=True)
    assert len(storage.load_time_entries()) == 1  # not deleted


def test_time_edit_blocks_invoiced(client):
    import timesheet.storage as storage
    storage.save_time_entries([{
        "id": "e1", "project_id": "p1", "date": "2026-05-16",
        "hours": 1.0, "description": "Done", "invoiced": True
    }])
    r = client.get("/time/e1/edit", follow_redirects=True)
    assert r.status_code == 200
    # Entry must not be editable — still invoiced and unchanged
    assert storage.load_time_entries()[0]["invoiced"] is True
    r2 = client.post("/time/e1/edit", data={
        "project_id": "p1", "date": "2026-05-16", "hours": "9.0", "description": "Hacked"
    }, follow_redirects=True)
    assert storage.load_time_entries()[0]["hours"] == 1.0  # unchanged


def test_expenses_add_no_receipt(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Alpha", "rate": 100.0, "currency": "CAD", "active": True}])
    r = client.post("/expenses/add", data={
        "project_id": "p1", "date": "2026-05-16", "amount": "49.99", "description": "Supplies"
    }, follow_redirects=True)
    assert r.status_code == 200
    exp = storage.load_expenses()
    assert len(exp) == 1
    assert exp[0]["amount"] == 49.99
    assert exp[0]["pdf_filename"] is None


def test_expenses_add_with_receipt(client, isolated_data_dir):
    import timesheet.storage as storage
    from io import BytesIO
    storage.save_projects([{"id": "p1", "name": "Alpha", "rate": 100.0, "currency": "CAD", "active": True}])
    pdf_data = b"%PDF-1.4 fake receipt"
    r = client.post("/expenses/add", data={
        "project_id": "p1", "date": "2026-05-16", "amount": "25.00", "description": "Receipt",
        "receipt": (BytesIO(pdf_data), "receipt.pdf"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    exp = storage.load_expenses()
    assert exp[0]["pdf_filename"] is not None
    receipt_path = isolated_data_dir / "expense_pdfs" / exp[0]["pdf_filename"]
    assert receipt_path.exists()


def test_invoices_page(client):
    r = client.get("/invoices")
    assert r.status_code == 200


def test_generate_invoice(client, monkeypatch):
    import timesheet.storage as storage
    from unittest.mock import patch
    storage.save_projects([{"id": "p1", "name": "ACME", "rate": 100.0, "currency": "CAD", "active": True}])
    storage.save_time_entries([{
        "id": "e1", "project_id": "p1", "date": "2026-05-16",
        "hours": 2.0, "description": "Work", "invoiced": False
    }])
    storage.save_settings({"business_name": "Me", "gst_number": "", "gst_rate": 0.05,
                            "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": ""})
    with patch("timesheet.app.pdf.generate_invoice_pdf", return_value=b"%PDF"):
        r = client.post("/invoices/generate", data={
            "project_id": "p1", "client_name": "ACME Corp"
        }, follow_redirects=True)
    assert r.status_code == 200
    invoices = storage.load_invoices()
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "INV-001"
    assert invoices[0]["total"] == round(200.0 * 1.05, 2)
    # time entry is now invoiced
    assert storage.load_time_entries()[0]["invoiced"] is True
