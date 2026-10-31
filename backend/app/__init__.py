import json
import logging
import time
import uuid
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_wtf.csrf import CSRFError
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from .config import settings
from .extensions import db, migrate, login_manager, csrf, limiter, talisman, mail

requests_metric = Counter("geopadrones_requests", "HTTP requests", ["method", "endpoint", "status"])
duration_metric = Histogram("geopadrones_request_seconds", "HTTP latency", ["endpoint"])


def create_app(config_name=None, overrides=None):
    import os

    app = Flask(__name__)
    app.config.update(settings(config_name or os.getenv("FLASK_CONFIG", "development")))
    app.config.update(overrides or {})
    if app.config["DEV_AUTH_BYPASS"] and (app.config["PRODUCTION"] or not app.config["DEVELOPMENT"]):
        raise RuntimeError("El acceso sin autenticación solo está permitido en desarrollo local.")
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    db.init_app(app)
    if app.config["PRODUCTION"]:
        with app.app_context():
            try:
                privileged = db.session.execute(
                    db.text(
                        "SELECT rolsuper OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname=current_user"
                    )
                ).scalar()
                if privileged:
                    raise RuntimeError(
                        "Producción requiere un rol PostgreSQL sin SUPERUSER, CREATEROLE ni CREATEDB. Configure DATABASE_APP_USER/PASSWORD."
                    )
            finally:
                db.session.remove()
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}}, supports_credentials=True)

    @app.before_request
    def correlation():
        g.started = time.monotonic()
        try:
            g.request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            g.request_id = str(uuid.uuid4())

    csrf.init_app(app)
    talisman.init_app(
        app,
        force_https=app.config["PRODUCTION"],
        session_cookie_secure=app.config["PRODUCTION"],
        content_security_policy={"default-src": "'none'", "frame-ancestors": "'none'"},
    )

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        from .auth_constants import LOCAL_PREVIEW_USER_ID

        if user_id == LOCAL_PREVIEW_USER_ID:
            return None

        user = db.session.get(User, user_id)
        return user if user and user.is_active else None

    @login_manager.request_loader
    def local_preview_user(incoming_request):
        from .services.local_preview import load_local_preview

        return load_local_preview(incoming_request)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(
            error={"code": exc.name, "message": exc.description, "request_id": getattr(g, "request_id", None)}
        ), exc.code

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        return jsonify(
            error={
                "code": "CSRF",
                "message": "Token CSRF ausente o vencido.",
                "request_id": getattr(g, "request_id", None),
            }
        ), 400

    @app.errorhandler(ValidationError)
    def validation_error(exc):
        return jsonify(
            error={
                "code": "VALIDATION",
                "message": "Revise los datos enviados.",
                "fields": exc.messages,
                "request_id": getattr(g, "request_id", None),
            }
        ), 422

    @app.errorhandler(IntegrityError)
    def conflict(exc):
        db.session.rollback()
        return jsonify(
            error={
                "code": "CONFLICT",
                "message": "El registro ya existe o cambió; actualice e intente nuevamente.",
                "request_id": getattr(g, "request_id", None),
            }
        ), 409

    @app.errorhandler(Exception)
    def unexpected(exc):
        if app.testing:
            raise exc
        db.session.rollback()
        # No payload, credentials, OTPs, raw SQL or exception messages in logs.
        app.logger.error(
            json.dumps(
                {
                    "event": "request_error",
                    "type": type(exc).__name__,
                    "request_id": getattr(g, "request_id", None),
                }
            )
        )
        return jsonify(
            error={
                "code": "INTERNAL",
                "message": "Error interno. Consulte el identificador de solicitud.",
                "request_id": getattr(g, "request_id", None),
            }
        ), 500

    @app.after_request
    def finish(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["Cache-Control"] = "no-store"
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        requests_metric.labels(request.method, endpoint, response.status_code).inc()
        duration_metric.labels(endpoint).observe(time.monotonic() - getattr(g, "started", time.monotonic()))
        return response

    from .routes.auth import bp as auth
    from .routes.cadastre import bp as cadastre
    from .routes.workflow import bp as workflow
    from .routes.admin import bp as admin
    from .routes.preferences import bp as preferences
    from .routes.versions import bp as versions
    from .routes.reviews import bp as review_evidence
    from .routes.analytics import bp as analytics
    from .routes.bulk_analysis import bp as bulk_analysis
    from .cli import register_commands

    for blueprint in (
        auth,
        cadastre,
        workflow,
        admin,
        preferences,
        versions,
        review_evidence,
        analytics,
        bulk_analysis,
    ):
        app.register_blueprint(blueprint, url_prefix="/api/v1")
    register_commands(app)

    @app.get("/api/v1/health")
    @talisman(force_https=False)
    def health():
        return jsonify(status="ok", service="geopadrones", version="0.1.0")

    @app.get("/api/v1/health/ready")
    @talisman(force_https=False)
    def ready():
        from redis import Redis
        from .services.storage import storage

        checks = {}
        try:
            checks["postgis"] = bool(db.session.execute(db.text("SELECT PostGIS_Version()")).scalar())
        except SQLAlchemyError:
            db.session.rollback()
            checks["postgis"] = False
        try:
            checks["redis"] = Redis.from_url(app.config["REDIS_URL"], socket_timeout=2).ping()
        except Exception:
            checks["redis"] = False
        try:
            checks["storage"] = storage().healthy()
        except Exception:
            checks["storage"] = False
        return jsonify(status="ok" if all(checks.values()) else "degraded", checks=checks), 200 if all(
            checks.values()
        ) else 503

    @app.get("/api/v1/metrics")
    def metrics():
        from .utils.security import require

        return require("settings")(lambda: (generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}))()

    @app.get("/api/v1/openapi.json")
    def openapi():
        from pathlib import Path
        from .utils.security import require

        return require("read")(
            lambda: jsonify(json.loads((Path(app.root_path) / "openapi.json").read_text(encoding="utf-8")))
        )()

    return app
