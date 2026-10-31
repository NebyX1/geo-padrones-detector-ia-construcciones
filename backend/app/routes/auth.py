import hashlib
import hmac
import secrets
from datetime import timedelta
from flask import Blueprint, abort, current_app, jsonify, request, session, g
from flask_login import current_user, login_user, logout_user
from flask_mail import Message
from flask_wtf.csrf import generate_csrf
from sqlalchemy import select, update
from ..extensions import db, limiter, mail
from ..models import User, AuthChallenge, utcnow, uid, ph
from ..schemas import LoginSchema, load
from ..utils.security import require, audit

bp = Blueprint("auth", __name__)
DUMMY_HASH = ph.hash(secrets.token_urlsafe(32))


def code_hash(challenge_id, code):
    return hmac.new(
        current_app.secret_key.encode(), f"{challenge_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def issue_challenge(user, purpose):
    db.session.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.user_id == user.id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=utcnow())
    )
    identifier = uid()
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = AuthChallenge(
        id=identifier,
        user_id=user.id,
        purpose=purpose,
        code_hash=code_hash(identifier, code),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db.session.add(challenge)
    # Never print codes. Tests use Flask-Mail recording; development uses Mailpit.
    try:
        reset_link = (
            f"{current_app.config['FRONTEND_URL'].rstrip('/')}/?reset={identifier}"
            if purpose == "reset"
            else None
        )
        body = f"Su código es {code}. Vence en 10 minutos. No lo comparta."
        if reset_link:
            body += f"\nRestablecer acceso: {reset_link}"
        mail.send(
            Message(
                "GeoPadrones · Código de verificación",
                recipients=[user.email],
                body=body,
            )
        )
    except Exception:
        db.session.rollback()
        abort(503, "No se pudo entregar el correo. Revise la configuración SMTP.")
    return challenge


def consume_challenge(identifier, code, purpose):
    challenge = db.session.execute(
        select(AuthChallenge).where(AuthChallenge.id == identifier).with_for_update()
    ).scalar_one_or_none()
    if (
        not challenge
        or challenge.purpose != purpose
        or challenge.consumed_at
        or challenge.expires_at <= utcnow()
        or challenge.attempts >= 5
    ):
        abort(422, "Código inválido, bloqueado o vencido.")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, code_hash(challenge.id, code)):
        db.session.commit()
        abort(422, "Código inválido, bloqueado o vencido.")
    challenge.consumed_at = utcnow()
    user = db.session.get(User, challenge.user_id)
    if not user or not user.is_active:
        abort(401)
    return user


@bp.get("/auth/csrf")
def csrf_token():
    g.pop("csrf_token", None)
    return jsonify(csrf_token=generate_csrf())


@bp.post("/auth/login")
@limiter.limit("5 per minute; 30 per hour")
def login():
    data = load(LoginSchema(), request.get_json())
    user = db.session.execute(
        select(User).where(User.email == data["email"].strip().lower())
    ).scalar_one_or_none()
    valid = user.check_password(data["password"]) if user else False
    if not user:
        try:
            ph.verify(DUMMY_HASH, data["password"])
        except Exception:
            pass
    if not valid or not user.is_active:
        audit("LOGIN_FAILED")
        db.session.commit()
        abort(401, "Correo o contraseña inválidos.")
    challenge = issue_challenge(user, "login")
    session.clear()
    session["challenge_id"] = challenge.id
    audit("LOGIN_CHALLENGE", user_id=user.id)
    db.session.commit()
    return jsonify(requires_2fa=True)


@bp.post("/auth/2fa/verify")
@limiter.limit("10 per minute")
def verify():
    data = request.get_json() or {}
    code = str(data.get("code", ""))
    if not code.isdigit() or len(code) != 6:
        abort(422, "Ingrese seis dígitos.")
    user = consume_challenge(session.get("challenge_id"), code, "login")
    session.clear()
    login_user(user, remember=False, fresh=True)
    session.permanent = True
    session["session_version"] = user.session_version
    user.last_login_at = utcnow()
    audit("LOGIN", user_id=user.id)
    db.session.commit()
    return jsonify(user=user.public(), csrf_token=generate_csrf())


@bp.get("/auth/me")
@require("read")
def me():
    return jsonify(user=current_user.public())


@bp.post("/auth/logout")
@require("read")
def logout():
    audit("LOGOUT")
    db.session.commit()
    logout_user()
    session.clear()
    return jsonify(message="Sesión cerrada.")


@bp.post("/auth/password/forgot")
@limiter.limit("3 per hour")
def forgot():
    email = str((request.get_json() or {}).get("email", "")).strip().lower()
    user = db.session.execute(
        select(User).where(User.email == email, User.is_active.is_(True))
    ).scalar_one_or_none()
    # Return an opaque random identifier in both cases; no account enumeration.
    identifier = uid()
    if user:
        identifier = issue_challenge(user, "reset").id
        audit("PASSWORD_RESET_REQUEST", user_id=user.id)
        db.session.commit()
    return jsonify(challenge_id=identifier, message="Si la cuenta existe recibirá un código.")


@bp.post("/auth/password/reset")
@limiter.limit("10 per minute")
def reset():
    data = request.get_json() or {}
    password = str(data.get("password", ""))
    if len(password) < 12 or len(password) > 256:
        abort(422, "La contraseña debe tener entre 12 y 256 caracteres.")
    user = consume_challenge(data.get("challenge_id"), str(data.get("code", "")), "reset")
    user.set_password(password)
    user.session_version += 1
    audit("PASSWORD_RESET", user_id=user.id)
    db.session.commit()
    session.clear()
    return jsonify(message="Contraseña actualizada. Inicie sesión.")


@bp.post("/auth/password/change")
@require("read")
def change_password():
    data = request.get_json() or {}
    password = str(data.get("password", ""))
    if (
        not current_user.check_password(str(data.get("current_password", "")))
        or not 12 <= len(password) <= 256
    ):
        abort(422, "Verifique su contraseña actual y use al menos 12 caracteres.")
    current_user.set_password(password)
    current_user.session_version += 1
    session["session_version"] = current_user.session_version
    audit("PASSWORD_CHANGE")
    db.session.commit()
    return jsonify(message="Contraseña actualizada; otras sesiones revocadas.")
