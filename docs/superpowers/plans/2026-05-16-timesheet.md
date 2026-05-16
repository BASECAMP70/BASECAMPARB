# Timesheet Tracking App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost Flask timesheet app for a solo freelancer with time tracking, expenses, PDF invoice generation with Canadian GST, Gmail SMTP email, and two reports.

**Architecture:** Flask + Jinja2 server-rendered HTML. All data stored in JSON files under `timesheet/data/`. Business logic split across `storage.py` (JSON I/O), `pdf.py` (WeasyPrint), and `mailer.py` (Gmail SMTP). All routes live in `app.py`.

**Tech Stack:** Python 3.11+, Flask, WeasyPrint, pypdf, python-dotenv, pytest, smtplib (stdlib)

---

## File Map

| File | Responsibility |
|------|---------------|
| `timesheet/app.py` | Flask app factory, all routes |
| `timesheet/storage.py` | JSON load/save helpers for all 5 data files |
| `timesheet/data/expense_pdfs/` | Uploaded expense receipt PDFs (auto-created) |
| `timesheet/pdf.py` | WeasyPrint invoice PDF + pypdf merge with expense receipts |
| `timesheet/mailer.py` | Gmail SMTP send with PDF attachment |
| `timesheet/data/*.json` | Persistent data (auto-created on first run) |
| `timesheet/templates/base.html` | Layout shell with nav bar |
| `timesheet/templates/dashboard.html` | Quick time-entry form + today's entries |
| `timesheet/templates/projects.html` | Project list, add, edit, deactivate |
| `timesheet/templates/time.html` | Time entry table, add, edit, delete |
| `timesheet/templates/expenses.html` | Expense table, add (with PDF receipt upload), edit, delete |
| `timesheet/templates/invoices.html` | Invoice list, preview, generate, email modal |
| `timesheet/templates/invoice_pdf.html` | PDF-only invoice template (WeasyPrint) |
| `timesheet/templates/report_monthly.html` | Monthly totals by project |
| `timesheet/templates/report_uninvoiced.html` | Uninvoiced hours by project |
| `timesheet/templates/settings.html` | Business info + SMTP settings form |
| `timesheet/requirements.txt` | Python dependencies |
| `timesheet/.env.example` | Example env file (committed) |
| `timesheet/.gitignore` | Ignores .env and data/ |
| `tests/conftest.py` | pytest fixtures (Flask test client, temp data dir) |
| `tests/test_storage.py` | Storage layer unit tests |
| `tests/test_routes.py` | Route smoke tests |
| `tests/test_invoice_calc.py` | Invoice calculation tests |

---

## Task 1: Project Scaffold

**Files:**
- Create: `timesheet/requirements.txt`
- Create: `timesheet/.env.example`
- Create: `timesheet/.gitignore`
- Create: `timesheet/data/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p timesheet/data timesheet/templates tests
touch timesheet/data/.gitkeep
```

- [ ] **Step 2: Write requirements.txt**

```
flask>=3.0.0
weasyprint>=62.0
pypdf>=4.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-flask>=1.3.0
```

- [ ] **Step 3: Write .env.example**

```
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-app-password
```

- [ ] **Step 4: Write .gitignore**

```
.env
data/*.json
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: Install dependencies**

```bash
cd timesheet
pip install -r requirements.txt
```

Expected: All packages install without error.

- [ ] **Step 6: Commit**

```bash
git add timesheet/ tests/
git commit -m "chore: project scaffold for timesheet app"
```

---

## Task 2: Storage Layer

**Files:**
- Create: `timesheet/storage.py`
- Create: `tests/conftest.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests for storage layer**

Create `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd timesheet
python -m pytest ../tests/test_storage.py -v
```

Expected: ImportError or ModuleNotFoundError (storage.py doesn't exist yet).

- [ ] **Step 3: Write storage.py**

Create `timesheet/storage.py`:

```python
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
        return DEFAULTS[filename]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULTS[filename]


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
```

Also create `timesheet/__init__.py` (empty):

```bash
touch timesheet/__init__.py
```

- [ ] **Step 4: Write conftest.py**

Create `tests/conftest.py`:

```python
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    import timesheet.storage as storage
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def app(isolated_data_dir):
    from timesheet.app import create_app
    app = create_app({"TESTING": True, "DATA_DIR": str(isolated_data_dir)})
    return app


@pytest.fixture
def client(app):
    return app.test_client()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest ../tests/test_storage.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/storage.py timesheet/__init__.py tests/
git commit -m "feat: storage layer with JSON load/save helpers"
```

---

## Task 3: Flask App Skeleton + Base Template

**Files:**
- Create: `timesheet/app.py`
- Create: `timesheet/templates/base.html`

- [ ] **Step 1: Write app.py skeleton**

Create `timesheet/app.py`:

```python
import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from dotenv import load_dotenv
import timesheet.storage as storage

load_dotenv()


def create_app(config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-timesheet")

    if config:
        app.config.update(config)

    # Inject settings into every template
    @app.context_processor
    def inject_settings():
        return {"settings": storage.load_settings()}

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
```

- [ ] **Step 2: Write base.html**

Create `timesheet/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Timesheet{% endblock %} — {{ settings.business_name or 'Timesheet' }}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #222; }
    nav { background: #1a1a2e; color: #fff; padding: 0 1.5rem; display: flex; align-items: center; gap: 1.5rem; height: 52px; }
    nav a { color: #ccc; text-decoration: none; font-size: 0.9rem; padding: 4px 0; }
    nav a:hover, nav a.active { color: #fff; border-bottom: 2px solid #4f8ef7; }
    nav .brand { font-weight: 700; color: #fff; font-size: 1rem; margin-right: 1rem; }
    .container { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }
    h1 { font-size: 1.5rem; margin-bottom: 1.25rem; }
    h2 { font-size: 1.2rem; margin-bottom: 1rem; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    th { background: #f0f0f0; text-align: left; padding: 10px 12px; font-size: 0.85rem; color: #555; }
    td { padding: 10px 12px; border-top: 1px solid #eee; font-size: 0.9rem; }
    tr:hover td { background: #fafafa; }
    .btn { display: inline-block; padding: 7px 16px; border-radius: 4px; border: none; cursor: pointer; font-size: 0.875rem; text-decoration: none; }
    .btn-primary { background: #4f8ef7; color: #fff; }
    .btn-primary:hover { background: #3a7be0; }
    .btn-danger { background: #e74c3c; color: #fff; }
    .btn-danger:hover { background: #c0392b; }
    .btn-sm { padding: 4px 10px; font-size: 0.8rem; }
    .btn-secondary { background: #eee; color: #333; }
    .btn-secondary:hover { background: #ddd; }
    form.inline { display: inline; }
    .card { background: #fff; border-radius: 6px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 1.5rem; }
    .form-group { margin-bottom: 1rem; }
    label { display: block; font-size: 0.85rem; color: #555; margin-bottom: 4px; }
    input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; }
    input:focus, select:focus { outline: none; border-color: #4f8ef7; }
    .flash { padding: 10px 16px; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9rem; }
    .flash-error { background: #fde8e8; color: #c0392b; }
    .flash-success { background: #e8f8e8; color: #27ae60; }
    .locked { color: #aaa; font-size: 0.8rem; }
    .text-right { text-align: right; }
    .text-muted { color: #888; font-size: 0.85rem; }
    .totals-table td { font-weight: 600; }
    .grand-total td { background: #f0f0f0; font-weight: 700; }
    .modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:100; align-items:center; justify-content:center; }
    .modal-overlay.open { display:flex; }
    .modal { background:#fff; border-radius:8px; padding:2rem; width:480px; max-width:95vw; }
    .modal h2 { margin-bottom:1rem; }
  </style>
</head>
<body>
<nav>
  <span class="brand">⏱ Timesheet</span>
  <a href="{{ url_for('dashboard') }}" class="{{ 'active' if request.endpoint == 'dashboard' }}">Dashboard</a>
  <a href="{{ url_for('projects') }}" class="{{ 'active' if request.endpoint == 'projects' }}">Projects</a>
  <a href="{{ url_for('time_entries') }}" class="{{ 'active' if request.endpoint == 'time_entries' }}">Time</a>
  <a href="{{ url_for('expenses') }}" class="{{ 'active' if request.endpoint == 'expenses' }}">Expenses</a>
  <a href="{{ url_for('invoices') }}" class="{{ 'active' if request.endpoint == 'invoices' }}">Invoices</a>
  <a href="{{ url_for('report_monthly') }}" class="{{ 'active' if 'report' in (request.endpoint or '') }}">Reports</a>
  <a href="{{ url_for('settings') }}" class="{{ 'active' if request.endpoint == 'settings' }}">Settings</a>
</nav>
<div class="container">
  {% for category, message in get_flashed_messages(with_categories=True) %}
    <div class="flash flash-{{ category }}">{{ message }}</div>
  {% endfor %}
  {% block content %}{% endblock %}
</div>
</body>
</html>
```

- [ ] **Step 3: Create a stub dashboard template**

Create `timesheet/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1>Dashboard</h1>
<p>App is running.</p>
{% endblock %}
```

- [ ] **Step 4: Run the app to verify it starts**

```bash
cd timesheet
python app.py
```

Expected: `* Running on http://127.0.0.1:5000` — open browser to verify nav renders.

- [ ] **Step 5: Commit**

```bash
git add timesheet/app.py timesheet/templates/
git commit -m "feat: flask app skeleton with base template and nav"
```

---

## Task 4: Settings Page

**Files:**
- Modify: `timesheet/app.py` (add settings routes)
- Create: `timesheet/templates/settings.html`
- Create: `tests/test_routes.py` (start route smoke tests here)

- [ ] **Step 1: Write failing route test**

Create `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_settings_get -v
```

Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Add settings routes to app.py**

Add inside `create_app()`, after the dashboard route:

```python
    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            s = storage.load_settings()
            s.update({
                "business_name": request.form["business_name"].strip(),
                "gst_number": request.form["gst_number"].strip(),
                "gst_rate": float(request.form.get("gst_rate", 0.05)),
                "smtp_host": request.form["smtp_host"].strip(),
                "smtp_port": int(request.form.get("smtp_port", 587)),
                "smtp_user": request.form["smtp_user"].strip(),
                "smtp_password": request.form["smtp_password"].strip(),
            })
            storage.save_settings(s)
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        return render_template("settings.html", s=storage.load_settings())
```

- [ ] **Step 4: Write settings.html**

Create `timesheet/templates/settings.html`:

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block content %}
<h1>Settings</h1>
<div class="card">
  <form method="post">
    <h2>Business Info</h2>
    <div class="form-group">
      <label>Business Name</label>
      <input name="business_name" value="{{ s.business_name }}">
    </div>
    <div class="form-group">
      <label>GST Number</label>
      <input name="gst_number" value="{{ s.gst_number }}">
    </div>
    <div class="form-group">
      <label>GST Rate (e.g. 0.05 for 5%)</label>
      <input name="gst_rate" type="number" step="0.001" value="{{ s.gst_rate }}">
    </div>
    <h2 style="margin-top:1.5rem">Email (SMTP)</h2>
    <div class="form-group">
      <label>SMTP Host</label>
      <input name="smtp_host" value="{{ s.smtp_host }}">
    </div>
    <div class="form-group">
      <label>SMTP Port</label>
      <input name="smtp_port" type="number" value="{{ s.smtp_port }}">
    </div>
    <div class="form-group">
      <label>Gmail Address</label>
      <input name="smtp_user" type="email" value="{{ s.smtp_user }}">
    </div>
    <div class="form-group">
      <label>App Password</label>
      <input name="smtp_password" type="password" value="{{ s.smtp_password }}" placeholder="Gmail App Password">
    </div>
    <button class="btn btn-primary" type="submit">Save Settings</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: Both settings tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/settings.html tests/test_routes.py
