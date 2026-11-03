from functools import wraps
from flask import abort, g, has_request_context, session
from flask_login import current_user
from ..extensions import db
from ..models import AuditLog

CAPABILITIES = {
    "superadmin": {"read", "analyze", "import", "export", "review", "users", "settings", "purge"},
    "admin": {"read", "analyze", "import", "export", "review", "users", "purge"},
    "analyst": {"read", "analyze", "import", "export"},
    "reviewer": {"read", "review"},
    "viewer": {"read"},
}


def require(capability):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_active:
                abort(401, "Inicie sesión para continuar.")
            from ..auth_constants import LOCAL_PREVIEW_USER_ID

            from ..services.local_preview import local_preview_allowed
            from flask import request

            preview = current_user.id == LOCAL_PREVIEW_USER_ID and local_preview_allowed(request)
            if current_user.id == LOCAL_PREVIEW_USER_ID and not preview:
                abort(401, "El acceso de prueba está desactivado. Inicie sesión.")
            if preview:
                g.local_preview = True
            if not preview and session.get("session_version") != current_user.session_version:
                session.clear()
                abort(401, "La sesión fue revocada. Inicie sesión nuevamente.")
            if capability not in CAPABILITIES.get(current_user.role, set()):
                abort(403, "Su rol no permite esta operación.")
            return fn(*args, **kwargs)

        return wrapped

    return decorate


def audit(action, entity_id=None, details=None, user_id=None):
    details = dict(details or {})
    if has_request_context() and getattr(g, "local_preview", False):
        details["local_preview"] = True
    db.session.add(
        AuditLog(
            action=action,
            entity_id=entity_id,
            details=details,
            user_id=user_id
            or (current_user.id if has_request_context() and current_user.is_authenticated else None),
            request_id=getattr(g, "request_id", None) if has_request_context() else None,
        )
    )
