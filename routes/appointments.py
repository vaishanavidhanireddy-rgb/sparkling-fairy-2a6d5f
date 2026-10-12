"""Government-sourced hospital discovery and clearly marked demo requests."""
import csv
import hashlib
import io
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from database.appointment_imports import align_hospital_cities, read_hospitals_csv
from database.models import connection
from routes.react_view import render_dashboard

appointments_bp = Blueprint("appointments", __name__)
MAX_DIRECTORY_BYTES = 15 * 1024 * 1024
MAX_DIRECTORY_ROWS = 100000
NMC_DOCTOR_SEARCH = "https://nmr.nmc.org.in/search-doctor"
TIME_SLOTS = {"morning", "afternoon", "evening"}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def hospital_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        email = session.get("email", "").strip().casefold()
        if email not in current_app.config.get("HOSPITAL_ADMIN_EMAILS", set()):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _api_error(message, status=400):
    return jsonify(error=message), status


def _clean_source_value(value):
    value = (value or "").strip()
    return "" if value.casefold() in {"0", "na", "n/a", "null", "none", "-"} else value


def _normalize_header(value):
    return "_".join((value or "").strip().casefold().replace("/", " ").split()).replace("__", "_")


@appointments_bp.get("/appointments")
@login_required
def directory():
    with connection(current_app.config["DATABASE_PATH"]) as db:
        directory_count = db.execute("SELECT COUNT(*) FROM appointment_hospitals").fetchone()[0]
        state_count = db.execute("SELECT COUNT(*) FROM appointment_states WHERE active=1").fetchone()[0]
        district_count = db.execute("SELECT COUNT(*) FROM appointment_districts WHERE active=1").fetchone()[0]
        location_count = db.execute("SELECT COUNT(*) FROM appointment_locations WHERE active=1").fetchone()[0]
        doctor_count = db.execute("SELECT COUNT(*) FROM appointment_doctors").fetchone()[0]
        appointments = db.execute(
            """SELECT a.id,a.appointment_date,a.appointment_at,a.time_slot,a.booking_mode,a.status,a.reason,
                      h.hospital_name,h.state,h.district,h.city,
                      COALESCE(d.doctor_name,'') AS doctor_name
               FROM appointment_requests a
               JOIN appointment_hospitals h ON h.id=a.hospital_id
               LEFT JOIN appointment_doctors d ON d.id=a.doctor_id
               WHERE a.user_id=? ORDER BY a.appointment_date DESC,a.id DESC""",
            (session["user_id"],),
        ).fetchall()
    is_hospital_admin = session.get("email", "").strip().casefold() in current_app.config.get("HOSPITAL_ADMIN_EMAILS", set())
    return render_dashboard(
        reports=[], page="appointments", appointments=appointments,
        directory_count=directory_count, state_count=state_count,
        district_count=district_count, location_count=location_count,
        doctor_count=doctor_count, is_hospital_admin=is_hospital_admin,
    )