git commit -m "feat: settings page with SMTP and business info"
```

---

## Task 5: Projects

**Files:**
- Modify: `timesheet/app.py` (add project routes)
- Create: `timesheet/templates/projects.html`
- Modify: `tests/test_routes.py` (add project tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_projects_empty -v
```

Expected: FAIL — route doesn't exist.

- [ ] **Step 3: Add project routes to app.py**

```python
    @app.route("/projects")
    def projects():
        return render_template("projects.html", projects=storage.load_projects())

    @app.route("/projects/add", methods=["POST"])
    def projects_add():
        name = request.form["name"].strip()
        rate = float(request.form.get("rate", 0))
        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("projects"))
        projects = storage.load_projects()
        projects.append({"id": storage.new_id(), "name": name, "rate": rate, "currency": "CAD", "active": True})
        storage.save_projects(projects)
        flash(f"Project '{name}' added.", "success")
        return redirect(url_for("projects"))

    @app.route("/projects/<pid>/edit", methods=["POST"])
    def projects_edit(pid):
        projects = storage.load_projects()
        for p in projects:
            if p["id"] == pid:
                p["name"] = request.form["name"].strip()
                p["rate"] = float(request.form.get("rate", p["rate"]))
                break
        storage.save_projects(projects)
        flash("Project updated.", "success")
        return redirect(url_for("projects"))

    @app.route("/projects/<pid>/deactivate", methods=["POST"])
    def projects_deactivate(pid):
        projects = storage.load_projects()
        for p in projects:
            if p["id"] == pid:
                p["active"] = False
                break
        storage.save_projects(projects)
        flash("Project deactivated.", "success")
        return redirect(url_for("projects"))
```

- [ ] **Step 4: Write projects.html**

Create `timesheet/templates/projects.html`:

```html
{% extends "base.html" %}
{% block title %}Projects{% endblock %}
{% block content %}
<h1>Projects</h1>

<div class="card">
  <h2>Add Project</h2>
  <form method="post" action="/projects/add" style="display:flex;gap:1rem;align-items:flex-end">
    <div class="form-group" style="flex:2;margin:0">
      <label>Name</label>
      <input name="name" required placeholder="Client name or project">
    </div>
    <div class="form-group" style="flex:1;margin:0">
      <label>Hourly Rate (CAD)</label>
      <input name="rate" type="number" step="0.01" min="0" placeholder="125.00">
    </div>
    <button class="btn btn-primary" type="submit">Add</button>
  </form>
</div>

{% if projects %}
<table>
  <thead><tr><th>Name</th><th>Rate (CAD/hr)</th><th>Status</th><th></th></tr></thead>
  <tbody>
  {% for p in projects %}
  <tr>
    <td>{{ p.name }}</td>
    <td>${{ "%.2f"|format(p.rate) }}</td>
    <td>{{ "Active" if p.active else "Inactive" }}</td>
    <td style="text-align:right">
      <button class="btn btn-sm btn-secondary" onclick="openEdit('{{ p.id }}','{{ p.name }}','{{ p.rate }}')">Edit</button>
      {% if p.active %}
      <form class="inline" method="post" action="/projects/{{ p.id }}/deactivate">
        <button class="btn btn-sm btn-danger" type="submit" onclick="return confirm('Deactivate?')">Deactivate</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-muted">No projects yet. Add one above.</p>
{% endif %}

<!-- Edit modal -->
<div class="modal-overlay" id="edit-modal">
  <div class="modal">
    <h2>Edit Project</h2>
    <form method="post" id="edit-form">
      <div class="form-group"><label>Name</label><input name="name" id="edit-name"></div>
      <div class="form-group"><label>Rate (CAD/hr)</label><input name="rate" type="number" step="0.01" id="edit-rate"></div>
      <button class="btn btn-primary" type="submit">Save</button>
      <button class="btn btn-secondary" type="button" onclick="closeEdit()">Cancel</button>
    </form>
  </div>
</div>
<script>
function openEdit(id, name, rate) {
  document.getElementById('edit-form').action = '/projects/' + id + '/edit';
  document.getElementById('edit-name').value = name;
  document.getElementById('edit-rate').value = rate;
  document.getElementById('edit-modal').classList.add('open');
}
function closeEdit() { document.getElementById('edit-modal').classList.remove('open'); }
</script>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/projects.html
git commit -m "feat: projects page with add, edit, deactivate"
```

