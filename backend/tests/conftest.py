import re
import uuid
from pathlib import Path
import pytest
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from app import create_app
from app.config import settings
from app.extensions import db, mail
from app.models import User


@pytest.fixture(scope="session")
def app():
    config = settings("testing")
    url = make_url(config["SQLALCHEMY_DATABASE_URI"])
    name = "geopadrones_test_" + uuid.uuid4().hex[:12]
    try:
        admin = psycopg.connect(
            host=url.host,
            port=url.port or 5432,
            dbname="postgres",
            user=url.username,
            password=url.password,
            connect_timeout=5,
            autocommit=True,
        )
    except psycopg.Error:
        pytest.fail("PostGIS local no disponible. Inicie los servicios de docker-compose.dev.yml.")
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": url.set(database=name).render_as_string(hide_password=False),
            "STORAGE_BACKEND": "local",
            "WTF_CSRF_ENABLED": True,
        },
    )
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parents[1] / "migrations"))
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    admin.close()


@pytest.fixture
def context(app):
    with app.app_context():
        # Only tables in this freshly-created, randomly-named test DB are touched.
        names = ",".join('"' + table.name + '"' for table in db.metadata.sorted_tables)
        db.session.execute(db.text("TRUNCATE " + names + " CASCADE"))
        db.session.commit()
        yield app
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def client(context):
    return context.test_client()


def post(client, path, data=None, method="post", **kwargs):
    csrf = client.get("/api/v1/auth/csrf").json["csrf_token"]
    headers = {"X-CSRFToken": csrf, **kwargs.pop("headers", {})}
    return getattr(client, method)("/api/v1" + path, json=data, headers=headers, **kwargs)


def login(client, role="superadmin"):
    user = User(email=f"{role}@example.org", name="Usuario de prueba", role=role)
    user.set_password("Test-only-password-2026")
    db.session.add(user)
    db.session.commit()
    with mail.record_messages() as messages:
        response = post(
            client,
            "/auth/login",
            {"email": user.email, "password": "Test-only-password-2026", **captcha_payload(client)},
        )
        assert response.status_code == 200
        code = re.search(r"\b\d{6}\b", messages[-1].body).group()
    assert post(client, "/auth/2fa/verify", {"code": code}).status_code == 200
    return user


def captcha_payload(client):
    challenge = client.get("/api/v1/auth/captcha").json
    left, right = map(int, challenge["question"].split(" + "))
    return {"captcha_id": challenge["id"], "captcha_answer": str(left + right)}