@appointments_bp.get("/api/appointments/states")
@login_required
def api_states():
    with connection(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            """SELECT name FROM (
                   SELECT state AS name FROM appointment_states WHERE active=1
                   UNION SELECT state AS name FROM appointment_districts WHERE active=1
                   UNION SELECT state AS name FROM appointment_locations WHERE active=1
                   UNION SELECT state AS name FROM appointment_hospitals
               ) WHERE trim(name)<>'' ORDER BY name COLLATE NOCASE"""
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@appointments_bp.get("/api/appointments/districts")
@login_required
def api_districts():
    state = request.args.get("state", "").strip()[:100]
    if not state:
        return _api_error("Choose a state first.")
    with connection(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            """SELECT name FROM (
                   SELECT district AS name FROM appointment_districts WHERE active=1 AND state=? COLLATE NOCASE
                   UNION SELECT district AS name FROM appointment_locations WHERE active=1 AND state=? COLLATE NOCASE
                   UNION SELECT district AS name FROM appointment_hospitals WHERE state=? COLLATE NOCASE
               ) WHERE trim(name)<>'' ORDER BY name COLLATE NOCASE""",
            (state, state, state),
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@appointments_bp.get("/api/appointments/cities")
@login_required
def api_cities():
    state = request.args.get("state", "").strip()[:100]
    district = request.args.get("district", "").strip()[:100]
    if not state or not district:
        return _api_error("Choose a state and district first.")
    with connection(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            """SELECT name FROM (
                   SELECT city AS name FROM appointment_locations
                   WHERE active=1 AND state=? COLLATE NOCASE AND district=? COLLATE NOCASE
                   UNION SELECT city AS name FROM appointment_hospitals
                   WHERE state=? COLLATE NOCASE AND district=? COLLATE NOCASE
               ) WHERE trim(name)<>'' ORDER BY name COLLATE NOCASE""",
            (state, district, state, district),
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@appointments_bp.get("/api/appointments/hospitals")
@login_required
def api_hospitals():
    state = request.args.get("state", "").strip()[:100]
    district = request.args.get("district", "").strip()[:100]
    city = request.args.get("city", "").strip()[:100]
    if not state or not district or not city:
        return _api_error("Choose a state, district, and city or town first.")
    with connection(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            """SELECT id,hospital_name,state,district,city,area,address,phone,category,care_type,
                      specialties,pincode,coordinates,source_type,source_record_id,source_url,imported_at
               FROM appointment_hospitals WHERE state=? COLLATE NOCASE AND district=? COLLATE NOCASE
               AND city=? COLLATE NOCASE ORDER BY hospital_name COLLATE NOCASE""",
            (state, district, city),
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@appointments_bp.get("/api/appointments/hospitals/<int:hospital_id>/doctors")
@login_required
def api_doctors(hospital_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        hospital = db.execute("SELECT id FROM appointment_hospitals WHERE id=?", (hospital_id,)).fetchone()
        if not hospital:
            return _api_error("Hospital listing not found.", 404)
        rows = db.execute(
            """SELECT id,doctor_name,specialty,registration_number,verification_url,verification_status,source_type
               FROM appointment_doctors WHERE hospital_id=? ORDER BY doctor_name COLLATE NOCASE""",
            (hospital_id,),
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@appointments_bp.get("/api/appointments/doctors")
@login_required
def api_doctor_directory():
    query = request.args.get("q", "").strip()[:100]
    specialty = request.args.get("specialty", "").strip()[:100]
    search = f"%{query}%"
    specialty_search = f"%{specialty}%"
    with connection(current_app.config["DATABASE_PATH"]) as db:
        rows = db.execute(
            """SELECT d.id,d.hospital_id,d.doctor_name,d.specialty,d.verification_status,
                      h.hospital_name,h.state,h.district,h.city
               FROM appointment_doctors d
               JOIN appointment_hospitals h ON h.id=d.hospital_id
               WHERE (?='' OR d.doctor_name LIKE ? COLLATE NOCASE
                    OR d.specialty LIKE ? COLLATE NOCASE
                    OR h.hospital_name LIKE ? COLLATE NOCASE)
                 AND (?='' OR d.specialty LIKE ? COLLATE NOCASE)
               ORDER BY d.doctor_name COLLATE NOCASE LIMIT 60""",
            (query, search, search, search, specialty, specialty_search),
        ).fetchall()
        specialties = db.execute(
            """SELECT DISTINCT specialty FROM appointment_doctors
               WHERE trim(specialty)<>'' ORDER BY specialty COLLATE NOCASE"""
        ).fetchall()
    return jsonify(items=[dict(row) for row in rows], specialties=[row["specialty"] for row in specialties])


@appointments_bp.post("/appointments/book")
@login_required
def book_demo_appointment():
    try:
        hospital_id = int(request.form.get("hospital_id", ""))
        doctor_id_value = request.form.get("doctor_id", "").strip()
        doctor_id = int(doctor_id_value) if doctor_id_value else None
        appointment_date = datetime.strptime(request.form.get("appointment_date", ""), "%Y-%m-%d").date()
        time_slot = request.form.get("time_slot", "").strip()
        if appointment_date < date.today() or time_slot not in TIME_SLOTS:
            raise ValueError
    except (TypeError, ValueError):
        flash("Choose a valid future date and a listed demo time preference.", "error")
        return redirect(url_for("appointments.directory"))
    if (appointment_date - date.today()).days > 365:
        flash("Choose a date within the next 12 months.", "error")
        return redirect(url_for("appointments.directory"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        hospital = db.execute("SELECT id FROM appointment_hospitals WHERE id=?", (hospital_id,)).fetchone()
        if not hospital:
            abort(404)
        if doctor_id is not None and not db.execute(
            "SELECT id FROM appointment_doctors WHERE id=? AND hospital_id=?", (doctor_id, hospital_id)
        ).fetchone():
            abort(400)
        user_id = session["user_id"]
        key_material = f"{user_id}|{hospital_id}|{doctor_id or 0}|{appointment_date.isoformat()}|{time_slot}"
        booking_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        try:
            db.execute(
                """INSERT INTO appointment_requests
                   (user_id,hospital_id,doctor_id,appointment_date,time_slot,booking_key,booking_mode,appointment_at,status)
                   VALUES(?,?,?,?,?,?, 'demo_request', ?, 'demo_pending')""",
                (user_id, hospital_id, doctor_id, appointment_date.isoformat(), time_slot,
                 booking_key, f"{appointment_date.isoformat()}T{time_slot}"),
            )
        except sqlite3.IntegrityError:
            flash("You already saved this demo request for that hospital, doctor, date, and time preference.", "error")
            return redirect(url_for("appointments.directory"))
    flash("Demo appointment request saved to your account. It was not sent to the hospital and is not a confirmed or available slot.", "success")
    return redirect(url_for("appointments.directory"))


@appointments_bp.post("/appointments/directory/upload")
@login_required
@hospital_admin_required
def upload_directory():
    # The official OGD CSV is larger than the normal patient-report upload cap.
    request.max_content_length = MAX_DIRECTORY_BYTES + 256 * 1024
    upload = request.files.get("directory_file")
    filename = (upload.filename or "").lower() if upload else ""
    if not upload or not filename.endswith(".csv"):
        flash("Choose a CSV file from the official OGD hospital directory or the documented admin format.", "error")
        return redirect(url_for("appointments.directory"))
    raw = upload.read(MAX_DIRECTORY_BYTES + 1)
    if not raw or len(raw) > MAX_DIRECTORY_BYTES:
        flash("The CSV is empty or larger than 15 MB.", "error")
        return redirect(url_for("appointments.directory"))
    try:
        normalized_rows = read_hospitals_csv(io.StringIO(raw.decode("utf-8-sig")))
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        flash(f"Could not read this hospital CSV: {exc}", "error")
        return redirect(url_for("appointments.directory"))
    if not normalized_rows or len(normalized_rows) > MAX_DIRECTORY_ROWS:
        flash("The CSV must contain 1 to 100,000 hospital rows.", "error")
        return redirect(url_for("appointments.directory"))

    with connection(current_app.config["DATABASE_PATH"]) as db:
        locations = [tuple(row) for row in db.execute(
            """SELECT state,district,city,source_code,pincodes FROM appointment_locations
               WHERE active=1"""
        )]
        normalized_rows = align_hospital_cities(normalized_rows, locations)
        db.executemany(
            """INSERT INTO appointment_hospitals
               (hospital_name,state,district,city,area,address,phone,category,care_type,specialties,pincode,
                coordinates,source_type,source_record_id,source_url,imported_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET
               address=excluded.address,phone=excluded.phone,category=excluded.category,care_type=excluded.care_type,
               specialties=excluded.specialties,pincode=excluded.pincode,coordinates=excluded.coordinates,
               source_type=excluded.source_type,source_record_id=excluded.source_record_id,
               source_url=excluded.source_url,imported_at=excluded.imported_at""",
            normalized_rows,
        )
    is_ogd = normalized_rows[0][12] == "data.gov.in"
    label = "official Government OGD rows" if is_ogd else "admin-provided, unverified rows"
    flash(f"Imported {len(normalized_rows)} {label}. Hospital listings are not live availability.", "success")
    return redirect(url_for("appointments.directory"))


@appointments_bp.post("/appointments/doctors/upload")
@login_required
@hospital_admin_required
def upload_doctors():
    upload = request.files.get("doctor_file")
    if not upload or not (upload.filename or "").lower().endswith(".csv"):
        flash("Choose a doctor CSV file.", "error")
        return redirect(url_for("appointments.directory"))
    raw = upload.read(2 * 1024 * 1024 + 1)
    if not raw or len(raw) > 2 * 1024 * 1024:
        flash("The doctor CSV is empty or larger than 2 MB.", "error")
        return redirect(url_for("appointments.directory"))
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        headers = {_normalize_header(header) for header in (reader.fieldnames or []) if header}
        required = {"hospital_name", "state", "district", "city", "doctor_name"}
        if not required.issubset(headers):
            raise ValueError("Required columns: hospital_name,state,district,city,doctor_name. specialty and registration_number are optional.")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        flash(f"Could not read this doctor CSV: {exc}", "error")
        return redirect(url_for("appointments.directory"))
    pending = []
    with connection(current_app.config["DATABASE_PATH"]) as db:
        for row_number, source in enumerate(rows, start=2):
            row = {_normalize_header(key): _clean_source_value(value) for key, value in source.items() if key and isinstance(value, str)}
            name = row.get("doctor_name", "")[:160]
            hospital = db.execute(
                """SELECT id FROM appointment_hospitals WHERE hospital_name=? COLLATE NOCASE
                   AND state=? COLLATE NOCASE AND district=? COLLATE NOCASE AND city=? COLLATE NOCASE LIMIT 1""",
                tuple(row.get(key, "")[:120] for key in ("hospital_name", "state", "district", "city")),
            ).fetchone()
            if not name or not hospital:
                flash(f"Doctor CSV row {row_number} has no matching hospital or doctor name. No doctors were imported.", "error")
                return redirect(url_for("appointments.directory"))
            pending.append((hospital["id"], name, row.get("specialty", "")[:160],
                            row.get("registration_number", "")[:80], NMC_DOCTOR_SEARCH))
        if not pending:
            flash("The doctor CSV contains no rows.", "error")
            return redirect(url_for("appointments.directory"))
        db.executemany(
            """INSERT INTO appointment_doctors
               (hospital_id,doctor_name,specialty,registration_number,verification_url,verification_status,source_type)
               VALUES(?,?,?,?,?,'unverified','admin_uploaded') ON CONFLICT DO UPDATE SET
               specialty=excluded.specialty,verification_url=excluded.verification_url,
               verification_status='unverified',source_type='admin_uploaded'""",
            pending,
        )
    flash(f"Imported {len(pending)} admin-provided doctor entries. They are unverified; check each registration in the NMC register.", "success")
    return redirect(url_for("appointments.directory"))


@appointments_bp.get("/appointments/directory/template.csv")
@login_required
@hospital_admin_required
def directory_template():
    content = "hospital_name,state,district,city,area,address,phone,specialties\n"
    return current_app.response_class(content, mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=hospital_directory_template.csv"
    })


@appointments_bp.get("/appointments/doctors/template.csv")
@login_required
@hospital_admin_required
def doctors_template():
    content = "hospital_name,state,district,city,doctor_name,specialty,registration_number\n"
    return current_app.response_class(content, mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=hospital_doctors_template.csv"
    })