---

## Task 6: Dashboard (Quick Time Entry)

**Files:**
- Modify: `timesheet/app.py` (update dashboard route)
- Modify: `timesheet/templates/dashboard.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_dashboard_post_creates_entry -v
```

Expected: FAIL.

- [ ] **Step 3: Update dashboard route in app.py**

Replace the stub dashboard route:

```python
    @app.route("/", methods=["GET", "POST"])
    def dashboard():
        if request.method == "POST":
            project_id = request.form["project_id"]
            date = request.form["date"]
            hours = float(request.form.get("hours", 0))
            description = request.form["description"].strip()
            if not project_id or hours <= 0:
                flash("Project and hours are required.", "error")
                return redirect(url_for("dashboard"))
            entries = storage.load_time_entries()
            entries.append({
                "id": storage.new_id(),
                "project_id": project_id,
                "date": date,
                "hours": hours,
                "description": description,
                "invoiced": False,
            })
            storage.save_time_entries(entries)
            flash("Time entry added.", "success")
            return redirect(url_for("dashboard"))

        from datetime import date as dt_date
        today = dt_date.today().isoformat()
        projects = [p for p in storage.load_projects() if p["active"]]
        all_entries = storage.load_time_entries()
        today_entries = [e for e in all_entries if e["date"] == today]
        project_map = {p["id"]: p for p in storage.load_projects()}
        return render_template("dashboard.html", projects=projects,
                               today=today, today_entries=today_entries,
                               project_map=project_map)
```

- [ ] **Step 4: Write dashboard.html**

Replace `timesheet/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1>Dashboard</h1>

<div class="card">
  <h2>Log Time</h2>
  <form method="post" style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0">
      <label>Project</label>
      <select name="project_id" required>
        <option value="">— select —</option>
        {% for p in projects %}
        <option value="{{ p.id }}">{{ p.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0">
      <label>Date</label>
      <input name="date" type="date" value="{{ today }}" required>
    </div>
    <div class="form-group" style="margin:0">
      <label>Hours</label>
      <input name="hours" type="number" step="0.25" min="0.25" placeholder="2.5" required>
    </div>
    <button class="btn btn-primary" type="submit" style="align-self:flex-end">Add</button>
    <div class="form-group" style="margin:0;grid-column:1/-1">
      <label>Description</label>
      <input name="description" placeholder="What did you work on?">
    </div>
  </form>
</div>

<h2>Today's Entries</h2>
{% if today_entries %}
<table>
  <thead><tr><th>Project</th><th>Hours</th><th>Description</th><th></th></tr></thead>
  <tbody>
  {% for e in today_entries %}
  <tr>
    <td>{{ project_map[e.project_id].name if e.project_id in project_map else '—' }}</td>
    <td>{{ e.hours }}</td>
    <td>{{ e.description }}</td>
    <td style="text-align:right">
      <a class="btn btn-sm btn-secondary" href="/time/{{ e.id }}/edit">Edit</a>
      {% if not e.invoiced %}
      <form class="inline" method="post" action="/time/{{ e.id }}/delete">
        <button class="btn btn-sm btn-danger" type="submit" onclick="return confirm('Delete?')">Delete</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-muted">No entries logged today.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/dashboard.html
git commit -m "feat: dashboard with quick time entry form and today's entries"
```

---

## Task 7: Time Entries Page

**Files:**
- Modify: `timesheet/app.py`
- Create: `timesheet/templates/time.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_time_entries_page -v
```

Expected: FAIL.

- [ ] **Step 3: Add time entry routes to app.py**

```python
    @app.route("/time")
    def time_entries():
        entries = storage.load_time_entries()
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        pf = request.args.get("project_id", "")
        df = request.args.get("date_from", "")
        dt = request.args.get("date_to", "")
        if pf:
            entries = [e for e in entries if e["project_id"] == pf]
        if df:
            entries = [e for e in entries if e["date"] >= df]
        if dt:
            entries = [e for e in entries if e["date"] <= dt]
        entries = sorted(entries, key=lambda e: e["date"], reverse=True)
        return render_template("time.html", entries=entries, projects=projects,
                               project_map=project_map, pf=pf, df=df, dt=dt)

    @app.route("/time/add", methods=["POST"])
    def time_add():
        project_id = request.form["project_id"]
        hours = float(request.form.get("hours", 0))
        if not project_id or hours <= 0:
            flash("Project and hours required.", "error")
            return redirect(url_for("time_entries"))
        entries = storage.load_time_entries()
        entries.append({
            "id": storage.new_id(),
            "project_id": project_id,
            "date": request.form["date"],
            "hours": hours,
            "description": request.form.get("description", "").strip(),
            "invoiced": False,
        })
        storage.save_time_entries(entries)
        flash("Time entry added.", "success")
        return redirect(url_for("time_entries"))

    @app.route("/time/<eid>/edit", methods=["GET", "POST"])
    def time_edit(eid):
        entries = storage.load_time_entries()
        entry = next((e for e in entries if e["id"] == eid), None)
        if not entry:
            flash("Entry not found.", "error")
            return redirect(url_for("time_entries"))
        if entry["invoiced"]:
            flash("Cannot edit an invoiced entry.", "error")
            return redirect(url_for("time_entries"))
        if request.method == "POST":
            entry["project_id"] = request.form["project_id"]
            entry["date"] = request.form["date"]
            entry["hours"] = float(request.form.get("hours", entry["hours"]))
            entry["description"] = request.form.get("description", "").strip()
            storage.save_time_entries(entries)
            flash("Entry updated.", "success")
            return redirect(url_for("time_entries"))
        return render_template("time.html", edit_entry=entry,
                               entries=storage.load_time_entries(),
                               projects=storage.load_projects(),
                               project_map={p["id"]: p for p in storage.load_projects()},
                               pf="", df="", dt="")

    @app.route("/time/<eid>/delete", methods=["POST"])
    def time_delete(eid):
        entries = storage.load_time_entries()
        entry = next((e for e in entries if e["id"] == eid), None)
        if entry and entry["invoiced"]:
            flash("Cannot delete an invoiced entry.", "error")
            return redirect(url_for("time_entries"))
        entries = [e for e in entries if e["id"] != eid]
        storage.save_time_entries(entries)
        flash("Entry deleted.", "success")
        return redirect(url_for("time_entries"))
```

- [ ] **Step 4: Write time.html**

Create `timesheet/templates/time.html`:

```html
{% extends "base.html" %}
{% block title %}Time Entries{% endblock %}
{% block content %}
<h1>Time Entries</h1>

<div class="card">
  <h2>Add Entry</h2>
  <form method="post" action="/time/add" style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0">
      <label>Project</label>
      <select name="project_id" required>
        <option value="">— select —</option>
        {% for p in projects %}<option value="{{ p.id }}">{{ p.name }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0"><label>Date</label><input name="date" type="date" required></div>
    <div class="form-group" style="margin:0"><label>Hours</label><input name="hours" type="number" step="0.25" min="0.25" required></div>
    <button class="btn btn-primary" type="submit" style="align-self:flex-end">Add</button>
    <div class="form-group" style="margin:0;grid-column:1/-1">
      <label>Description</label><input name="description" placeholder="Description">
    </div>
  </form>
</div>

<div style="display:flex;gap:1rem;margin-bottom:1rem;align-items:flex-end">
  <form method="get" style="display:flex;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0"><label>Project</label>
      <select name="project_id"><option value="">All</option>
        {% for p in projects %}<option value="{{ p.id }}" {{ 'selected' if p.id == pf }}>{{ p.name }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0"><label>From</label><input name="date_from" type="date" value="{{ df }}"></div>
    <div class="form-group" style="margin:0"><label>To</label><input name="date_to" type="date" value="{{ dt }}"></div>
    <button class="btn btn-secondary" type="submit">Filter</button>
  </form>
</div>

{% if entries %}
<table>
  <thead><tr><th>Date</th><th>Project</th><th>Hours</th><th>Description</th><th></th></tr></thead>
  <tbody>
  {% for e in entries %}
  <tr>
    <td>{{ e.date }}</td>
    <td>{{ project_map[e.project_id].name if e.project_id in project_map else '—' }}</td>
    <td>{{ e.hours }}</td>
    <td>{{ e.description }}{% if e.invoiced %} <span class="locked">🔒 invoiced</span>{% endif %}</td>
    <td style="text-align:right">
      {% if not e.invoiced %}
      <a class="btn btn-sm btn-secondary" href="/time/{{ e.id }}/edit">Edit</a>
      <form class="inline" method="post" action="/time/{{ e.id }}/delete">
        <button class="btn btn-sm btn-danger" onclick="return confirm('Delete?')">Delete</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-muted">No time entries found.</p>
{% endif %}

{% if edit_entry %}
<div class="modal-overlay open" id="edit-modal">
  <div class="modal">
    <h2>Edit Entry</h2>
    <form method="post" action="/time/{{ edit_entry.id }}/edit">
      <div class="form-group"><label>Project</label>
        <select name="project_id">
          {% for p in projects %}<option value="{{ p.id }}" {{ 'selected' if p.id == edit_entry.project_id }}>{{ p.name }}</option>{% endfor %}
        </select>
      </div>
      <div class="form-group"><label>Date</label><input name="date" type="date" value="{{ edit_entry.date }}"></div>
      <div class="form-group"><label>Hours</label><input name="hours" type="number" step="0.25" value="{{ edit_entry.hours }}"></div>
      <div class="form-group"><label>Description</label><input name="description" value="{{ edit_entry.description }}"></div>
      <button class="btn btn-primary" type="submit">Save</button>
      <a class="btn btn-secondary" href="/time">Cancel</a>
    </form>
  </div>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/time.html
git commit -m "feat: time entries page with add, edit, delete, filter"
```

