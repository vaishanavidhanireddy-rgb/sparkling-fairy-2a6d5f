"""Quantum Healthcare demo application.

This application is an educational prototype. It is not a medical device and
does not provide diagnosis or treatment recommendations.
"""
import os
from pathlib import Path

from flask import Flask, redirect, render_template, session, url_for

from database.models import init_db
from routes.auth import auth_bp
from routes.quantum import quantum_bp
from routes.reports import reports_bp
from routes.hospitals import hospitals_bp


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


def create_app():
    load_local_env()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        HOST=os.environ.get("HOST", "127.0.0.1"),
        TWILIO_ACCOUNT_SID=os.environ.get("TWILIO_ACCOUNT_SID", ""),
        TWILIO_AUTH_TOKEN=os.environ.get("TWILIO_AUTH_TOKEN", ""),
        TWILIO_PHONE_NUMBER=os.environ.get("TWILIO_PHONE_NUMBER", ""),
        FIREBASE_API_KEY=os.environ.get("FIREBASE_API_KEY", ""),
        GEMINI_API_KEY=os.environ.get("GEMINI_API_KEY", ""),
        GROQ_API_KEY=os.environ.get("GROQ_API_KEY", ""),
        FIREBASE_AUTH_DOMAIN=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        FIREBASE_PROJECT_ID=os.environ.get("FIREBASE_PROJECT_ID", ""),
        FIREBASE_APP_ID=os.environ.get("FIREBASE_APP_ID", ""),
        FIREBASE_MESSAGING_SENDER_ID=os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
        FIREBASE_STORAGE_BUCKET=os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
        FIREBASE_SERVICE_ACCOUNT_FILE=os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", ""),
        HOSPITAL_ADMIN_KEY=os.environ.get("HOSPITAL_ADMIN_KEY", ""),
        DATABASE_PATH=str(Path(__file__).parent / "quantum_healthcare.sqlite3"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    init_db(app.config["DATABASE_PATH"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(quantum_bp)
    app.register_blueprint(hospitals_bp)

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
        return render_template("index.html", firebase_config=firebase_config)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], debug=False)
