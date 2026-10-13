"""Flask-to-React page bootstrap helpers."""
from collections.abc import Mapping
from datetime import date, datetime

from flask import get_flashed_messages, render_template, session, url_for


def _json_value(value):
    if isinstance(value, Mapping) or hasattr(value, "keys"):
        return {key: _json_value(value[key]) for key in value.keys() if key != "file_data"}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return value


def common_urls():
    return {
        "dashboard": url_for("reports.welcome"), "upload": url_for("reports.upload"),
        "insights": url_for("reports.health_insights_page"),
        "wellnessPage": url_for("reports.wellness_page"),
        "medicationsPage": url_for("reports.medications_page"),
        "explanation": url_for("reports.explanation"), "compare": url_for("reports.compare"),
        "history": url_for("reports.history"), "settings": url_for("reports.settings"),
        "appointments": url_for("appointments.directory"), "logout": url_for("auth.logout"),
        "login": url_for("auth.login"), "register": url_for("auth.register"),
        "profile": url_for("reports.complete_profile"),
        "google": url_for("auth.google_login"),
        "states": url_for("appointments.api_states"), "districts": url_for("appointments.api_districts"),
        "cities": url_for("appointments.api_cities"), "hospitals": url_for("appointments.api_hospitals"),
        "doctors": url_for("appointments.api_doctors", hospital_id=0),
        "doctorDirectory": url_for("appointments.api_doctor_directory"),
        "book": url_for("appointments.book_demo_appointment"),
        "wellness": url_for("reports.save_wellness"), "medication": url_for("reports.add_medication"),
        "deleteMedication": url_for("reports.delete_medication", medication_id=0),
        "aiIdeas": url_for("reports.generate_wellness_suggestions"),
        "assistant": url_for("reports.assistant_api"),
        "healthInsights": url_for("reports.health_insights_api"),
        "viewReport": url_for("reports.view_report", report_id=0),
        "deleteReport": url_for("reports.delete_report", report_id=0),
        "explainReport": url_for("reports.explain_saved_report", report_id=0),
        "directoryUpload": url_for("appointments.upload_directory"),
        "directoryTemplate": url_for("appointments.directory_template"),
        "doctorUpload": url_for("appointments.upload_doctors"),
        "doctorTemplate": url_for("appointments.doctors_template"),
    }


def render_react_page(view, **context):
    props = _json_value(context)
    props.update(view=view, email=session.get("email", ""), urls=common_urls(),
                 flashes=get_flashed_messages(with_categories=True))
    return render_template("react.html", react_props=props)


def render_dashboard(**context):
    context.setdefault("page", "dashboard")
    return render_react_page("dashboard", **context)