---

## Task 8: Expenses Page (with PDF Receipt Upload)

**Files:**
- Modify: `timesheet/app.py`
- Create: `timesheet/templates/expenses.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_expenses_add_no_receipt -v
```

Expected: FAIL.

- [ ] **Step 3: Add expense routes to app.py**

Add import at top of `app.py`:

```python
from werkzeug.utils import secure_filename
```

Add routes inside `create_app()`:

```python
    EXPENSE_PDF_DIR = storage.DATA_DIR / "expense_pdfs"

    @app.route("/expenses")
    def expenses():
        items = storage.load_expenses()
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        pf = request.args.get("project_id", "")
        df = request.args.get("date_from", "")
        dt = request.args.get("date_to", "")
        if pf:
            items = [x for x in items if x["project_id"] == pf]
        if df:
            items = [x for x in items if x["date"] >= df]
        if dt:
            items = [x for x in items if x["date"] <= dt]
        items = sorted(items, key=lambda x: x["date"], reverse=True)
        return render_template("expenses.html", expenses=items, projects=projects,
                               project_map=project_map, pf=pf, df=df, dt=dt)

    @app.route("/expenses/add", methods=["POST"])
    def expenses_add():
        project_id = request.form["project_id"]
        amount = float(request.form.get("amount", 0))
        if not project_id or amount <= 0:
            flash("Project and amount required.", "error")
            return redirect(url_for("expenses"))

        pdf_filename = None
        receipt = request.files.get("receipt")
        if receipt and receipt.filename and receipt.filename.lower().endswith(".pdf"):
            EXPENSE_PDF_DIR.mkdir(parents=True, exist_ok=True)
            pdf_filename = storage.new_id() + ".pdf"
            receipt.save(str(EXPENSE_PDF_DIR / pdf_filename))

        items = storage.load_expenses()
        items.append({
            "id": storage.new_id(),
            "project_id": project_id,
            "date": request.form["date"],
            "amount": amount,
            "description": request.form.get("description", "").strip(),
            "pdf_filename": pdf_filename,
            "invoiced": False,
        })
        storage.save_expenses(items)
        flash("Expense added.", "success")
        return redirect(url_for("expenses"))

    @app.route("/expenses/<xid>/edit", methods=["GET", "POST"])
    def expenses_edit(xid):
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if not item or item["invoiced"]:
            flash("Cannot edit this expense.", "error")
            return redirect(url_for("expenses"))
        if request.method == "POST":
            item["project_id"] = request.form["project_id"]
            item["date"] = request.form["date"]
            item["amount"] = float(request.form.get("amount", item["amount"]))
            item["description"] = request.form.get("description", "").strip()
            # Allow replacing the receipt PDF
            receipt = request.files.get("receipt")
            if receipt and receipt.filename and receipt.filename.lower().endswith(".pdf"):
                EXPENSE_PDF_DIR.mkdir(parents=True, exist_ok=True)
                pdf_filename = storage.new_id() + ".pdf"
                receipt.save(str(EXPENSE_PDF_DIR / pdf_filename))
                item["pdf_filename"] = pdf_filename
            storage.save_expenses(items)
            flash("Expense updated.", "success")
            return redirect(url_for("expenses"))
        return render_template("expenses.html", edit_expense=item,
                               expenses=storage.load_expenses(),
                               projects=storage.load_projects(),
                               project_map={p["id"]: p for p in storage.load_projects()},
                               pf="", df="", dt="")

    @app.route("/expenses/<xid>/delete", methods=["POST"])
    def expenses_delete(xid):
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if item and item["invoiced"]:
            flash("Cannot delete an invoiced expense.", "error")
            return redirect(url_for("expenses"))
        if item and item.get("pdf_filename"):
            pdf_path = EXPENSE_PDF_DIR / item["pdf_filename"]
            if pdf_path.exists():
                pdf_path.unlink()
        items = [x for x in items if x["id"] != xid]
        storage.save_expenses(items)
        flash("Expense deleted.", "success")
        return redirect(url_for("expenses"))

    @app.route("/expenses/<xid>/receipt")
    def expenses_receipt(xid):
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if not item or not item.get("pdf_filename"):
            flash("No receipt found.", "error")
            return redirect(url_for("expenses"))
        pdf_path = EXPENSE_PDF_DIR / item["pdf_filename"]
        if not pdf_path.exists():
            flash("Receipt file missing.", "error")
            return redirect(url_for("expenses"))
        return send_file(str(pdf_path), download_name=f"receipt-{item['date']}.pdf",
                         as_attachment=True, mimetype="application/pdf")
```

- [ ] **Step 4: Write expenses.html**

Create `timesheet/templates/expenses.html`:

```html
{% extends "base.html" %}
{% block title %}Expenses{% endblock %}
{% block content %}
<h1>Expenses</h1>

<div class="card">
  <h2>Add Expense</h2>
  <form method="post" action="/expenses/add" enctype="multipart/form-data"
        style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0"><label>Project</label>
      <select name="project_id" required>
        <option value="">— select —</option>
        {% for p in projects %}<option value="{{ p.id }}">{{ p.name }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0"><label>Date</label><input name="date" type="date" required></div>
    <div class="form-group" style="margin:0"><label>Amount (CAD)</label><input name="amount" type="number" step="0.01" min="0.01" required></div>
    <button class="btn btn-primary" type="submit" style="align-self:flex-end">Add</button>
    <div class="form-group" style="margin:0;grid-column:1/3">
      <label>Description</label><input name="description" placeholder="What was this for?">
    </div>
    <div class="form-group" style="margin:0;grid-column:3/-1">
      <label>Receipt PDF (optional)</label>
      <input name="receipt" type="file" accept=".pdf" style="padding:4px">
    </div>
  </form>
</div>

<div style="display:flex;gap:1rem;margin-bottom:1rem;align-items:flex-end">
  <form method="get" style="display:flex;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0"><label>Project</label>
      <select name="project_id"><option value="">All</option>
        {% for p in projects %}<option value="{{ p.id }}" {{ 'selected' if p.id == pf }}>{{ p.name }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0"><label>From</label><input name="date_from" type="date" value="{{ df }}"></div>
    <div class="form-group" style="margin:0"><label>To</label><input name="date_to" type="date" value="{{ dt }}"></div>
    <button class="btn btn-secondary" type="submit">Filter</button>
  </form>
</div>

{% if expenses %}
<table>
  <thead><tr><th>Date</th><th>Project</th><th>Amount</th><th>Description</th><th></th></tr></thead>
  <tbody>
  {% for x in expenses %}
  <tr>
    <td>{{ x.date }}</td>
    <td>{{ project_map[x.project_id].name if x.project_id in project_map else '—' }}</td>
    <td>${{ "%.2f"|format(x.amount) }}</td>
    <td>
      {{ x.description }}
      {% if x.pdf_filename %}<a class="btn btn-sm btn-secondary" href="/expenses/{{ x.id }}/receipt" style="margin-left:6px">📎 Receipt</a>{% endif %}
      {% if x.invoiced %} <span class="locked">🔒 invoiced</span>{% endif %}
    </td>
    <td style="text-align:right">
      {% if not x.invoiced %}
      <a class="btn btn-sm btn-secondary" href="/expenses/{{ x.id }}/edit">Edit</a>
      <form class="inline" method="post" action="/expenses/{{ x.id }}/delete">
        <button class="btn btn-sm btn-danger" onclick="return confirm('Delete?')">Delete</button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-muted">No expenses found.</p>
{% endif %}

{% if edit_expense %}
<div class="modal-overlay open">
  <div class="modal">
    <h2>Edit Expense</h2>
    <form method="post" action="/expenses/{{ edit_expense.id }}/edit" enctype="multipart/form-data">
      <div class="form-group"><label>Project</label>
        <select name="project_id">
          {% for p in projects %}<option value="{{ p.id }}" {{ 'selected' if p.id == edit_expense.project_id }}>{{ p.name }}</option>{% endfor %}
        </select>
      </div>
      <div class="form-group"><label>Date</label><input name="date" type="date" value="{{ edit_expense.date }}"></div>
      <div class="form-group"><label>Amount</label><input name="amount" type="number" step="0.01" value="{{ edit_expense.amount }}"></div>
      <div class="form-group"><label>Description</label><input name="description" value="{{ edit_expense.description }}"></div>
      <div class="form-group">
        <label>Replace Receipt PDF{% if edit_expense.pdf_filename %} (currently attached){% endif %}</label>
        <input name="receipt" type="file" accept=".pdf" style="padding:4px">
      </div>
      <button class="btn btn-primary" type="submit">Save</button>
      <a class="btn btn-secondary" href="/expenses">Cancel</a>
    </form>
  </div>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/expenses.html
git commit -m "feat: expenses page with optional PDF receipt upload and download"
```

---

## Task 9: Invoice Calculation Tests + PDF Module

**Files:**
- Create: `tests/test_invoice_calc.py`
- Create: `timesheet/pdf.py`

- [ ] **Step 1: Write invoice calculation tests**

Create `tests/test_invoice_calc.py`:

```python
def test_invoice_subtotal_time_only():
    entries = [{"hours": 2.0, "rate": 100.0, "amount": 200.0}]
    expenses = []
    subtotal = sum(e["amount"] for e in entries) + sum(x["amount"] for x in expenses)
    assert subtotal == 200.0


def test_invoice_subtotal_with_expenses():
    subtotal = (2.5 * 125.0) + 49.99
    assert round(subtotal, 2) == 362.49


def test_gst_calculation():
    subtotal = 362.49
    gst_rate = 0.05
    gst = round(subtotal * gst_rate, 2)
    assert gst == 18.12


def test_invoice_number_increments():
    existing = [{"invoice_number": "INV-001"}, {"invoice_number": "INV-003"}]
    nums = [int(i["invoice_number"].split("-")[1]) for i in existing]
    next_num = max(nums) + 1 if nums else 1
    assert f"INV-{next_num:03d}" == "INV-004"


def test_invoice_number_starts_at_001_when_empty():
    existing = []
    nums = [int(i["invoice_number"].split("-")[1]) for i in existing]
    next_num = max(nums) + 1 if nums else 1
    assert f"INV-{next_num:03d}" == "INV-001"
```

- [ ] **Step 2: Run to verify pass (pure logic, no dependencies)**

```bash
python -m pytest ../tests/test_invoice_calc.py -v
```

Expected: All 5 PASS.

- [ ] **Step 3: Write pdf.py**

Create `timesheet/pdf.py`:

```python
from io import BytesIO
from weasyprint import HTML
from flask import render_template
from pypdf import PdfWriter, PdfReader


def generate_invoice_pdf(app, invoice, settings, expense_pdf_dir=None):
    """Render invoice_pdf.html with WeasyPrint, then append any expense receipt
    PDFs as additional pages. Returns combined PDF bytes."""
    with app.app_context():
        html_content = render_template("invoice_pdf.html", invoice=invoice, settings=settings)

    invoice_bytes = HTML(string=html_content).write_pdf()

    # Collect receipt PDFs for expenses that have one
    receipt_paths = []
    if expense_pdf_dir is not None:
        for item in invoice.get("line_items", []):
            if item.get("type") == "expense" and item.get("pdf_filename"):
                path = expense_pdf_dir / item["pdf_filename"]
                if path.exists():
                    receipt_paths.append(path)

    if not receipt_paths:
        return invoice_bytes

    # Merge invoice + receipts into one PDF
    writer = PdfWriter()
    for reader in [PdfReader(BytesIO(invoice_bytes))] + [PdfReader(str(p)) for p in receipt_paths]:
        for page in reader.pages:
            writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
```

- [ ] **Step 4: Write invoice_pdf.html**

Create `timesheet/templates/invoice_pdf.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 12px; color: #222; margin: 40px; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  .meta { color: #666; margin-bottom: 24px; }
  .parties { display: flex; justify-content: space-between; margin-bottom: 32px; }
  .party h3 { font-size: 11px; text-transform: uppercase; color: #999; margin-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  th { background: #f5f5f5; text-align: left; padding: 8px; border-bottom: 2px solid #ddd; font-size: 11px; }
  td { padding: 8px; border-bottom: 1px solid #eee; }
  .amount { text-align: right; }
  .totals { width: 300px; margin-left: auto; }
  .totals tr td { padding: 5px 8px; }
  .totals .total-row td { font-weight: bold; font-size: 14px; border-top: 2px solid #222; }
  .gst-note { color: #888; font-size: 10px; margin-top: 32px; }
</style>
</head>
<body>

<h1>INVOICE</h1>
<div class="meta">{{ invoice.invoice_number }} &nbsp;|&nbsp; {{ invoice.issued_date }}</div>

<div class="parties">
  <div class="party">
    <h3>From</h3>
    <strong>{{ settings.business_name }}</strong><br>
    {% if settings.gst_number %}GST# {{ settings.gst_number }}{% endif %}
  </div>
  <div class="party">
    <h3>Bill To</h3>
    <strong>{{ invoice.client_name }}</strong>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Date</th><th>Description</th><th>Qty / Hrs</th><th>Rate</th><th class="amount">Amount</th>
    </tr>
  </thead>
  <tbody>
  {% for item in invoice.line_items %}
  <tr>
    <td>{{ item.date }}</td>
    <td>{{ item.description }}</td>
    {% if item.type == 'time' %}
    <td>{{ item.hours }} hrs</td>
    <td>${{ "%.2f"|format(item.rate) }}/hr</td>
    {% else %}
    <td>—</td><td>Expense</td>
    {% endif %}
    <td class="amount">${{ "%.2f"|format(item.amount) }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>

<table class="totals">
  <tr><td>Subtotal</td><td class="amount">${{ "%.2f"|format(invoice.subtotal) }}</td></tr>
  <tr><td>GST ({{ (settings.gst_rate * 100)|int }}%)</td><td class="amount">${{ "%.2f"|format(invoice.gst) }}</td></tr>
  <tr class="total-row"><td>Total (CAD)</td><td class="amount">${{ "%.2f"|format(invoice.total) }}</td></tr>
</table>

<p class="gst-note">GST Registration: {{ settings.gst_number }}</p>

</body>
</html>
```

- [ ] **Step 5: Commit**

```bash
git add timesheet/pdf.py timesheet/templates/invoice_pdf.html tests/test_invoice_calc.py
git commit -m "feat: invoice PDF module and invoice_pdf.html template"
```

---

## Task 10: Invoices Page

