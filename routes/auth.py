import secrets
import re

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import connection

auth_bp = Blueprint("auth", __name__)


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
