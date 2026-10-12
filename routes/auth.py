import hashlib
import secrets
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import connection
from routes.react_view import render_react_page

auth_bp = Blueprint("auth", __name__)
RESET_MESSAGE = "If that email belongs to a password-enabled account and email delivery is configured, a password reset link will be sent shortly."


def _send_password_reset(email, token):
    config = current_app.config
    required = ("MAIL_SERVER", "MAIL_DEFAULT_SENDER")
    if not all(config.get(key) for key in required):
        current_app.logger.error("Password reset email is not configured; set MAIL_SERVER and MAIL_DEFAULT_SENDER.")
        return False
    base_url = config.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base_url:
        current_app.logger.error("Password reset email is not configured; set PUBLIC_BASE_URL.")
        return False
    reset_url = f"{base_url}{url_for('auth.reset_password', token=token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your Healthcare password"
    message["From"] = config["MAIL_DEFAULT_SENDER"]
    message["To"] = email
    message.set_content(
        "We received a request to reset the password for your Healthcare account.\n\n"
        f"Use this link within 60 minutes to choose a new password:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    try:
        with smtplib.SMTP(config["MAIL_SERVER"], config.get("MAIL_PORT", 587), timeout=10) as server:
            if config.get("MAIL_USE_TLS", True):
                server.starttls()
            if config.get("MAIL_USERNAME"):
                server.login(config["MAIL_USERNAME"], config.get("MAIL_PASSWORD", ""))
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        current_app.logger.exception("Could not send a Healthcare password reset email.")
        return False


def _reset_token_record(token, db):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return db.execute(
        """SELECT id,user_id FROM password_reset_tokens
           WHERE token_hash=? AND used_at='' AND expires_at>?""",
        (token_hash, datetime.now(timezone.utc).isoformat()),
    ).fetchone(), token_hash


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()[:254]
        if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            now = datetime.now(timezone.utc)
            with connection(current_app.config["DATABASE_PATH"]) as db:
                user = db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
                if user:
                    recent = db.execute(
                        "SELECT created_at FROM password_reset_tokens WHERE user_id=? ORDER BY id DESC LIMIT 1",
                        (user["id"],),
                    ).fetchone()
                    last_sent = datetime.fromisoformat(recent["created_at"]) if recent else None
                    if not last_sent or now - last_sent >= timedelta(minutes=1):
                        token = secrets.token_urlsafe(32)
                        db.execute("DELETE FROM password_reset_tokens WHERE user_id=? AND used_at=''", (user["id"],))
                        db.execute(
                            """INSERT INTO password_reset_tokens(user_id,token_hash,created_at,expires_at)
                               VALUES(?,?,?,?)""",
                            (user["id"], hashlib.sha256(token.encode("utf-8")).hexdigest(),
                             now.isoformat(), (now + timedelta(minutes=60)).isoformat()),
                        )
                    else:
                        token = ""
            if user and token:
                _send_password_reset(email, token)
        flash(RESET_MESSAGE, "success")
        return redirect(url_for("auth.forgot_password"))
    return render_react_page("forgot_password")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if len(token) > 200:
        return render_react_page("reset_password", token="", valid=False)
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        if len(password) < 10 or len(password) > 128:
            flash("Use a password between 10 and 128 characters.", "error")
        elif password != confirmation:
            flash("The password entries do not match.", "error")
        else:
            now = datetime.now(timezone.utc).isoformat()
            with connection(current_app.config["DATABASE_PATH"]) as db:
                record, token_hash = _reset_token_record(token, db)
                if record:
                    consumed = db.execute(
                        "UPDATE password_reset_tokens SET used_at=? WHERE id=? AND used_at=''",
                        (now, record["id"]),
                    )
                    if consumed.rowcount:
                        db.execute("UPDATE users SET password_hash=? WHERE id=?",
                                   (generate_password_hash(password), record["user_id"]))
                        db.execute("DELETE FROM password_reset_tokens WHERE user_id=? AND id<>?",
                                   (record["user_id"], record["id"]))
                        session.clear()
                        flash("Your password has been reset. You can now sign in.", "success")
                        return redirect(url_for("index"))
            flash("This password reset link is invalid or has expired. Request a new link.", "error")
            return render_react_page("reset_password", token="", valid=False)
    with connection(current_app.config["DATABASE_PATH"]) as db:
        record, _token_hash = _reset_token_record(token, db)
    return render_react_page("reset_password", token=token, valid=bool(record))


@auth_bp.post("/register")
def register():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    phone = request.form.get("phone", "").strip()
    state = request.form.get("state", "").strip()[:100]
    area = request.form.get("area", "").strip()[:100]
    country = request.form.get("country", "India").strip()[:100] or "India"
    if not email or len(password) < 10 or not state or not area:
        flash("Enter an email, a password with at least 10 characters, your state, and your area.", "error")
        return redirect(url_for("index"))
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
        flash("Enter your phone in international format, for example +919876543210.", "error")
        return redirect(url_for("index"))
    try:
        with connection(current_app.config["DATABASE_PATH"]) as db:
            cursor = db.execute(
                "INSERT INTO users (email, password_hash, phone, state, area, country) VALUES (?, ?, ?, ?, ?, ?)",
                (email, generate_password_hash(password), phone, state, area, country),
            )
            session.clear()
            session["user_id"] = cursor.lastrowid
            session["email"] = email
    except Exception:
        flash("That account could not be created. The email may already be registered.", "error")
        return redirect(url_for("index"))
    return redirect(url_for("reports.dashboard"))


@auth_bp.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    with connection(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], request.form.get("password", "")):
        flash("Invalid email or password.", "error")
        return redirect(url_for("index"))
    session.clear()
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return redirect(url_for("reports.dashboard"))