**Files:**
- Modify: `timesheet/app.py`
- Create: `timesheet/templates/invoices.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_invoices_page -v
```

Expected: FAIL.

- [ ] **Step 3: Add invoice routes to app.py**

Add import at top of app.py:

```python
import timesheet.pdf as pdf
from io import BytesIO
```

Add routes inside `create_app()`:

```python
    @app.route("/invoices")
    def invoices():
        project_id = request.args.get("project_id", "")
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        all_entries = storage.load_time_entries()
        all_expenses = storage.load_expenses()
        all_invoices = storage.load_invoices()

        preview = None
        if project_id:
            p = project_map.get(project_id)
            uninvoiced_time = [e for e in all_entries if e["project_id"] == project_id and not e["invoiced"]]
            uninvoiced_exp = [x for x in all_expenses if x["project_id"] == project_id and not x["invoiced"]]
            time_subtotal = sum(e["hours"] * (p["rate"] if p else 0) for e in uninvoiced_time)
            exp_subtotal = sum(x["amount"] for x in uninvoiced_exp)
            subtotal = round(time_subtotal + exp_subtotal, 2)
            gst_rate = storage.load_settings().get("gst_rate", 0.05)
            gst = round(subtotal * gst_rate, 2)
            preview = {
                "project": p,
                "time_entries": uninvoiced_time,
                "expenses": uninvoiced_exp,
                "subtotal": subtotal,
                "gst": gst,
                "total": round(subtotal + gst, 2),
            }

        return render_template("invoices.html", projects=projects, project_map=project_map,
                               invoices=all_invoices, preview=preview, selected_project=project_id)

    @app.route("/invoices/generate", methods=["POST"])
    def invoices_generate():
        project_id = request.form["project_id"]
        client_name = request.form.get("client_name", "").strip()
        settings = storage.load_settings()
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        p = project_map.get(project_id)
        if not p or not client_name:
            flash("Project and client name are required.", "error")
            return redirect(url_for("invoices"))

        all_entries = storage.load_time_entries()
        all_expenses = storage.load_expenses()
        uninvoiced_time = [e for e in all_entries if e["project_id"] == project_id and not e["invoiced"]]
        uninvoiced_exp = [x for x in all_expenses if x["project_id"] == project_id and not x["invoiced"]]

        if not uninvoiced_time and not uninvoiced_exp:
            flash("No uninvoiced entries for this project.", "error")
            return redirect(url_for("invoices"))

        line_items = []
        for e in uninvoiced_time:
            amount = round(e["hours"] * p["rate"], 2)
            line_items.append({"type": "time", "date": e["date"], "description": e["description"],
                                "hours": e["hours"], "rate": p["rate"], "amount": amount})
        for x in uninvoiced_exp:
            line_items.append({"type": "expense", "date": x["date"],
                                "description": x["description"], "amount": x["amount"],
                                "pdf_filename": x.get("pdf_filename")})

        subtotal = round(sum(li["amount"] for li in line_items), 2)
        gst_rate = settings.get("gst_rate", 0.05)
        gst = round(subtotal * gst_rate, 2)
        total = round(subtotal + gst, 2)

        existing = storage.load_invoices()
        nums = [int(i["invoice_number"].split("-")[1]) for i in existing] if existing else []
        next_num = max(nums) + 1 if nums else 1
        invoice_number = f"INV-{next_num:03d}"

        invoice = {
            "id": storage.new_id(),
            "invoice_number": invoice_number,
            "project_id": project_id,
            "client_name": client_name,
            "issued_date": __import__("datetime").date.today().isoformat(),
            "subtotal": subtotal,
            "gst": gst,
            "total": total,
            "sent": False,
            "line_items": line_items,
        }

        try:
            pdf.generate_invoice_pdf(app, invoice, settings, expense_pdf_dir=EXPENSE_PDF_DIR)
        except Exception as e:
            flash(f"PDF generation failed: {e}", "error")
            return redirect(url_for("invoices"))

        existing.append(invoice)
        storage.save_invoices(existing)

        # Mark entries as invoiced
        for e in all_entries:
            if any(li["type"] == "time" and li["date"] == e["date"] and li["description"] == e["description"]
                   and e["project_id"] == project_id for li in line_items):
                e["invoiced"] = True
        storage.save_time_entries(all_entries)

        for x in all_expenses:
            if any(li["type"] == "expense" and li["date"] == x["date"] and li["description"] == x["description"]
                   and x["project_id"] == project_id for li in line_items):
                x["invoiced"] = True
        storage.save_expenses(all_expenses)

        flash(f"Invoice {invoice_number} generated.", "success")
        return redirect(url_for("invoices"))

    @app.route("/invoices/<inv_id>/pdf")
    def invoices_pdf(inv_id):
        invoices = storage.load_invoices()
        invoice = next((i for i in invoices if i["id"] == inv_id), None)
        if not invoice:
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices"))
        settings = storage.load_settings()
        try:
            pdf_bytes = pdf.generate_invoice_pdf(app, invoice, settings, expense_pdf_dir=EXPENSE_PDF_DIR)
        except Exception as e:
            flash(f"PDF error: {e}", "error")
            return redirect(url_for("invoices"))
        return send_file(BytesIO(pdf_bytes), download_name=f"{invoice['invoice_number']}.pdf",
                         as_attachment=True, mimetype="application/pdf")

    @app.route("/invoices/<inv_id>/send", methods=["POST"])
    def invoices_send(inv_id):
        invoices = storage.load_invoices()
        invoice = next((i for i in invoices if i["id"] == inv_id), None)
        if not invoice:
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices"))
        recipient = request.form.get("recipient", "").strip()
        if not recipient:
            flash("Recipient email required.", "error")
            return redirect(url_for("invoices"))
        settings = storage.load_settings()
        try:
            pdf_bytes = pdf.generate_invoice_pdf(app, invoice, settings, expense_pdf_dir=EXPENSE_PDF_DIR)
        except Exception as e:
            flash(f"PDF error: {e}", "error")
            return redirect(url_for("invoices"))
        from timesheet.mailer import send_invoice_email
        subject = request.form.get("subject", f"{invoice['invoice_number']} from {settings.get('business_name','')}")
        body = request.form.get("body", "Please find your invoice attached.")
        try:
            send_invoice_email(settings, recipient, subject, body,
                               pdf_bytes, invoice["invoice_number"])
            for i in invoices:
                if i["id"] == inv_id:
                    i["sent"] = True
            storage.save_invoices(invoices)
            flash(f"Invoice sent to {recipient}.", "success")
        except Exception as e:
            flash(f"Failed to send email: {e}", "error")
        return redirect(url_for("invoices"))
```

- [ ] **Step 4: Write invoices.html**

Create `timesheet/templates/invoices.html`:

