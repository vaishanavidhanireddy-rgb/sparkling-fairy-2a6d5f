import io
import re
from datetime import date
from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from database.models import connection
from routes.react_view import render_dashboard, render_react_page
from ai.file_explanation import explain_upload, explain_saved_text
from ai.report_comparison import compare_reports, extract_measurements
from ai.symptom_explanation import answer_report_question, explain_symptom, suggest_wellness
from ai.biomarkers import extract_biomarkers

reports_bp = Blueprint("reports", __name__)
UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def _reports(user_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        return db.execute("SELECT id,title,content,explanation,mime_type,created_at FROM reports WHERE user_id=? ORDER BY created_at DESC,id DESC", (user_id,)).fetchall()


@reports_bp.get("/dashboard")
@login_required
def dashboard():
    return render_dashboard(**_dashboard_context(session["user_id"]))


@reports_bp.get("/welcome")
@login_required
def welcome():
    context = _dashboard_context(session["user_id"])
    context["page"] = "dashboard"
    return render_dashboard(**context)


@reports_bp.get("/health-insights")
@login_required
def health_insights_page():
    context = _dashboard_context(session["user_id"])
    context["page"] = "insights"
    return render_dashboard(**context)


@reports_bp.get("/wellness")
@login_required
def wellness_page():
    context = _dashboard_context(session["user_id"])
    context["page"] = "wellness"
    return render_dashboard(**context)


@reports_bp.get("/medications")
@login_required
def medications_page():
    context = _dashboard_context(session["user_id"])
    context["page"] = "medications"
    return render_dashboard(**context)


@reports_bp.route("/complete-profile", methods=["GET", "POST"])
@login_required
def complete_profile():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        country = request.form.get("country", "India").strip()[:100] or "India"
        state = request.form.get("state", "").strip()[:100]
        area = request.form.get("area", "").strip()[:100]
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) or not state or not area:
            flash("Enter a valid international phone number, country, state, and area.", "error")
        else:
            with connection(current_app.config["DATABASE_PATH"]) as db:
                db.execute("UPDATE users SET phone=?,country=?,state=?,area=? WHERE id=?",
                           (phone, country, state, area, session["user_id"]))
            session.pop("profile_required", None)
            flash("Profile completed.", "success")
            return redirect(url_for("reports.dashboard"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        account = db.execute("SELECT phone,country,state,area FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_react_page("profile", account=account)


def _dashboard_context(user_id):
    today = date.today().isoformat()
    with connection(current_app.config["DATABASE_PATH"]) as db:
        medications = db.execute("SELECT id,name,instructions,reminder_time FROM medications WHERE user_id=? AND active=1 ORDER BY reminder_time,id", (user_id,)).fetchall()
        wellness = db.execute("SELECT * FROM wellness_logs WHERE user_id=? AND log_date=?", (user_id, today)).fetchone()
        wellness_history = db.execute("SELECT * FROM wellness_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 7", (user_id,)).fetchall()
        appointments = db.execute(
            """SELECT a.id,a.appointment_date,a.time_slot,a.status,a.booking_mode,
                      h.hospital_name,h.city,h.district,h.state,COALESCE(d.doctor_name,'') AS doctor_name
               FROM appointment_requests a
               JOIN appointment_hospitals h ON h.id=a.hospital_id
               LEFT JOIN appointment_doctors d ON d.id=a.doctor_id
               WHERE a.user_id=? AND a.appointment_date>=?
               ORDER BY a.appointment_date,a.id LIMIT 5""",
            (user_id, today),
        ).fetchall()
    reports = _reports(user_id)
    measurements = extract_biomarkers(reports)
    suggestions = _wellness_suggestions(wellness)
    return {"reports": reports, "page": "dashboard", "medications": medications,
            "appointments": appointments,
            "measurements": measurements,
            "abnormal_result_count": sum(1 for item in measurements if item["abnormal"]),
            "wellness": wellness, "wellness_history": wellness_history,
            "wellness_suggestions": suggestions,
            "max_steps": max((row["steps"] for row in wellness_history), default=0),
            "today": today}


def _wellness_suggestions(log):
    if not log:
        return ["Log today's habits to see a gentle reflection based on your entries."]
    tips = []
    if log["focus"].strip():
        tips.append(f"You chose to focus on: {log['focus'].strip()}. Take a manageable step that fits your day and any advice from your clinician.")
    if log["sleep_hours"] and log["sleep_hours"] < 7:
        tips.append("You logged under 7 hours of sleep. A steady wind-down routine may help; sleep needs vary from person to person.")
    if log["exercise_minutes"] == 0:
        tips.append("No movement was logged today. If it feels comfortable for you, consider a brief walk or stretch.")
    elif log["exercise_minutes"] > 0:
        tips.append("You logged movement today. Taking breaks and choosing activities that feel comfortable can help make a routine sustainable.")
    if log["water_glasses"]:
        tips.append("You logged your water intake. Follow any fluid limits or advice given by your clinician.")
    if not tips:
        tips.append("Thanks for logging today. Keep choosing routines that fit your needs and any guidance from your clinician.")
    return tips[:3]


@reports_bp.post("/medications")
@login_required
def add_medication():
    name = request.form.get("name", "").strip()[:100]
    instructions = request.form.get("instructions", "").strip()[:300]
    reminder_time = request.form.get("reminder_time", "").strip()
    if not name or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", reminder_time):
        flash("Enter a medicine name and a valid reminder time.", "error")
    else:
        with connection(current_app.config["DATABASE_PATH"]) as db:
            db.execute("INSERT INTO medications(user_id,name,instructions,reminder_time) VALUES(?,?,?,?)",
                       (session["user_id"], name, instructions, reminder_time))
        flash("Reminder saved. Follow the schedule provided by your clinician.", "success")
    return redirect(url_for("reports.medications_page"))


@reports_bp.post("/medications/<int:medication_id>/delete")
@login_required
def delete_medication(medication_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("DELETE FROM medications WHERE id=? AND user_id=?", (medication_id, session["user_id"]))
    flash("Medicine reminder removed.", "success")
    return redirect(url_for("reports.medications_page"))


@reports_bp.post("/wellness")
@login_required
def save_wellness():
    try:
        water = int(request.form.get("water_glasses", "0"))
        sleep = float(request.form.get("sleep_hours", "0"))
        exercise = int(request.form.get("exercise_minutes", "0"))
        steps = int(request.form.get("steps", "0"))
        focus = request.form.get("focus", "").strip()[:120]
        if not (0 <= water <= 30 and 0 <= sleep <= 24 and 0 <= exercise <= 1440 and 0 <= steps <= 100000):
            raise ValueError
    except ValueError:
        flash("Check your entries: water 0-30 glasses, sleep 0-24 hours, exercise 0-1440 minutes, steps 0-100000.", "error")
        return redirect(url_for("reports.wellness_page"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("""INSERT INTO wellness_logs(user_id,log_date,water_glasses,sleep_hours,exercise_minutes,steps,focus)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,log_date) DO UPDATE SET
            water_glasses=excluded.water_glasses,sleep_hours=excluded.sleep_hours,
            exercise_minutes=excluded.exercise_minutes,steps=excluded.steps,focus=excluded.focus""",
            (session["user_id"], date.today().isoformat(), water, sleep, exercise, steps, focus))
    flash("Today's wellness entries saved.", "success")
    return redirect(url_for("reports.wellness_page"))


@reports_bp.post("/wellness/suggestions")
@login_required
def generate_wellness_suggestions():
    if request.form.get("share_daily_log") != "yes":
        flash("Confirm before sending today's wellness log to NVIDIA NIM for AI suggestions.", "error")
        return redirect(url_for("reports.wellness_page"))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        log = db.execute("SELECT * FROM wellness_logs WHERE user_id=? AND log_date=?",
                         (session["user_id"], date.today().isoformat())).fetchone()
    if not log:
        flash("Save today's wellness check-in before requesting AI ideas.", "error")
        return redirect(url_for("reports.wellness_page"))
    try:
        suggestions = suggest_wellness(log, current_app.config.get("NVIDIA_NIM_API_KEY", ""),
                                      model=current_app.config.get("NVIDIA_NIM_MODEL", "meta/llama-3.2-11b-vision-instruct"))
    except RuntimeError as exc:
        context = _dashboard_context(session["user_id"])
        context["ai_wellness_error"] = str(exc)
        context["page"] = "wellness"
        return render_dashboard(**context)
    context = _dashboard_context(session["user_id"])
    context["ai_wellness_suggestions"] = suggestions
    context["page"] = "wellness"
    return render_dashboard(**context)


@reports_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        uploaded = request.files.get("file")
        name = secure_filename(uploaded.filename or "") if uploaded else ""
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        mime = UPLOAD_TYPES.get(ext)
        if not mime:
            flash("Choose a PDF, JPG, or PNG report.", "error")
            return redirect(url_for("reports.upload"))
        data = uploaded.read(2 * 1024 * 1024 + 1)
        if not data or len(data) > 2 * 1024 * 1024:
            flash("The file is empty or larger than 2 MB.", "error")
            return redirect(url_for("reports.upload"))
        valid_signature = (data.startswith(b"%PDF-") if mime == "application/pdf" else
                           data.startswith(b"\xff\xd8\xff") if mime == "image/jpeg" else
                           data.startswith(b"\x89PNG\r\n\x1a\n"))
        if not valid_signature:
            flash("The file contents do not match the selected report type.", "error")
            return redirect(url_for("reports.upload"))
        extraction_warning = False
        try:
            from ai.file_explanation import extract_report_text
            extracted = extract_report_text(data, mime)
        except RuntimeError:
            extracted = ""
            extraction_warning = True
        body = extracted or "Text could not be extracted from this file. Request an AI explanation to analyze the saved report file."
        with connection(current_app.config["DATABASE_PATH"]) as db:
            cursor = db.execute("INSERT INTO reports (user_id,title,content,file_data,mime_type) VALUES (?,?,?,?,?)",
                                (session["user_id"], name[:100], body[:20000], data, mime))
            report_id = cursor.lastrowid
        flash("Report saved privately. Open it in your history when you are ready to request an English and Telugu explanation.", "success")
        if extraction_warning:
            flash("Local text extraction is unavailable, but the saved file can still be sent for an AI explanation when requested.", "error")
        return redirect(url_for("reports.view_report", report_id=report_id))
    return render_dashboard(reports=_reports(session["user_id"]), page="upload")


@reports_bp.route("/explanation", methods=["GET", "POST"])
@login_required
def explanation():
    question = answer = error = ""
    reports = _reports(session["user_id"])
    if request.method == "POST":
        question = request.form.get("question", "").strip()[:1000]
        if question:
            try:
                answer = explain_symptom(question, current_app.config.get("NVIDIA_NIM_API_KEY", ""),
                                         model=current_app.config.get("NVIDIA_NIM_MODEL", "meta/llama-3.2-11b-vision-instruct"))
            except RuntimeError as exc:
                error = str(exc)
    return render_dashboard(reports=reports, page="explanation", question=question, answer=answer, error=error)


@reports_bp.post("/api/assistant")
@login_required
def assistant_api():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Send a JSON object with a question."}, 400
    question = payload.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return {"error": "Enter a question first."}, 400
    question = question.strip()[:1000]
    try:
        model = current_app.config.get("NVIDIA_NIM_MODEL", "meta/llama-3.2-11b-vision-instruct")
        api_key = current_app.config.get("NVIDIA_NIM_API_KEY", "")
        report_id = payload.get("report_id")
        if report_id is not None:
            try:
                report_id = int(report_id)
            except (TypeError, ValueError):
                return {"error": "Choose a valid saved report."}, 400
            with connection(current_app.config["DATABASE_PATH"]) as db:
                report = db.execute("SELECT title,content FROM reports WHERE id=? AND user_id=?",
                                    (report_id, session["user_id"])).fetchone()
            if not report:
                return {"error": "That report is not available in your account."}, 404
            answer = answer_report_question(question, report["title"], report["content"], api_key, model=model)
        else:
            answer = explain_symptom(question, api_key, model=model)
    except RuntimeError as exc:
        return {"error": str(exc)}, 503
    return {"answer": answer}


@reports_bp.get("/api/health-insights")
@login_required
def health_insights_api():
    start = request.args.get("from", "").strip()
    end = request.args.get("to", "").strip()
    for label, value in (("start date", start), ("end date", end)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                return {"error": f"Enter a valid {label}."}, 400
    if start and end and start > end:
        return {"error": "The start date must be on or before the end date."}, 400
    reports = _reports(session["user_id"])
    measurements = extract_biomarkers(reports)
    available = sorted({item["name"] for item in measurements}, key=str.casefold)
    name = request.args.get("biomarker", "").strip()[:60]
    filtered = [item for item in measurements
                if (not name or item["name"].casefold() == name.casefold())
                and (not start or item["date"] >= start)
                and (not end or item["date"] <= end)]
    return {"items": filtered, "biomarkers": available,
            "abnormal_count": sum(1 for item in filtered if item["abnormal"])}


@reports_bp.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    reports = _reports(session["user_id"])
    reports = sorted(reports, key=lambda report: (report["created_at"], report["id"]))
    result = None
    selected = []
    if request.method == "POST":
        try:
            ids = [int(request.form["first"]), int(request.form["second"])]
            owned = {r["id"]: r for r in reports}
            if ids[0] == ids[1] or any(i not in owned for i in ids):
                abort(404)
            result = compare_reports(owned[ids[0]]["content"], owned[ids[1]]["content"])
            result["first_title"] = owned[ids[0]]["title"]
            result["second_title"] = owned[ids[1]]["title"]
            result["measurements"] = extract_measurements(owned[ids[0]]["content"], owned[ids[1]]["content"])
            selected = ids
        except (ValueError, KeyError):
            flash("Select two different saved reports.", "error")
    return render_dashboard(reports=reports, page="compare", result=result, selected=selected)


@reports_bp.get("/history")
@login_required
def history():
    return render_dashboard(reports=_reports(session["user_id"]), page="history")


@reports_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        country = request.form.get("country", "India").strip()[:100] or "India"
        state = request.form.get("state", "").strip()[:100]
        area = request.form.get("area", "").strip()[:100]
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) or not state or not area:
            flash("Enter a valid international phone number, country, state, and area.", "error")
            user = {"email": session.get("email", ""), "phone": phone,
                    "country": country, "state": state, "area": area}
            return render_dashboard(reports=_reports(session["user_id"]), page="settings", user=user)
        with connection(current_app.config["DATABASE_PATH"]) as db:
            db.execute("UPDATE users SET phone=?,country=?,state=?,area=? WHERE id=?",
                       (phone, country, state, area, session["user_id"]))
        flash("Registration details updated.", "success")
    with connection(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT email,phone,country,state,area FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_dashboard(reports=_reports(session["user_id"]), page="settings", user=user)


@reports_bp.get("/reports/<int:report_id>")
@login_required
def view_report(report_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        report = db.execute("SELECT * FROM reports WHERE id=? AND user_id=?", (report_id, session["user_id"])).fetchone()
    if not report: abort(404)
    measurements = [item for item in extract_biomarkers([report])]
    return render_dashboard(reports=_reports(session["user_id"]), page="view", report=report,
                            measurements=measurements)


@reports_bp.post("/reports/<int:report_id>/explain")
@login_required
def explain_saved_report(report_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        report = db.execute("SELECT id,content,file_data,mime_type FROM reports WHERE id=? AND user_id=?",
                            (report_id, session["user_id"])).fetchone()
    if not report:
        abort(404)
    try:
        model = current_app.config.get("NVIDIA_NIM_MODEL", "meta/llama-3.2-11b-vision-instruct")
        api_key = current_app.config.get("NVIDIA_NIM_API_KEY", "")
        if report["file_data"] and report["mime_type"]:
            explanation = explain_upload(bytes(report["file_data"]), report["mime_type"], api_key,
                                         model=model, extracted_text=report["content"])
        elif report["content"] and not report["content"].startswith("Text could not be extracted"):
            explanation = explain_saved_text(report["content"], api_key, model=model)
        else:
            flash("This older report has no saved file or extractable text to explain. Upload it again to request an explanation.", "error")
            return redirect(url_for("reports.view_report", report_id=report_id))
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("reports.view_report", report_id=report_id))
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("UPDATE reports SET explanation=? WHERE id=? AND user_id=?",
                   (explanation, report_id, session["user_id"]))
    flash("English and Telugu explanation saved with your report.", "success")
    return redirect(url_for("reports.view_report", report_id=report_id))


@reports_bp.post("/reports/<int:report_id>/delete")
@login_required
def delete_report(report_id):
    with connection(current_app.config["DATABASE_PATH"]) as db:
        db.execute("DELETE FROM reports WHERE id=? AND user_id=?", (report_id, session["user_id"]))
    flash("Report deleted.", "success")
    return redirect(url_for("reports.history"))


@reports_bp.post("/reports")
@login_required
def add_report():
    title = request.form.get("title", "").strip()[:100]
    content = request.form.get("content", "").strip()[:20000]
    if not title or not content:
        flash("A title and report text are required.", "error")
    else:
        with connection(current_app.config["DATABASE_PATH"]) as db:
            db.execute("INSERT INTO reports(user_id,title,content) VALUES(?,?,?)", (session["user_id"], title, content))
        flash("Report saved.", "success")
    return redirect(url_for("reports.history"))
