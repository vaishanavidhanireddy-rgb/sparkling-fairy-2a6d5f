import base64
import io
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from werkzeug.utils import secure_filename

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from database.models import connection
from ai.file_explanation import explain_upload
from ai.symptom_explanation import explain_symptom, read_local_groq_key
from security.consent import (
    ANALYSIS_PURPOSE, SMS_PURPOSE, has_analysis_consent, has_sms_consent,
    record_analysis_consent, record_sms_consent,
)

reports_bp = Blueprint("reports", __name__)
SHARE_PURPOSE = "Display this report to anyone with its QR link"
UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp", ".pdf": "application/pdf"}


def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("index"))
        if session.get("profile_required") and request.endpoint != "reports.complete_profile":
            return redirect(url_for("reports.complete_profile"))
        return view(*args, **kwargs)
    return wrapped


@reports_bp.route("/profile/complete", methods=["GET", "POST"])
@login_required
def complete_profile():
    if not session.get("profile_required"):
        return redirect(url_for("reports.dashboard"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        account = db.execute("SELECT phone, state, area, country FROM users WHERE id = ?",
                             (session["user_id"],)).fetchone()
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        state = request.form.get("state", "").strip()[:100]
        area = request.form.get("area", "").strip()[:100]
        country = request.form.get("country", "India").strip()[:100] or "India"
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) or not state or not area:
            flash("Enter your phone in international format and complete your country, state, and area.", "error")
            return render_template("complete_profile.html", account={"phone": phone, "state": state,
                                     "area": area, "country": country}), 400
        with connection(current_app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE users SET phone = ?, state = ?, area = ?, country = ? WHERE id = ?",
                       (phone, state, area, country, session["user_id"]))
        session.pop("profile_required", None)
        flash("Patient contact and location saved.", "success")
        return redirect(url_for("reports.dashboard"))
    return render_template("complete_profile.html", account=account)


@reports_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    symptom_result = None
    symptom_error = None
    if request.method == "POST":
        symptom = request.form.get("symptom", "").strip()
        if not symptom:
            symptom_error = "Describe a symptom or health question first."
        elif len(symptom) > 600:
            symptom_error = "Keep your question under 600 characters."
        else:
            try:
                groq_key = current_app.config.get("GROQ_API_KEY") or read_local_groq_key(current_app.root_path)
                if groq_key:
                    current_app.config["GROQ_API_KEY"] = groq_key
                symptom_result = explain_symptom(symptom, groq_key)
            except RuntimeError as exc:
                symptom_error = str(exc)
    with connection(current_app.config["DATABASE_PATH"]) as db:
        account = db.execute("SELECT email, phone, state, area, country FROM users WHERE id = ?",
                             (session["user_id"],)).fetchone()
        reports = db.execute("SELECT id, title, created_at, explanation FROM reports WHERE user_id = ? ORDER BY id DESC",
                             (session["user_id"],)).fetchall()
        consent = has_analysis_consent(db, session["user_id"])
        sms_consent = has_sms_consent(db, session["user_id"])
        shares = db.execute(
            "SELECT s.token, s.created_at, r.title FROM report_shares s "
            "JOIN reports r ON r.id = s.report_id "
            "WHERE s.user_id = ? AND s.revoked = 0 ORDER BY s.id DESC",
            (session["user_id"],),
        ).fetchall()
    share_items = []
    for share in shares:
        share_url = url_for("reports.shared_report", token=share["token"], _external=True)
        qr = qrcode.make(share_url)
        output = io.BytesIO()
        qr.save(output, format="PNG")
        share_items.append({"title": share["title"], "created_at": share["created_at"],
                            "url": share_url,
                            "qr_data": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii"),
                            "token": share["token"]})
    return render_template("dashboard.html", reports=reports, consent=consent,
                           purpose=ANALYSIS_PURPOSE, shares=share_items,
                           phone=account["phone"] or "", sms_consent=sms_consent,
                           sms_purpose=SMS_PURPOSE, patient_state=account["state"] or "",
                           patient_area=account["area"] or "", patient_country=account["country"] or "India",
                           symptom_result=symptom_result, symptom_error=symptom_error,
                           symptom_question=request.form.get("symptom", "") if request.method == "POST" else "")


@reports_bp.post("/reports")
@login_required
def add_report():
    title = request.form.get("title", "").strip()[:100]
    content = request.form.get("content", "").strip()[:20000]
    if not title or not content:
        flash("A title and report text are required.", "error")
        return redirect(url_for("reports.dashboard"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("INSERT INTO reports (user_id, title, content) VALUES (?, ?, ?)",
                   (session["user_id"], title, content))
    return redirect(url_for("reports.dashboard"))


@reports_bp.post("/reports/upload")
@login_required
def upload_report():
    uploaded = request.files.get("file")
    safe_name = secure_filename(uploaded.filename or "") if uploaded else ""
    extension = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    mime_type = UPLOAD_TYPES.get(extension)
    if not uploaded or not safe_name or not mime_type:
        flash("Choose a JPG, PNG, WEBP image, or PDF report.", "error")
        return redirect(url_for("reports.dashboard"))
    data = uploaded.read(2 * 1024 * 1024 + 1)
    if not data or len(data) > 2 * 1024 * 1024:
        flash("The file is empty or larger than 2 MB. Choose a smaller file.", "error")
        return redirect(url_for("reports.dashboard"))
    try:
        explanation = explain_upload(data, mime_type, current_app.config["GEMINI_API_KEY"])
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("reports.dashboard"))
    title = safe_name[:100]
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("INSERT INTO reports (user_id, title, content, explanation) VALUES (?, ?, ?, ?)",
                   (session["user_id"], title, explanation, explanation))
    flash("File explained in English and Telugu and saved to your reports.", "success")
    return redirect(url_for("reports.dashboard"))


@reports_bp.post("/consent")
@login_required
def consent():
    granted = request.form.get("granted") == "yes"
    with connection(current_app.config["DATABASE_PATH"]) as db:
        record_analysis_consent(db, session["user_id"], granted)
    flash("Analysis consent updated.", "success")
    return redirect(url_for("reports.dashboard"))


@reports_bp.post("/contact")
@login_required
def update_contact():
    phone = request.form.get("phone", "").strip()
    patient_state = request.form.get("state", "").strip()[:100]
    patient_area = request.form.get("area", "").strip()[:100]
    patient_country = request.form.get("country", "India").strip()[:100] or "India"
    sms_opt_in = request.form.get("sms_consent") == "yes"
    if phone and not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
        flash("Enter the phone number in international format, such as +14155552671.", "error")
        return redirect(url_for("reports.dashboard"))
    if sms_opt_in and not phone:
        flash("Add a phone number before opting in to SMS confirmations.", "error")
        return redirect(url_for("reports.dashboard"))
    if bool(patient_state) != bool(patient_area):
        flash("Enter both your state and your area, or leave both blank.", "error")
        return redirect(url_for("reports.dashboard"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("UPDATE users SET phone = ?, state = ?, area = ?, country = ? WHERE id = ?",
                   (phone or None, patient_state or None, patient_area or None,
                    patient_country, session["user_id"]))
        record_sms_consent(db, session["user_id"], sms_opt_in)
    flash("Patient contact, location, and SMS preference saved.", "success")
    return redirect(url_for("reports.dashboard"))


def send_twilio_sms(to_number, body):
    sid = current_app.config["TWILIO_ACCOUNT_SID"]
    token = current_app.config["TWILIO_AUTH_TOKEN"]
    from_number = current_app.config["TWILIO_PHONE_NUMBER"]
    if not sid or not token or not from_number:
        return False, "Twilio is not configured. Set its account SID, auth token, and sender number."
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = urllib.parse.urlencode({"To": to_number, "From": from_number, "Body": body}).encode("utf-8")
    credentials = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(endpoint, data=payload, headers={"Authorization": f"Basic {credentials}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, ""
            return False, "Twilio did not accept the message. Check your Twilio setup."
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False, "SMS could not be sent. Check your Twilio setup and connection."


@reports_bp.post("/reports/share")
@login_required
def create_share():
    report_id = request.form.get("report_id", type=int)
    if request.form.get("share_consent") != "yes":
        flash("Please confirm consent before creating a QR share link.", "error")
        return redirect(url_for("reports.dashboard"))
    if not report_id:
        flash("Choose a report to share.", "error")
        return redirect(url_for("reports.dashboard"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        report = db.execute("SELECT id, title FROM reports WHERE id = ? AND user_id = ?",
                            (report_id, session["user_id"])).fetchone()
        if not report:
            abort(404)
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO report_shares (token, user_id, report_id) VALUES (?, ?, ?)",
                   (token, session["user_id"], report_id))
        db.execute("INSERT INTO consents (user_id, purpose, granted) VALUES (?, ?, 1)",
                   (session["user_id"], SHARE_PURPOSE))
        account = db.execute("SELECT phone FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        sms_allowed = has_sms_consent(db, session["user_id"])
    share_url = url_for("reports.shared_report", token=token, _external=True)
    flash("QR share link created. Anyone who scans or receives it can view this report until you revoke it.", "success")
    if sms_allowed and account["phone"]:
        sent, message = send_twilio_sms(
            account["phone"],
            f"Quantum Healthcare: Your QR share link for '{report['title']}' is ready: {share_url} "
            "Anyone with this link can view the report. Revoke it from your dashboard.",
        )
        if sent:
            flash("SMS confirmation sent to your saved contact number.", "success")
        else:
            flash(message, "error")
    else:
        flash("No SMS sent. Add a contact number and opt in to SMS confirmations in your dashboard.", "notice")
    return redirect(url_for("reports.dashboard"))


@reports_bp.post("/reports/share/<token>/revoke")
@login_required
def revoke_share(token):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        cursor = db.execute("UPDATE report_shares SET revoked = 1 WHERE token = ? AND user_id = ?",
                             (token, session["user_id"]))
        if cursor.rowcount:
            flash("QR share link revoked.", "success")
    return redirect(url_for("reports.dashboard"))


@reports_bp.get("/shared/<token>")
def shared_report(token):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        report = db.execute(
            "SELECT r.title, r.content, r.created_at FROM report_shares s "
            "JOIN reports r ON r.id = s.report_id "
            "WHERE s.token = ? AND s.revoked = 0",
            (token,),
        ).fetchone()
    if not report:
        abort(404)
    response = current_app.make_response(render_template("shared_report.html", report=report))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