```html
{% extends "base.html" %}
{% block title %}Invoices{% endblock %}
{% block content %}
<h1>Invoices</h1>

<div class="card">
  <h2>Generate Invoice</h2>
  <form method="get" style="display:flex;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0;flex:2">
      <label>Select Project</label>
      <select name="project_id" onchange="this.form.submit()">
        <option value="">— select project —</option>
        {% for p in projects %}<option value="{{ p.id }}" {{ 'selected' if p.id == selected_project }}>{{ p.name }}</option>{% endfor %}
      </select>
    </div>
  </form>

  {% if preview %}
  <div style="margin-top:1.5rem">
    <h3>Uninvoiced Items — {{ preview.project.name }}</h3>
    {% if preview.time_entries %}
    <table style="margin-bottom:1rem">
      <thead><tr><th>Date</th><th>Description</th><th>Hours</th><th>Rate</th><th class="text-right">Amount</th></tr></thead>
      <tbody>
      {% for e in preview.time_entries %}
      <tr>
        <td>{{ e.date }}</td><td>{{ e.description }}</td>
        <td>{{ e.hours }}</td><td>${{ "%.2f"|format(preview.project.rate) }}/hr</td>
        <td class="text-right">${{ "%.2f"|format(e.hours * preview.project.rate) }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% endif %}
    {% if preview.expenses %}
    <table style="margin-bottom:1rem">
      <thead><tr><th>Date</th><th>Description</th><th colspan="2"></th><th class="text-right">Amount</th></tr></thead>
      <tbody>
      {% for x in preview.expenses %}
      <tr><td>{{ x.date }}</td><td>{{ x.description }}</td><td colspan="2"></td><td class="text-right">${{ "%.2f"|format(x.amount) }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    {% endif %}
    {% if not preview.time_entries and not preview.expenses %}
    <p class="text-muted">No uninvoiced entries for this project.</p>
    {% else %}
    <table class="totals" style="width:280px;margin-left:auto">
      <tr><td>Subtotal</td><td class="text-right">${{ "%.2f"|format(preview.subtotal) }}</td></tr>
      <tr><td>GST</td><td class="text-right">${{ "%.2f"|format(preview.gst) }}</td></tr>
      <tr style="font-weight:700"><td>Total (CAD)</td><td class="text-right">${{ "%.2f"|format(preview.total) }}</td></tr>
    </table>
    <form method="post" action="/invoices/generate" style="margin-top:1rem;display:flex;gap:1rem;align-items:flex-end">
      <input type="hidden" name="project_id" value="{{ selected_project }}">
      <div class="form-group" style="margin:0;flex:2">
        <label>Client Name (for invoice)</label>
        <input name="client_name" required placeholder="Client ABC Corp">
      </div>
      <button class="btn btn-primary" type="submit">Generate Invoice</button>
    </form>
    {% endif %}
  </div>
  {% endif %}
</div>

<h2>Past Invoices</h2>
{% if invoices %}
<table>
  <thead><tr><th>#</th><th>Client</th><th>Date</th><th>Total</th><th>Sent</th><th></th></tr></thead>
  <tbody>
  {% for inv in invoices|sort(attribute='invoice_number', reverse=True) %}
  <tr>
    <td>{{ inv.invoice_number }}</td>
    <td>{{ inv.client_name }}</td>
    <td>{{ inv.issued_date }}</td>
    <td>${{ "%.2f"|format(inv.total) }}</td>
    <td>{{ "✓" if inv.sent else "—" }}</td>
    <td style="text-align:right">
      <a class="btn btn-sm btn-secondary" href="/invoices/{{ inv.id }}/pdf">Download PDF</a>
      <button class="btn btn-sm btn-primary" onclick="openEmail('{{ inv.id }}','{{ inv.invoice_number }}','{{ inv.client_name }}')">Email</button>
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-muted">No invoices generated yet.</p>
{% endif %}

<!-- Email modal -->
<div class="modal-overlay" id="email-modal">
  <div class="modal">
    <h2>Email Invoice</h2>
    <form method="post" id="email-form">
      <div class="form-group"><label>To</label><input name="recipient" type="email" required></div>
      <div class="form-group"><label>Subject</label><input name="subject" id="email-subject"></div>
      <div class="form-group"><label>Message</label>
        <textarea name="body" rows="4">Please find your invoice attached. Thank you for your business.</textarea>
      </div>
      <button class="btn btn-primary" type="submit">Send</button>
      <button class="btn btn-secondary" type="button" onclick="closeEmail()">Cancel</button>
    </form>
  </div>
</div>
<script>
function openEmail(id, num, client) {
  document.getElementById('email-form').action = '/invoices/' + id + '/send';
  document.getElementById('email-subject').value = num + ' from {{ settings.business_name }}';
  document.getElementById('email-modal').classList.add('open');
}
function closeEmail() { document.getElementById('email-modal').classList.remove('open'); }
</script>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/invoices.html
git commit -m "feat: invoices page with preview, generate, download PDF"
```

---

## Task 11: Email (Mailer Module)

**Files:**
- Create: `timesheet/mailer.py`

- [ ] **Step 1: Write mailer.py**

