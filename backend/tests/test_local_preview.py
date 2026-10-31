import pytest
from app import create_app
from app.config import settings
from app.auth_constants import LOCAL_PREVIEW_USER_ID, LOCAL_PREVIEW_EMAIL
from app.extensions import db, mail
from app.models import Job, User, AuditLog
from conftest import post

pytestmark = pytest.mark.integration


@pytest.fixture
def preview(context, monkeypatch):
    monkeypatch.setitem(context.config, "DEV_AUTH_BYPASS", True)
    monkeypatch.setitem(context.config, "DEVELOPMENT", True)
    return context


def test_local_entry_supports_real_jobs_and_audit_without_login(client, preview, monkeypatch):
    monkeypatch.setattr("app.routes.workflow.dispatch", lambda job: None)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json["user"]["is_local_preview"] is True
    assert client.get("/api/v1/parcels").status_code == 200
    assert client.get("/api/v1/users").json["items"] == []
    assert client.post("/api/v1/exports", json={"format": "csv"}).status_code == 400  # CSRF remains enforced.
    result = post(client, "/exports", {"format": "csv", "filters": {}})
    assert result.status_code == 202
    assert db.session.query(Job).one().user_id == LOCAL_PREVIEW_USER_ID
    entry = db.session.query(AuditLog).filter_by(action="EXPORT_REQUEST").one()
    assert entry.user_id == LOCAL_PREVIEW_USER_ID and entry.details["local_preview"] is True
    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_flag_off_restores_auth_and_no_preview_cookie_is_accepted(client, preview, monkeypatch):
    assert client.get("/api/v1/auth/me").status_code == 200
    monkeypatch.setitem(preview.config, "DEV_AUTH_BYPASS", False)
    assert client.get("/api/v1/parcels").status_code == 401
    with client.session_transaction() as session:
        session["_user_id"] = LOCAL_PREVIEW_USER_ID
        session["session_version"] = 1
    assert client.get("/api/v1/auth/me").status_code == 401


def test_preview_host_and_auth_endpoints_stay_guarded(client, preview):
    assert client.get("/api/v1/auth/me", base_url="http://example.com").status_code == 401
    assert (
        post(client, "/auth/login", {"email": "someone@example.org", "password": "whatever"}).status_code
        == 422
    )
    assert post(client, "/auth/2fa/verify", {"code": "123456"}).status_code == 422
    assert (
        post(
            client,
            "/auth/password/change",
            {"current_password": "anything", "password": "never-a-preview-password"},
        ).status_code
        == 401
    )


def test_technical_identity_cannot_be_changed_reset_or_replace_last_human_admin(client, preview):
    assert client.get("/api/v1/auth/me").status_code == 200
    assert (
        post(client, f"/users/{LOCAL_PREVIEW_USER_ID}", {"role": "viewer"}, method="patch").status_code == 409
    )
    assert post(client, f"/users/{LOCAL_PREVIEW_USER_ID}/reset-access").status_code == 409
    with mail.record_messages() as messages:
        assert post(client, "/auth/password/forgot", {"email": LOCAL_PREVIEW_EMAIL}).status_code == 200
    assert messages == []
    human = User(email="human-admin@example.org", name="Human test admin", role="superadmin")
    human.set_password("Test-only-password-2026")
    db.session.add(human)
    db.session.commit()
    assert post(client, f"/users/{human.id}", {"is_active": False}, method="patch").status_code == 409


def test_production_refuses_preview_at_configuration_and_factory(monkeypatch):
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    with pytest.raises(RuntimeError, match="prohibido en producción"):
        settings("production")
    assert settings("testing")["DEV_AUTH_BYPASS"] is False
    with pytest.raises(RuntimeError, match="desarrollo local"):
        create_app("testing", {"DEV_AUTH_BYPASS": True, "PRODUCTION": True})
