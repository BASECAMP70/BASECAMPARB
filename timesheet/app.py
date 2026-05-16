import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from dotenv import load_dotenv
import timesheet.storage as storage
from io import BytesIO
from datetime import date as dt_date

import timesheet.pdf as pdf

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

        today = dt_date.today().isoformat()
        projects = [p for p in storage.load_projects() if p["active"]]
        all_entries = storage.load_time_entries()
        today_entries = [e for e in all_entries if e["date"] == today]
        project_map = {p["id"]: p for p in storage.load_projects()}
        return render_template("dashboard.html", projects=projects,
                               today=today, today_entries=today_entries,
                               project_map=project_map)

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            try:
                gst_rate = float(request.form.get("gst_rate", 0.05))
                smtp_port = int(request.form.get("smtp_port", 587))
            except ValueError:
                flash("GST rate and SMTP port must be numbers.", "error")
                return redirect(url_for("settings"))
            s = storage.load_settings()
            s.update({
                "business_name": request.form["business_name"].strip(),
                "gst_number": request.form["gst_number"].strip(),
                "gst_rate": gst_rate,
                "smtp_host": request.form["smtp_host"].strip(),
                "smtp_port": smtp_port,
                "smtp_user": request.form["smtp_user"].strip(),
                "smtp_password": request.form["smtp_password"].strip(),
                "invoice_brand_color": request.form.get("invoice_brand_color", s.get("invoice_brand_color", "#1D1E1C")).strip() or "#1D1E1C",
                "invoice_bg_color": request.form.get("invoice_bg_color", s.get("invoice_bg_color", "#FFFFFF")).strip() or "#FFFFFF",
                "app_nav_color": request.form.get("app_nav_color", s.get("app_nav_color", "#1a1a2e")).strip() or "#1a1a2e",
                "app_accent_color": request.form.get("app_accent_color", s.get("app_accent_color", "#4f8ef7")).strip() or "#4f8ef7",
            })

            # Logo upload
            logo = request.files.get("invoice_logo")
            if logo and logo.filename:
                ext = logo.filename.rsplit(".", 1)[-1].lower()
                if ext in ("jpg", "jpeg", "png", "gif"):
                    logo_data = logo.read()
                    if len(logo_data) <= 5 * 1024 * 1024:
                        logo_dir = storage.DATA_DIR / "invoice_logos"
                        logo_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"logo.{ext}"
                        (logo_dir / fname).write_bytes(logo_data)
                        s["invoice_logo_filename"] = fname
                    else:
                        flash("Logo must be under 5 MB.", "error")
                else:
                    flash("Logo must be JPG, PNG, or GIF.", "error")

            # Logo removal
            if request.form.get("remove_logo"):
                s["invoice_logo_filename"] = None

            storage.save_settings(s)
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        return render_template("settings.html", s=storage.load_settings())

    @app.route("/settings/logo")
    def settings_logo():
        s = storage.load_settings()
        fname = s.get("invoice_logo_filename")
        if not fname:
            return "", 404
        logo_path = storage.DATA_DIR / "invoice_logos" / fname
        if not logo_path.exists():
            return "", 404
        ext = fname.rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/png")
        return send_file(str(logo_path), mimetype=mime)

    # ── Clients ──────────────────────────────────────────────────────────────

    @app.route("/clients")
    def clients():
        return render_template("clients.html", clients=storage.load_clients())

    @app.route("/clients/add", methods=["POST"])
    def clients_add():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        if not name:
            flash("Client name is required.", "error")
            return redirect(url_for("clients"))
        all_clients = storage.load_clients()
        all_clients.append({"id": storage.new_id(), "name": name, "email": email, "address": address})
        storage.save_clients(all_clients)
        flash(f"Client '{name}' added.", "success")
        return redirect(url_for("clients"))

    @app.route("/clients/<cid>/edit", methods=["POST"])
    def clients_edit(cid):
        all_clients = storage.load_clients()
        for c in all_clients:
            if c["id"] == cid:
                c["name"] = request.form.get("name", "").strip() or c["name"]
                c["email"] = request.form.get("email", "").strip()
                c["address"] = request.form.get("address", "").strip()
                storage.save_clients(all_clients)
                flash("Client updated.", "success")
                return redirect(url_for("clients"))
        flash("Client not found.", "error")
        return redirect(url_for("clients"))

    # ── Projects ─────────────────────────────────────────────────────────────

    @app.route("/projects")
    def projects():
        client_map = {c["id"]: c for c in storage.load_clients()}
        return render_template("projects.html", projects=storage.load_projects(), client_map=client_map,
                               clients=storage.load_clients())

    @app.route("/projects/add", methods=["POST"])
    def projects_add():
        name = request.form.get("name", "").strip()
        try:
            rate = float(request.form.get("rate", 0))
        except ValueError:
            flash("Rate must be a number.", "error")
            return redirect(url_for("projects"))
        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("projects"))
        client_id = request.form.get("client_id", "").strip() or None
        projects = storage.load_projects()
        projects.append({"id": storage.new_id(), "name": name, "rate": rate,
                         "currency": "CAD", "active": True, "client_id": client_id})
        storage.save_projects(projects)
        flash(f"Project '{name}' added.", "success")
        return redirect(url_for("projects"))

    @app.route("/projects/<pid>/edit", methods=["POST"])
    def projects_edit(pid):
        projects = storage.load_projects()
        for p in projects:
            if p["id"] == pid:
                p["name"] = request.form.get("name", "").strip() or p["name"]
                try:
                    p["rate"] = float(request.form.get("rate", p["rate"]))
                except ValueError:
                    pass
                p["client_id"] = request.form.get("client_id", "").strip() or None
                storage.save_projects(projects)
                flash("Project updated.", "success")
                return redirect(url_for("projects"))
        flash("Project not found.", "error")
        return redirect(url_for("projects"))

    @app.route("/projects/<pid>/deactivate", methods=["POST"])
    def projects_deactivate(pid):
        projects = storage.load_projects()
        found = False
        for p in projects:
            if p["id"] == pid:
                p["active"] = False
                found = True
                break
        if not found:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))
        storage.save_projects(projects)
        flash("Project deactivated.", "success")
        return redirect(url_for("projects"))

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
        date = request.form.get("date", "").strip()
        try:
            hours = float(request.form.get("hours", 0))
        except ValueError:
            flash("Hours must be a number.", "error")
            return redirect(url_for("time_entries"))
        if not project_id or hours <= 0:
            flash("Project and hours required.", "error")
            return redirect(url_for("time_entries"))
        if not date:
            flash("Date is required.", "error")
            return redirect(url_for("time_entries"))
        entries = storage.load_time_entries()
        entries.append({
            "id": storage.new_id(),
            "project_id": project_id,
            "date": date,
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
            entry["date"] = request.form.get("date", entry["date"]).strip() or entry["date"]
            try:
                hours = float(request.form.get("hours", entry["hours"]))
            except ValueError:
                flash("Hours must be a number.", "error")
                return redirect(url_for("time_entries"))
            if hours <= 0:
                flash("Hours must be greater than zero.", "error")
                return redirect(url_for("time_entries"))
            entry["hours"] = hours
            entry["description"] = request.form.get("description", "").strip()
            storage.save_time_entries(entries)
            flash("Entry updated.", "success")
            return redirect(url_for("time_entries"))
        projects = storage.load_projects()
        return render_template("time.html", edit_entry=entry,
                               entries=sorted(storage.load_time_entries(), key=lambda e: e["date"], reverse=True),
                               projects=projects,
                               project_map={p["id"]: p for p in projects},
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

    # Stub routes — implemented in later tasks

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
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        project_id = request.form["project_id"]
        date = request.form.get("date", "").strip()
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            flash("Amount must be a number.", "error")
            return redirect(url_for("expenses"))
        if not project_id or amount <= 0:
            flash("Project and amount required.", "error")
            return redirect(url_for("expenses"))
        if not date:
            flash("Date is required.", "error")
            return redirect(url_for("expenses"))

        pdf_filename = None
        receipt = request.files.get("receipt")
        if receipt and receipt.filename and receipt.filename.lower().endswith(".pdf") \
                and receipt.mimetype == "application/pdf":
            expense_pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_filename = storage.new_id() + ".pdf"
            receipt.save(str(expense_pdf_dir / pdf_filename))

        items = storage.load_expenses()
        items.append({
            "id": storage.new_id(),
            "project_id": project_id,
            "date": date,
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
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if not item:
            flash("Expense not found.", "error")
            return redirect(url_for("expenses"))
        if item["invoiced"]:
            flash("Cannot edit an invoiced expense.", "error")
            return redirect(url_for("expenses"))
        if request.method == "POST":
            item["project_id"] = request.form["project_id"]
            item["date"] = request.form.get("date", item["date"]).strip() or item["date"]
            try:
                amount = float(request.form.get("amount", item["amount"]))
            except ValueError:
                flash("Amount must be a number.", "error")
                return redirect(url_for("expenses"))
            if amount <= 0:
                flash("Amount must be greater than zero.", "error")
                return redirect(url_for("expenses"))
            item["amount"] = amount
            item["description"] = request.form.get("description", "").strip()
            receipt = request.files.get("receipt")
            if receipt and receipt.filename and receipt.filename.lower().endswith(".pdf") \
                    and receipt.mimetype == "application/pdf":
                if item.get("pdf_filename"):
                    old_path = expense_pdf_dir / item["pdf_filename"]
                    if old_path.exists():
                        old_path.unlink()
                expense_pdf_dir.mkdir(parents=True, exist_ok=True)
                pdf_filename = storage.new_id() + ".pdf"
                receipt.save(str(expense_pdf_dir / pdf_filename))
                item["pdf_filename"] = pdf_filename
            storage.save_expenses(items)
            flash("Expense updated.", "success")
            return redirect(url_for("expenses"))
        projects = storage.load_projects()
        return render_template("expenses.html", edit_expense=item,
                               expenses=sorted(items, key=lambda x: x["date"], reverse=True),
                               projects=projects,
                               project_map={p["id"]: p for p in projects},
                               pf="", df="", dt="")

    @app.route("/expenses/<xid>/delete", methods=["POST"])
    def expenses_delete(xid):
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if item and item["invoiced"]:
            flash("Cannot delete an invoiced expense.", "error")
            return redirect(url_for("expenses"))
        if item and item.get("pdf_filename"):
            pdf_path = expense_pdf_dir / item["pdf_filename"]
            if pdf_path.exists():
                pdf_path.unlink()
        items = [x for x in items if x["id"] != xid]
        storage.save_expenses(items)
        flash("Expense deleted.", "success")
        return redirect(url_for("expenses"))

    @app.route("/expenses/<xid>/receipt")
    def expenses_receipt(xid):
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        items = storage.load_expenses()
        item = next((x for x in items if x["id"] == xid), None)
        if not item or not item.get("pdf_filename"):
            flash("No receipt found.", "error")
            return redirect(url_for("expenses"))
        pdf_path = expense_pdf_dir / item["pdf_filename"]
        if not pdf_path.exists():
            flash("Receipt file missing.", "error")
            return redirect(url_for("expenses"))
        return send_file(str(pdf_path), download_name=f"receipt-{item['date']}.pdf",
                         as_attachment=True, mimetype="application/pdf")

    @app.route("/invoices")
    def invoices():
        client_id = request.args.get("client_id", "")
        all_clients = storage.load_clients()
        client_map = {c["id"]: c for c in all_clients}
        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        all_entries = storage.load_time_entries()
        all_expenses = storage.load_expenses()
        all_invoices = storage.load_invoices()

        preview = None
        if client_id:
            client = client_map.get(client_id)
            client_projects = [p for p in projects if p.get("client_id") == client_id]
            client_pids = {p["id"] for p in client_projects}

            sections = []
            for p in client_projects:
                time_entries = sorted(
                    [e for e in all_entries if e["project_id"] == p["id"] and not e["invoiced"]],
                    key=lambda e: e["date"])
                expenses = sorted(
                    [x for x in all_expenses if x["project_id"] == p["id"] and not x["invoiced"]],
                    key=lambda x: x["date"])
                if time_entries or expenses:
                    sections.append({"project": p, "time_entries": time_entries, "expenses": expenses})

            if sections:
                settings_data = storage.load_settings()
                gst_rate = settings_data.get("gst_rate", 0.05)
                subtotal = round(sum(
                    sum(e["hours"] * s["project"]["rate"] for e in s["time_entries"]) +
                    sum(x["amount"] for x in s["expenses"])
                    for s in sections), 2)
                gst = round(subtotal * gst_rate, 2)
                preview = {
                    "client": client,
                    "sections": sections,
                    "subtotal": subtotal,
                    "gst": gst,
                    "total": round(subtotal + gst, 2),
                }

        return render_template("invoices.html", clients=all_clients, client_map=client_map,
                               project_map=project_map, invoices=all_invoices,
                               preview=preview, selected_client=client_id)

    @app.route("/invoices/generate", methods=["POST"])
    def invoices_generate():
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        client_id = request.form["client_id"]
        settings_data = storage.load_settings()
        all_clients = storage.load_clients()
        client_map = {c["id"]: c for c in all_clients}
        client = client_map.get(client_id)
        if not client:
            flash("Client not found.", "error")
            return redirect(url_for("invoices"))

        projects = storage.load_projects()
        project_map = {p["id"]: p for p in projects}
        client_projects = [p for p in projects if p.get("client_id") == client_id]

        all_entries = storage.load_time_entries()
        all_expenses = storage.load_expenses()

        line_items = []
        for p in client_projects:
            uninvoiced_time = sorted(
                [e for e in all_entries if e["project_id"] == p["id"] and not e["invoiced"]],
                key=lambda e: e["date"])
            uninvoiced_exp = sorted(
                [x for x in all_expenses if x["project_id"] == p["id"] and not x["invoiced"]],
                key=lambda x: x["date"])
            for e in uninvoiced_time:
                amount = round(e["hours"] * p["rate"], 2)
                line_items.append({"type": "time", "date": e["date"], "description": e["description"],
                                    "project_name": p["name"],
                                    "hours": e["hours"], "rate": p["rate"], "amount": amount,
                                    "entry_id": e["id"]})
            for x in uninvoiced_exp:
                line_items.append({"type": "expense", "date": x["date"],
                                    "description": x["description"], "project_name": p["name"],
                                    "amount": x["amount"], "pdf_filename": x.get("pdf_filename"),
                                    "expense_id": x["id"]})

        if not line_items:
            flash("No uninvoiced entries for this client.", "error")
            return redirect(url_for("invoices"))

        subtotal = round(sum(li["amount"] for li in line_items), 2)
        gst_rate = settings_data.get("gst_rate", 0.05)
        gst = round(subtotal * gst_rate, 2)
        total = round(subtotal + gst, 2)

        existing = storage.load_invoices()
        nums = []
        for inv in existing:
            parts = inv.get("invoice_number", "").split("-")
            if len(parts) == 2 and parts[1].isdigit():
                nums.append(int(parts[1]))
        next_num = max(nums) + 1 if nums else 1
        invoice_number = f"INV-{next_num:03d}"

        invoice = {
            "id": storage.new_id(),
            "invoice_number": invoice_number,
            "client_id": client["id"],
            "client_name": client["name"],
            "client_email": client.get("email", ""),
            "client_address": client.get("address", ""),
            "issued_date": dt_date.today().isoformat(),
            "subtotal": subtotal,
            "gst": gst,
            "total": total,
            "sent": False,
            "line_items": line_items,
        }

        # Save invoice first so a crash during entry marking doesn't lose the invoice record
        existing.append(invoice)
        storage.save_invoices(existing)

        invoiced_time_ids = {li["entry_id"] for li in line_items if li["type"] == "time"}
        invoiced_expense_ids = {li["expense_id"] for li in line_items if li["type"] == "expense"}
        for e in all_entries:
            if e["id"] in invoiced_time_ids:
                e["invoiced"] = True
        storage.save_time_entries(all_entries)
        for x in all_expenses:
            if x["id"] in invoiced_expense_ids:
                x["invoiced"] = True
        storage.save_expenses(all_expenses)

        flash(f"Invoice {invoice_number} generated.", "success")
        return redirect(url_for("invoices"))

    @app.route("/invoices/<inv_id>/pdf")
    def invoices_pdf(inv_id):
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        inv_list = storage.load_invoices()
        invoice = next((i for i in inv_list if i["id"] == inv_id), None)
        if not invoice:
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices"))
        settings_data = storage.load_settings()
        try:
            pdf_bytes = pdf.generate_invoice_pdf(app, invoice, settings_data, expense_pdf_dir=expense_pdf_dir)
        except Exception as e:
            flash(f"PDF error: {e}", "error")
            return redirect(url_for("invoices"))
        return send_file(BytesIO(pdf_bytes), download_name=f"{invoice['invoice_number']}.pdf",
                         as_attachment=True, mimetype="application/pdf")

    @app.route("/invoices/<inv_id>/send", methods=["POST"])
    def invoices_send(inv_id):
        expense_pdf_dir = storage.DATA_DIR / "expense_pdfs"
        inv_list = storage.load_invoices()
        invoice = next((i for i in inv_list if i["id"] == inv_id), None)
        if not invoice:
            flash("Invoice not found.", "error")
            return redirect(url_for("invoices"))
        recipient = request.form.get("recipient", "").strip()
        if not recipient:
            flash("Recipient email required.", "error")
            return redirect(url_for("invoices"))
        settings_data = storage.load_settings()
        try:
            pdf_bytes = pdf.generate_invoice_pdf(app, invoice, settings_data, expense_pdf_dir=expense_pdf_dir)
        except Exception as e:
            flash(f"PDF error: {e}", "error")
            return redirect(url_for("invoices"))
        from timesheet.mailer import send_invoice_email
        subject = request.form.get("subject", f"{invoice['invoice_number']} from {settings_data.get('business_name','')}")
        body = request.form.get("body", "Please find your invoice attached.")
        try:
            send_invoice_email(settings_data, recipient, subject, body,
                               pdf_bytes, invoice["invoice_number"])
            for i in inv_list:
                if i["id"] == inv_id:
                    i["sent"] = True
            storage.save_invoices(inv_list)
            flash(f"Invoice sent to {recipient}.", "success")
        except Exception as e:
            flash(f"Failed to send email: {e}", "error")
        return redirect(url_for("invoices"))

    @app.route("/reports/monthly")
    def report_monthly():
        today = dt_date.today()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
            if not (1 <= month <= 12):
                raise ValueError
        except ValueError:
            year, month = today.year, today.month
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
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0, "billable": 0.0, "expenses": 0}
            rows[pid]["hours"] += e["hours"]
            rows[pid]["billable"] += e["hours"] * p.get("rate", 0)
        for x in expenses:
            pid = x["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"), "hours": 0, "billable": 0.0, "expenses": 0}
            rows[pid]["expenses"] += x["amount"]

        for r in rows.values():
            r["billable"] = round(r["billable"], 2)
            r["total"] = round(r["billable"] + r["expenses"], 2)

        grand = {
            "hours": sum(r["hours"] for r in rows.values()),
            "billable": round(sum(r["billable"] for r in rows.values()), 2),
            "expenses": round(sum(r["expenses"] for r in rows.values()), 2),
            "total": round(sum(r["total"] for r in rows.values()), 2),
        }

        return render_template("report_monthly.html", rows=rows, grand=grand,
                               year=year, month=month)

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
                rows[pid] = {"name": p.get("name", "Unknown"),
                             "client_id": p.get("client_id") or "",
                             "hours": 0, "billable": 0.0, "expenses": 0,
                             "entries": [], "expense_items": []}
            entry_amount = round(e["hours"] * p.get("rate", 0), 2)
            rows[pid]["hours"] += e["hours"]
            rows[pid]["billable"] += entry_amount
            rows[pid]["entries"].append({**e, "amount": entry_amount})
        for x in expenses:
            pid = x["project_id"]
            p = project_map.get(pid, {})
            if pid not in rows:
                rows[pid] = {"name": p.get("name", "Unknown"),
                             "client_id": p.get("client_id") or "",
                             "hours": 0, "billable": 0.0, "expenses": 0,
                             "entries": [], "expense_items": []}
            rows[pid]["expenses"] += x["amount"]
            rows[pid]["expense_items"].append(x)

        for r in rows.values():
            r["billable"] = round(r["billable"], 2)
            r["total"] = round(r["billable"] + r["expenses"], 2)

        grand = {
            "hours": sum(r["hours"] for r in rows.values()),
            "billable": round(sum(r["billable"] for r in rows.values()), 2),
            "expenses": round(sum(r["expenses"] for r in rows.values()), 2),
            "total": round(sum(r["total"] for r in rows.values()), 2),
        }

        return render_template("report_uninvoiced.html", rows=rows, grand=grand)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
