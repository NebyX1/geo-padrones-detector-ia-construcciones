"""Reversible local preview. Authentication code and normal RBAC remain intact."""

import secrets
from urllib.parse import urlsplit
from flask import current_app, g
from sqlalchemy import select, text
from ..auth_constants import LOCAL_PREVIEW_USER_ID, LOCAL_PREVIEW_EMAIL
from ..extensions import db
from ..models import User, AuditLog


def local_preview_allowed(request):
    config = current_app.config
    if not config.get("DEV_AUTH_BYPASS") or not config.get("DEVELOPMENT") or config["PRODUCTION"]:
        return False
    if urlsplit(request.host_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    # Real login, captcha, recovery and 2FA always run their original security checks.
    if request.path.startswith("/api/v1/auth/") and request.path != "/api/v1/auth/me":
        return False
    return True


def load_local_preview(request):
    if not local_preview_allowed(request):
        return None
    db.session.execute(text("SELECT pg_advisory_xact_lock(805384)"))
    user = db.session.get(User, LOCAL_PREVIEW_USER_ID)
    if user is None:
        if db.session.scalar(select(User.id).where(User.email == LOCAL_PREVIEW_EMAIL)):
            raise RuntimeError("La identidad técnica local está ocupada por otra cuenta.")
        user = User(
            id=LOCAL_PREVIEW_USER_ID,
            email=LOCAL_PREVIEW_EMAIL,
            name="Pruebas locales sin autenticación",
            role="superadmin",
        )
        user.set_password(secrets.token_urlsafe(64))  # No usable/default password is retained or displayed.
        db.session.add(user)
        db.session.flush()
        db.session.add(
            AuditLog(
                user_id=user.id,
                action="LOCAL_PREVIEW_PRINCIPAL_CREATED",
                details={"local_preview": True},
                request_id=getattr(g, "request_id", None),
            )
        )
    if user.email != LOCAL_PREVIEW_EMAIL or not user.is_active or user.role != "superadmin":
        raise RuntimeError("La identidad técnica local fue modificada; revise la configuración.")
    db.session.commit()
    g.local_preview = True
    return user