Create `timesheet/mailer.py`:

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def send_invoice_email(settings, recipient, subject, body, pdf_bytes, invoice_number):
    """Send invoice PDF via Gmail SMTP. Raises on failure."""
    smtp_host = settings.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_user = settings.get("smtp_user", "")
    smtp_password = settings.get("smtp_password", "")

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP credentials not configured. Go to Settings to add them.")

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{invoice_number}.pdf"')
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())
```

- [ ] **Step 2: Verify import works**

```bash
cd timesheet && python -c "from timesheet.mailer import send_invoice_email; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add timesheet/mailer.py
git commit -m "feat: gmail SMTP mailer module for invoice emails"
```

---

## Task 12: Monthly Report

**Files:**
- Modify: `timesheet/app.py`
- Create: `timesheet/templates/report_monthly.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_routes.py`:

```python
def test_monthly_report(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Alpha", "rate": 100.0, "currency": "CAD", "active": True}])
    storage.save_time_entries([{"id": "e1", "project_id": "p1", "date": "2026-05-16",
                                "hours": 3.0, "description": "Work", "invoiced": False}])
    r = client.get("/reports/monthly?year=2026&month=5")
    assert r.status_code == 200
    assert b"Alpha" in r.data
    assert b"300.00" in r.data  # 3hrs * $100
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_monthly_report -v
```

Expected: FAIL.

- [ ] **Step 3: Add monthly report route to app.py**

```python
    @app.route("/reports/monthly")
    def report_monthly():
        from datetime import date as dt_date
        today = dt_date.today()
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        month_prefix = f"{year}-{month:02d}"

        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        entries = [e for e in storage.load_time_entries() if e["date"].startswith(month_prefix)]
        expenses = [x for x in storage.load_expenses() if x["date"].startswith(month_prefix)]

        rows = {}
        for e in entries:
            pid = e["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0, "billable": 0, "expenses": 0}
            rows[pid]["hours"] += e["hours"]
            rows[pid]["billable"] += round(e["hours"] * p.get("rate", 0), 2)
        for x in expenses:
            pid = x["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0, "billable": 0, "expenses": 0}
            rows[pid]["expenses"] += x["amount"]

        for r in rows.values():
            r["total"] = round(r["billable"] + r["expenses"], 2)

        grand = {
            "hours": sum(r["hours"] for r in rows.values()),
            "billable": round(sum(r["billable"] for r in rows.values()), 2),
            "expenses": round(sum(r["expenses"] for r in rows.values()), 2),
            "total": round(sum(r["total"] for r in rows.values()), 2),
        }

        months = [(y, m) for y in range(today.year - 1, today.year + 1)
                  for m in range(1, 13)]

        return render_template("report_monthly.html", rows=rows, grand=grand,
                               year=year, month=month, months=months)
```

- [ ] **Step 4: Write report_monthly.html**

Create `timesheet/templates/report_monthly.html`:

```html
{% extends "base.html" %}
{% block title %}Monthly Report{% endblock %}
{% block content %}
<h1>Monthly Totals</h1>

<div style="display:flex;gap:1rem;margin-bottom:1.5rem;align-items:flex-end">
  <form method="get" style="display:flex;gap:1rem;align-items:flex-end">
    <div class="form-group" style="margin:0">
      <label>Year</label>
      <input name="year" type="number" value="{{ year }}" style="width:90px">
    </div>
    <div class="form-group" style="margin:0">
      <label>Month</label>
      <select name="month">
        {% for m in range(1,13) %}
        <option value="{{ m }}" {{ 'selected' if m == month }}>
          {{ ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1] }}
        </option>
        {% endfor %}
      </select>
    </div>
    <button class="btn btn-secondary" type="submit">View</button>
  </form>
  <a class="btn btn-secondary" href="/reports/uninvoiced">Uninvoiced Hours →</a>
</div>

{% if rows %}
<table>
  <thead>
    <tr><th>Project</th><th class="text-right">Hours</th><th class="text-right">Billable</th><th class="text-right">Expenses</th><th class="text-right">Total</th></tr>
  </thead>
  <tbody>
  {% for pid, r in rows.items() %}
  <tr>
    <td>{{ r.name }}</td>
    <td class="text-right">{{ "%.2f"|format(r.hours) }}</td>
    <td class="text-right">${{ "%.2f"|format(r.billable) }}</td>
    <td class="text-right">${{ "%.2f"|format(r.expenses) }}</td>
    <td class="text-right">${{ "%.2f"|format(r.total) }}</td>
  </tr>
  {% endfor %}
  </tbody>
  <tfoot>
  <tr class="grand-total">
    <td><strong>Total</strong></td>
    <td class="text-right"><strong>{{ "%.2f"|format(grand.hours) }}</strong></td>
    <td class="text-right"><strong>${{ "%.2f"|format(grand.billable) }}</strong></td>
    <td class="text-right"><strong>${{ "%.2f"|format(grand.expenses) }}</strong></td>
    <td class="text-right"><strong>${{ "%.2f"|format(grand.total) }}</strong></td>
  </tr>
  </tfoot>
</table>
{% else %}
<p class="text-muted">No entries for {{ ['January','February','March','April','May','June','July','August','September','October','November','December'][month-1] }} {{ year }}.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest ../tests/test_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/report_monthly.html
git commit -m "feat: monthly totals report grouped by project"
```

---

## Task 13: Uninvoiced Report

**Files:**
- Modify: `timesheet/app.py`
- Create: `timesheet/templates/report_uninvoiced.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_routes.py`:

```python
def test_uninvoiced_report(client):
    import timesheet.storage as storage
    storage.save_projects([{"id": "p1", "name": "Beta", "rate": 150.0, "currency": "CAD", "active": True}])
    storage.save_time_entries([
        {"id": "e1", "project_id": "p1", "date": "2026-05-10", "hours": 1.0, "description": "A", "invoiced": False},
        {"id": "e2", "project_id": "p1", "date": "2026-05-11", "hours": 1.0, "description": "B", "invoiced": True},
    ])
    r = client.get("/reports/uninvoiced")
    assert r.status_code == 200
    assert b"Beta" in r.data
    assert b"150.00" in r.data   # only 1 uninvoiced hour * $150
    assert b"300.00" not in r.data  # invoiced entry excluded
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest ../tests/test_routes.py::test_uninvoiced_report -v
```

Expected: FAIL.

- [ ] **Step 3: Add uninvoiced report route to app.py**

```python
    @app.route("/reports/uninvoiced")
    def report_uninvoiced():
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        entries = [e for e in storage.load_time_entries() if not e["invoiced"]]
        expenses = [x for x in storage.load_expenses() if not x["invoiced"]]

        rows = {}
        for e in entries:
            pid = e["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0,
                             "billable": 0, "expenses": 0, "entries": [], "expense_items": []}
            rows[pid]["hours"] += e["hours"]
            rows[pid]["billable"] += round(e["hours"] * p.get("rate", 0), 2)
            rows[pid]["entries"].append(e)
        for x in expenses:
            pid = x["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0,
                             "billable": 0, "expenses": 0, "entries": [], "expense_items": []}
            rows[pid]["expenses"] += x["amount"]
            rows[pid]["expense_items"].append(x)

        for r in rows.values():
            r["total"] = round(r["billable"] + r["expenses"], 2)

        grand = {
            "hours": sum(r["hours"] for r in rows.values()),
            "billable": round(sum(r["billable"] for r in rows.values()), 2),
            "expenses": round(sum(r["expenses"] for r in rows.values()), 2),
            "total": round(sum(r["total"] for r in rows.values()), 2),
        }

        return render_template("report_uninvoiced.html", rows=rows, grand=grand)
```

- [ ] **Step 4: Write report_uninvoiced.html**

Create `timesheet/templates/report_uninvoiced.html`:

```html
{% extends "base.html" %}
{% block title %}Uninvoiced Hours{% endblock %}
{% block content %}
<h1>Uninvoiced Hours</h1>
<p class="text-muted" style="margin-bottom:1.5rem">All time entries and expenses not yet included on an invoice.</p>

{% if rows %}
{% for pid, r in rows.items() %}
<div class="card" style="margin-bottom:1.5rem">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
    <h2>{{ r.name }}</h2>
    <a class="btn btn-primary btn-sm" href="/invoices?project_id={{ pid }}">Generate Invoice →</a>
  </div>

  {% if r.entries %}
  <table style="margin-bottom:1rem">
    <thead><tr><th>Date</th><th>Description</th><th class="text-right">Hours</th><th class="text-right">Billable</th></tr></thead>
    <tbody>
    {% for e in r.entries|sort(attribute='date') %}
    {% set proj = rows[e.project_id] if e.project_id in rows else {} %}
    <tr>
      <td>{{ e.date }}</td><td>{{ e.description }}</td>
      <td class="text-right">{{ e.hours }}</td>
      <td class="text-right">${{ "%.2f"|format(e.hours * (r.billable / r.hours if r.hours else 0)) }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if r.expense_items %}
  <table style="margin-bottom:1rem">
    <thead><tr><th>Date</th><th>Expense</th><th class="text-right" colspan="2">Amount</th></tr></thead>
    <tbody>
    {% for x in r.expense_items|sort(attribute='date') %}
    <tr><td>{{ x.date }}</td><td>{{ x.description }}</td><td colspan="1"></td><td class="text-right">${{ "%.2f"|format(x.amount) }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  <table style="width:280px;margin-left:auto">
    <tr><td>Hours</td><td class="text-right">{{ "%.2f"|format(r.hours) }}</td></tr>
    <tr><td>Billable</td><td class="text-right">${{ "%.2f"|format(r.billable) }}</td></tr>
    {% if r.expenses %}<tr><td>Expenses</td><td class="text-right">${{ "%.2f"|format(r.expenses) }}</td></tr>{% endif %}
    <tr style="font-weight:700;border-top:2px solid #ccc"><td>Total</td><td class="text-right">${{ "%.2f"|format(r.total) }}</td></tr>
  </table>
</div>
{% endfor %}

<div class="card" style="background:#f0f0f0">
  <table style="width:280px;margin-left:auto">
    <tr><td>Total Hours</td><td class="text-right">{{ "%.2f"|format(grand.hours) }}</td></tr>
    <tr><td>Total Billable</td><td class="text-right">${{ "%.2f"|format(grand.billable) }}</td></tr>
    {% if grand.expenses %}<tr><td>Total Expenses</td><td class="text-right">${{ "%.2f"|format(grand.expenses) }}</td></tr>{% endif %}
    <tr style="font-weight:700;border-top:2px solid #333"><td>Grand Total</td><td class="text-right">${{ "%.2f"|format(grand.total) }}</td></tr>
  </table>
</div>

{% else %}
<p class="text-muted">All entries are invoiced. Nothing outstanding.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest ../tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add timesheet/app.py timesheet/templates/report_uninvoiced.html
git commit -m "feat: uninvoiced hours report grouped by project with invoice link"
```

---

## Task 14: Final Wiring + Smoke Test

**Files:**
- Modify: `timesheet/app.py` (fix marking invoiced entries by ID)

- [ ] **Step 1: Fix invoiced entry marking in invoices_generate**

The current `invoices_generate` route matches entries by date+description which can have false matches. Fix to mark by ID directly (collect IDs before building line items):

Replace the invoiced-marking block in `invoices_generate` with:

```python
        invoiced_time_ids = {e["id"] for e in uninvoiced_time}
        invoiced_exp_ids = {x["id"] for x in uninvoiced_exp}

        for e in all_entries:
            if e["id"] in invoiced_time_ids:
                e["invoiced"] = True
        storage.save_time_entries(all_entries)

        for x in all_expenses:
            if x["id"] in invoiced_exp_ids:
                x["invoiced"] = True
        storage.save_expenses(all_expenses)
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest ../tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Run the app and manually verify the golden path**

```bash
cd timesheet && python app.py
```

Visit `http://localhost:5000` and verify:
1. Settings → enter business name, GST number
2. Projects → add a project with hourly rate
3. Dashboard → log a time entry
4. Expenses → add an expense for that project
5. Invoices → select project, preview, generate invoice, download PDF
6. Reports → Monthly shows this month's data; Uninvoiced shows the entry until invoiced

- [ ] **Step 4: Final commit**

```bash
git add timesheet/app.py
git commit -m "fix: mark invoiced entries by ID to prevent false matches"
```

---

## Quick Start (for reference)

```bash
cd timesheet
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

For Gmail SMTP, create an App Password at https://myaccount.google.com/apppasswords and enter it in Settings.
