"""Healthcare patient dashboard Flask application.

This application is an educational prototype. It is not a medical device and
does not provide diagnosis or treatment recommendations.
"""
import os
import secrets
from pathlib import Path

from flask import Flask, redirect, send_from_directory, session, url_for

from database.models import connection, init_db
from routes.auth import auth_bp
from routes.reports import reports_bp
from routes.appointments import appointments_bp
from routes.react_view import render_react_page


def load_local_env():
    """Load simple KEY=value settings from the project .env without overriding shell values."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        if name and name.replace("_", "").isalnum() and not os.environ.get(name):
            os.environ[name] = value


LOCATION_DATA = Path(__file__).parent / "data" / "appointments" / "hospital_finder_locations.json"


def seed_locations(database_path):
    """Load the bundled state/district/city list the first time the database is created."""
    if not LOCATION_DATA.is_file():
        return
    with connection(database_path) as db:
        if db.execute("SELECT 1 FROM appointment_states LIMIT 1").fetchone():
            return
    from scripts.import_hospital_finder_locations import import_locations
    import_locations(database_path, LOCATION_DATA)


def create_app():
    load_local_env()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        HOST=os.environ.get("HOST", "127.0.0.1"),
        FIREBASE_API_KEY=os.environ.get("FIREBASE_API_KEY", ""),
        MISTRAL_API_KEY=os.environ.get("MISTRAL_API_KEY", ""),
        MISTRAL_MODEL=os.environ.get("MISTRAL_MODEL", "ministral-14b-latest"),
        HOSPITAL_ADMIN_EMAILS={email.strip().casefold() for email in os.environ.get("HOSPITAL_ADMIN_EMAILS", "").split(",") if email.strip()},
        FIREBASE_AUTH_DOMAIN=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        FIREBASE_PROJECT_ID=os.environ.get("FIREBASE_PROJECT_ID", ""),
        FIREBASE_APP_ID=os.environ.get("FIREBASE_APP_ID", ""),
        FIREBASE_MESSAGING_SENDER_ID=os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
        FIREBASE_STORAGE_BUCKET=os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
        FIREBASE_SERVICE_ACCOUNT_FILE=os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", ""),
        DATABASE_PATH=os.environ.get("DATABASE_PATH") or str(
            Path("/tmp/quantum_healthcare.sqlite3") if os.environ.get("VERCEL")
            else Path(__file__).parent / "quantum_healthcare.sqlite3"
        ),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.config.update(SESSION_COOKIE_HTTPONLY=True,
                     SESSION_COOKIE_SAMESITE=os.environ.get("COOKIE_SAMESITE", "Lax"),
                     SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1" if os.environ.get("VERCEL") else "0") == "1")
    init_db(app.config["DATABASE_PATH"])
    seed_locations(app.config["DATABASE_PATH"])

    dist_assets = Path(__file__).parent / "dist" / "assets"

    @app.get("/assets/<path:filename>")
    def built_assets(filename):
        return send_from_directory(dist_assets, filename, max_age=31536000)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(appointments_bp)

    @app.get("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("reports.dashboard"))
        web_config_keys = ("FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_PROJECT_ID", "FIREBASE_APP_ID")
        firebase_config = None
        if all(app.config[key] for key in web_config_keys):
            firebase_config = {
                "apiKey": app.config["FIREBASE_API_KEY"],
                "authDomain": app.config["FIREBASE_AUTH_DOMAIN"],
                "projectId": app.config["FIREBASE_PROJECT_ID"],
                "appId": app.config["FIREBASE_APP_ID"],
                "messagingSenderId": app.config["FIREBASE_MESSAGING_SENDER_ID"],
                "storageBucket": app.config["FIREBASE_STORAGE_BUCKET"],
            }
        return render_react_page("landing", firebase=firebase_config)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], debug=False)
