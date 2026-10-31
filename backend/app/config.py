import os
from datetime import timedelta
from pathlib import Path


def settings(name):
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    testing = name == "testing"
    production = name == "production"
    secret = os.getenv("SECRET_KEY", "")
    if not secret and not testing:
        raise RuntimeError("Configure SECRET_KEY con un valor aleatorio privado de al menos 32 caracteres.")
    database = os.getenv("DATABASE_URL", "postgresql+psycopg://geopadrones:local@localhost:5432/geopadrones")
    database = database.replace("@localhost:", "@127.0.0.1:")
    if not database.startswith("postgresql"):
        raise RuntimeError("Esta aplicación requiere PostgreSQL/PostGIS.")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").replace("://localhost:", "://127.0.0.1:")
    if production and (len(secret) < 32 or "change" in secret.lower() or "example" in secret.lower()):
        raise RuntimeError("SECRET_KEY no es adecuado para producción.")
    origins = [v.strip() for v in os.getenv("CORS_ORIGINS", "").split(",") if v.strip()]
    if "*" in origins:
        raise RuntimeError("CORS no admite comodines con credenciales.")

    def local_path(value):
        path = Path(value)
        return (project_root / path).resolve() if not path.is_absolute() else path.resolve()

    base = local_path(os.getenv("DATA_DIR", "data/runtime"))
    return dict(
        TESTING=testing,
        DEBUG=False,
        PRODUCTION=production,
        SECRET_KEY=secret or "unit-tests-only-never-deploy",
        WTF_CSRF_SECRET_KEY=os.getenv("WTF_CSRF_SECRET_KEY") or secret or "unit-tests-csrf-only",
        SESSION_COOKIE_NAME="geopadrones_session",
        SQLALCHEMY_DATABASE_URI=database,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "connect_args": {"connect_timeout": 5}},
        REDIS_URL=redis_url,
        RATELIMIT_STORAGE_URI=redis_url if not testing else "memory://",
        RATELIMIT_ENABLED=not testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        WTF_CSRF_TIME_LIMIT=28800,
        WTF_CSRF_SSL_STRICT=production,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_SIZE", "10485760")),
        MAX_ANALYSIS_AREA=float(os.getenv("MAX_ANALYSIS_AREA", "100000")),
        MAX_ANALYSIS_PARCELS=int(os.getenv("MAX_ANALYSIS_PARCELS", "100")),
        MAX_RASTER_PIXELS=int(os.getenv("MAX_RASTER_PIXELS", "16000000")),
        MAX_STORAGE_BYTES=int(os.getenv("MAX_STORAGE_BYTES", "10737418240")),
        RQ_QUEUE=os.getenv("RQ_QUEUE", "geopadrones"),
        DATA_DIR=base,
        MODEL_DIR=local_path(os.getenv("MODEL_DIR", "data/models")),
        MODEL_DEVICE=os.getenv("MODEL_DEVICE", "cpu"),
        MINIO_ENDPOINT=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000").replace("localhost:", "127.0.0.1:"),
        MINIO_ACCESS_KEY=os.getenv("MINIO_ACCESS_KEY", ""),
        MINIO_SECRET_KEY=os.getenv("MINIO_SECRET_KEY", ""),
        MINIO_BUCKET=os.getenv("MINIO_BUCKET", "geopadrones"),
        MINIO_SECURE=os.getenv("MINIO_SECURE", "false").lower() == "true",
        STORAGE_BACKEND=os.getenv("STORAGE_BACKEND", "minio"),
        MAIL_SERVER="127.0.0.1"
        if os.getenv("MAIL_SERVER", "localhost") == "localhost"
        else os.getenv("MAIL_SERVER"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "1025")),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "false").lower() == "true",
        MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "false").lower() == "true",
        MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", "geopadrones@example.invalid"),
        MAIL_SUPPRESS_SEND=testing,
        CORS_ORIGINS=origins,
        FRONTEND_URL=os.getenv("FRONTEND_URL", "http://localhost:5173"),
        TRUST_PROXY=os.getenv("TRUST_PROXY", "false").lower() == "true",
    )