def get_firebase_admin_app():
    import firebase_admin
    from firebase_admin import credentials

    project_id = current_app.config["FIREBASE_PROJECT_ID"]
    if not project_id:
        raise RuntimeError("Firebase project is not configured")
    try:
        return firebase_admin.get_app()
    except ValueError:
        credential_file = current_app.config["FIREBASE_SERVICE_ACCOUNT_FILE"]
        credential = credentials.Certificate(credential_file) if credential_file else credentials.ApplicationDefault()
        return firebase_admin.initialize_app(credential, {"projectId": project_id})


@auth_bp.post("/google")
def google_login():
    from firebase_admin import auth as firebase_auth

    id_token = (request.get_json(silent=True) or {}).get("idToken", "")
    if not id_token:
        return jsonify(error="Google sign-in token is missing."), 400
    try:
        firebase_app = get_firebase_admin_app()
        claims = firebase_auth.verify_id_token(id_token, app=firebase_app)
    except Exception:
        current_app.logger.exception("Firebase ID token verification failed")
        return jsonify(error="Google sign-in could not be verified. Check Firebase server configuration."), 401

    email = (claims.get("email") or "").strip().lower()
    provider = claims.get("firebase", {}).get("sign_in_provider")
    if not email or claims.get("email_verified") is not True or provider != "google.com":
        return jsonify(error="Use a verified Google account to sign in."), 403

    firebase_uid = claims.get("uid")
    if not firebase_uid:
        return jsonify(error="Google account ID is missing."), 403

    with connection(current_app.config["DATABASE_PATH"]) as db:
        user = db.execute("SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid,)).fetchone()
        if user and user["email"].lower() != email:
            return jsonify(error="This Google account is linked to a different email."), 403
        if not user:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and user["firebase_uid"] and user["firebase_uid"] != firebase_uid:
                return jsonify(error="This email is already linked to another Google account."), 409
            if user:
                # Verified Firebase email allows the user to link an existing local account.
                db.execute("UPDATE users SET firebase_uid = ? WHERE id = ?", (firebase_uid, user["id"]))
                user_id = user["id"]
            else:
                cursor = db.execute(
                    "INSERT INTO users (email, password_hash, firebase_uid) VALUES (?, ?, ?)",
                    (email, generate_password_hash(secrets.token_urlsafe(32)), firebase_uid),
                )
                user_id = cursor.lastrowid
        else:
            user_id = user["id"]
        profile = db.execute("SELECT phone, state, area FROM users WHERE id = ?", (user_id,)).fetchone()
        needs_profile = not (profile["phone"] and profile["state"] and profile["area"])

    session.clear()
    session["user_id"] = user_id
    session["email"] = email
    if needs_profile:
        session["profile_required"] = True
    return jsonify(ok=True, needsProfile=needs_profile)


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
