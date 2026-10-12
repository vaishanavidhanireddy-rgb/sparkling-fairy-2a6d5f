import hmac
import re
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from database.models import connection
from routes.reports import login_required

hospitals_bp = Blueprint("hospitals", __name__)


@hospitals_bp.get("/hospitals")
@login_required
def directory():
    with connection(current_app.config["DATABASE_PATH"]) as db:
        patient = db.execute("SELECT state, area, country FROM users WHERE id = ?",
                             (session["user_id"],)).fetchone()
        hospitals = []
        if patient and patient["state"] and patient["area"]:
            hospitals = db.execute(
                "SELECT name, email, phone, address, website FROM hospitals "
                "WHERE status = 'approved' AND lower(state) = lower(?) "
                "AND lower(area) = lower(?) AND lower(country) = lower(?) "
                "ORDER BY name COLLATE NOCASE",
                (patient["state"], patient["area"], patient["country"] or "India"),
            ).fetchall()
    return render_template("hospital_directory.html", hospitals=hospitals, patient=patient)


@hospitals_bp.route("/hospitals/register", methods=["GET", "POST"])
def register_hospital():
    if request.method == "GET":
        return render_template("hospital_register.html")
    fields = {
        "name": request.form.get("name", "").strip()[:160],
        "email": request.form.get("email", "").strip().lower()[:254],
        "phone": request.form.get("phone", "").strip(),
        "state": request.form.get("state", "").strip()[:100],
        "area": request.form.get("area", "").strip()[:100],
        "country": request.form.get("country", "India").strip()[:100] or "India",
        "address": request.form.get("address", "").strip()[:500],
        "website": request.form.get("website", "").strip()[:300],
    }
    if not all(fields[key] for key in ("name", "email", "phone", "state", "area", "address")):
        flash("Complete all required hospital details.", "error")
        return render_template("hospital_register.html", values=fields), 400
    if "@" not in fields["email"] or not re.fullmatch(r"\+[1-9][0-9]{7,14}", fields["phone"]):
        flash("Enter a valid email and an international phone number, such as +919876543210.", "error")
        return render_template("hospital_register.html", values=fields), 400
    if fields["website"] and urlparse(fields["website"]).scheme not in ("http", "https"):
        flash("Hospital website must start with http:// or https://.", "error")
        return render_template("hospital_register.html", values=fields), 400
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute(
            "INSERT INTO hospitals (name, email, phone, state, area, country, address, website) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(fields[key] for key in ("name", "email", "phone", "state", "area", "country", "address", "website")),
        )
    return render_template("hospital_register.html", submitted=True)


@hospitals_bp.route("/hospitals/admin", methods=["GET", "POST"])
def hospital_admin():
    is_admin = False
    submitted_key = ""
    if request.method == "POST":
        configured_key = current_app.config["HOSPITAL_ADMIN_KEY"]
        submitted_key = request.form.get("admin_key", "")
        if not configured_key:
            flash("Hospital review is not configured. Set HOSPITAL_ADMIN_KEY on the server.", "error")
        elif hmac.compare_digest(submitted_key, configured_key):
            is_admin = True
        else:
            flash("Incorrect review key.", "error")
    submissions = []
    if is_admin:
        with connection(current_app.config["DATABASE_PATH"]) as db:
            submissions = db.execute("SELECT * FROM hospitals WHERE status = 'pending' ORDER BY id").fetchall()
    return render_template("hospital_admin.html", submissions=submissions,
                           is_admin=is_admin, admin_key=submitted_key)


@hospitals_bp.post("/hospitals/admin/<int:hospital_id>/<action>")
def review_hospital(hospital_id, action):
    configured_key = current_app.config["HOSPITAL_ADMIN_KEY"]
    submitted_key = request.form.get("admin_key", "")
    if not configured_key or not hmac.compare_digest(submitted_key, configured_key):
        return redirect(url_for("hospitals.hospital_admin"))
    if action not in ("approve", "reject"):
        return "Not found", 404
    status = "approved" if action == "approve" else "rejected"
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("UPDATE hospitals SET status = ? WHERE id = ? AND status = 'pending'",
                   (status, hospital_id))
    flash(f"Hospital listing {status}.", "success")
    return redirect(url_for("hospitals.hospital_admin"))
