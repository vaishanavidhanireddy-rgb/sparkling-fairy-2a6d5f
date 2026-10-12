"""Healthcare patient dashboard Flask application.

This application is an educational prototype. It is not a medical device and
does not provide diagnosis or treatment recommendations.
"""
import os
import secrets
from pathlib import Path

from flask import Flask, redirect, render_template, session, url_for, jsonify, request

from database.models import init_db
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


def create_app():
    load_local_env()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        HOST=os.environ.get("HOST", "0.0.0.1"),
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_ANON_KEY=os.environ.get("SUPABASE_ANON_KEY", ""),
        MISTRAL_API_KEY=os.environ.get("MISTRAL_API_KEY", ""),
        MISTRAL_MODEL=os.environ.get("MISTRAL_MODEL", "ministral-14b-latest"),
        MAIL_SERVER=os.environ.get("MAIL_SERVER", ""),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "0") == "1",
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", ""),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", ""),
        PUBLIC_BASE_URL=os.environ.get("PUBLIC_BASE_URL", "").rstrip("/"),
        HOSPITAL_ADMIN_EMAILS={email.strip().casefold() for email in os.environ.get("HOSPITAL_ADMIN_EMAILS", "").split(",") if email.strip()},
        MAIL_VERIFICATION_ENABLED=os.environ.get("MAIL_VERIFICATION_ENABLED", "0") == "1",
        MAIL_OTP_ENABLED=os.environ.get("MAIL_OTP_ENABLED", "0") == "1",
        FIREBASE_AUTH_DOMAIN=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        FIREBASE_PROJECT_ID=os.environ.get("FIREBASE_PROJECT_ID", ""),
        FIREBASE_APP_ID=os.environ.get("FIREBASE_APP_ID", ""),
        FIREBASE_MESSAGING_SENDER_ID=os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
        FIREBASE_STORAGE_BUCKET=os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
        FIREBASE_SERVICE_ACCOUNT_FILE=os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", ""),
        DATABASE_PATH=str(Path(__file__).parent / "quantum_healthcare.sqlite3"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1")
    init_db(app.config["DATABASE_PATH"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(appointments_bp)

    # Supabase authentication middleware
    @app.before_request
    def supabase_auth():
        """Verify Supabase JWT token and set session user if valid."""
        if request.endpoint and ("static" in request.endpoint or "auth" in request.endpoint):
            return None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                import httpx
                supabase_url = app.config.get("SUPABASE_URL", "")
                supabase_anon_key = app.config.get("SUPABASE_ANON_KEY", "")
                if supabase_url and supabase_anon_key:
                    headers = {"Authorization": f"Bearer {supabase_anon_key}"}
                    resp = httpx.get(
                        f"{supabase_url}/rest/v1/users",
                        headers=headers,
                        params={"select": "id,email"},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        user_data = resp.json()
                        if user_data:
                            session["user_id"] = user_data[0].get("id")
                            session["email"] = user_data[0].get("email")
            except Exception:
                pass
        if not session.get("user_id"):
            # Allow public routes
            public_routes = ["index", "auth.login", "auth.register", "auth.forgot_password",
                           "auth.reset_password", "static"]
            if request.endpoint not in public_routes:
                return redirect(url_for("index"))

    @app.after_request
    def add_cors_headers(response):
        """Add CORS headers for Vercel frontend."""
        origin = request.headers.get("Origin", "")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.get("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("reports.dashboard"))
        return render_react_page("landing")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], debug=False)
