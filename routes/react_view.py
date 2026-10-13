"""Flask-to-React page bootstrap helpers."""
import os
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from flask import Response, get_flashed_messages, session, url_for
from jinja2.utils import htmlsafe_json_dumps


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
        "dashboard": url_for("reports.dashboard"), "upload": url_for("reports.upload"),
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


DIST_INDEX = Path(__file__).resolve().parents[1] / "dist" / "index.html"
FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">'
)
# Matches what @vitejs/plugin-react injects when Vite itself serves index.html.
VITE_DEV_HEAD = (
    '<script type="module">import RefreshRuntime from "/@react-refresh";'
    "RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};"
    "window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;</script>"
    '<script type="module" src="/@vite/client"></script>'
)


def _page_shell():
    if os.environ.get("VITE_DEV") == "1" or not DIST_INDEX.is_file():
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Healthcare</title>{FONT_LINKS}{VITE_DEV_HEAD}</head>"
            '<body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>'
        )
    return DIST_INDEX.read_text(encoding="utf-8").replace('src="./assets/', 'src="/assets/').replace('href="./assets/', 'href="/assets/')


def render_react_page(view, **context):
    props = _json_value(context)
    props.update(view=view, email=session.get("email", ""), urls=common_urls(),
                 flashes=get_flashed_messages(with_categories=True))
    bootstrap = f"<script>window.CARECONNECT = {htmlsafe_json_dumps(props)};</script>"
    html = _page_shell().replace('<div id="root"></div>', f'<div id="root"></div>{bootstrap}', 1)
    return Response(html, mimetype="text/html")


def render_dashboard(**context):
    context.setdefault("page", "dashboard")
    return render_react_page("dashboard", **context)
