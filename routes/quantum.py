from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from database.models import connection
from quantum.quantum_model import analyze
from routes.reports import login_required
from security.consent import has_analysis_consent

quantum_bp = Blueprint("quantum", __name__)


@quantum_bp.route("/analysis", methods=["GET", "POST"])
@login_required
def analysis():
    result = None
    with connection(current_app.config["DATABASE_PATH"]) as db:
        consent = has_analysis_consent(db, session["user_id"])
        reports = db.execute("SELECT id, title, content FROM reports WHERE user_id = ? ORDER BY id DESC",
                             (session["user_id"],)).fetchall()
    if request.method == "POST" and consent:
        try:
            first_id, second_id = int(request.form["first"]), int(request.form["second"])
            items = {row["id"]: row for row in reports}
            if first_id != second_id and first_id in items and second_id in items:
                result = analyze(items[first_id]["content"], items[second_id]["content"])
        except (ValueError, KeyError):
            pass
        except Exception:
            current_app.logger.exception("Quantum report simulation failed")
            flash("Quantum simulation failed. Install the latest requirements and try again.", "error")
    return render_template("analysis.html", reports=reports, result=result, consent=consent)
