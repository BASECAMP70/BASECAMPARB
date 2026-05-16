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
