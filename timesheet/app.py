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
            })
            storage.save_settings(s)
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        return render_template("settings.html", s=storage.load_settings())

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
        found = False
        for p in projects:
            if p["id"] == pid:
                p["name"] = request.form["name"].strip()
                p["rate"] = float(request.form.get("rate", p["rate"]))
                found = True
                break
        if not found:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))
        storage.save_projects(projects)
        flash("Project updated.", "success")
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
        try:
            hours = float(request.form.get("hours", 0))
        except ValueError:
            flash("Hours must be a number.", "error")
            return redirect(url_for("time_entries"))
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
            try:
                entry["hours"] = float(request.form.get("hours", entry["hours"]))
            except ValueError:
                flash("Hours must be a number.", "error")
                return redirect(url_for("time_entries"))
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

    # Stub routes — implemented in later tasks

    @app.route("/expenses")
    def expenses():
        return render_template("dashboard.html", projects=[], today="", today_entries=[], project_map={})

    @app.route("/invoices")
    def invoices():
        return render_template("dashboard.html", projects=[], today="", today_entries=[], project_map={})

    @app.route("/reports/monthly")
    def report_monthly():
        return render_template("dashboard.html", projects=[], today="", today_entries=[], project_map={})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
