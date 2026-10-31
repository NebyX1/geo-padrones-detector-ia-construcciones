import re
import pytest
from app.extensions import db, mail
from app.models import User, AuthChallenge
from conftest import login, post, captcha_payload

pytestmark = pytest.mark.integration


def test_csrf_auth_2fa_replay_logout(client):
    assert client.get("/api/v1/parcels").status_code == 401
    assert client.post("/api/v1/auth/login", json={}).status_code == 400
    user = login(client)
    assert client.get("/api/v1/auth/me").json["user"]["id"] == user.id
    challenge = db.session.query(AuthChallenge).one()
    assert challenge.consumed_at is not None
    assert post(client, "/auth/2fa/verify", {"code": "000000"}).status_code == 422
    assert post(client, "/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "role,endpoint,expected",
    [
        ("viewer", "/users", 403),
        ("reviewer", "/users", 403),
        ("analyst", "/users", 403),
        ("admin", "/users", 200),
        ("superadmin", "/users", 200),
    ],
)
def test_roles_enforced_on_server(client, role, endpoint, expected):
    login(client, role)
    assert client.get("/api/v1" + endpoint).status_code == expected
    if role in {"viewer", "reviewer"}:
        assert post(client, "/exports", {"format": "csv"}).status_code == 403
        assert post(client, "/analysis/jobs", {}).status_code == 403


def test_five_wrong_codes_lock_challenge(client):
    user = User(email="lock@example.org", name="Lock", role="viewer")
    user.set_password("Test-only-password-2026")
    db.session.add(user)
    db.session.commit()
    with mail.record_messages() as messages:
        assert (
            post(
                client,
                "/auth/login",
                {"email": user.email, "password": "Test-only-password-2026", **captcha_payload(client)},
            ).status_code
            == 200
        )
        code = re.search(r"\b\d{6}\b", messages[0].body).group()
    wrong = "999999" if code != "999999" else "000000"
    for _ in range(5):
        assert post(client, "/auth/2fa/verify", {"code": wrong}).status_code == 422
    assert post(client, "/auth/2fa/verify", {"code": code}).status_code == 422


def test_deactivation_and_role_change_revoke_session(client):
    user = login(client, "viewer")
    user.session_version += 1
    db.session.commit()
    assert client.get("/api/v1/parcels").status_code == 401


def test_admin_cannot_escalate_and_last_superadmin_is_protected(client):
    login(client, "admin")
    assert (
        post(
            client,
            "/users",
            {
                "email": "bad@example.org",
                "name": "Bad role",
                "password": "Test-only-password-2026",
                "role": "superadmin",
            },
        ).status_code
        == 403
    )
    post(client, "/auth/logout")
    user = login(client, "superadmin")
    assert post(client, f"/users/{user.id}", {"is_active": False}, method="patch").status_code == 409


def test_expired_code_and_password_reset_revoke_existing_session(client):
    user = login(client, "viewer")
    with mail.record_messages() as messages:
        response = post(client, "/auth/password/forgot", {"email": user.email})
        code = re.search(r"\b\d{6}\b", messages[0].body).group()
    assert (
        post(
            client,
            "/auth/password/reset",
            {
                "challenge_id": response.json["challenge_id"],
                "code": code,
                "password": "Updated-only-password-2026",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        post(
            client,
            "/auth/password/reset",
            {
                "challenge_id": response.json["challenge_id"],
                "code": code,
                "password": "Updated-only-password-2026",
            },
        ).status_code
        == 422
    )


def test_admin_reset_access_sends_recovery_and_revokes_sessions(client):
    login(client, "superadmin")
    target = User(email="recover@example.org", name="Recuperación", role="viewer")
    target.set_password("Test-only-password-2026")
    db.session.add(target)
    db.session.commit()
    previous_version = target.session_version
    with mail.record_messages() as messages:
        response = post(client, f"/users/{target.id}/reset-access")
    assert response.status_code == 200
    assert target.session_version == previous_version + 1
    assert len(messages) == 1
    challenge = db.session.query(AuthChallenge).filter_by(user_id=target.id, purpose="reset").one()
    assert f"?reset={challenge.id}" in messages[0].body
    code = re.search(r"\b\d{6}\b", messages[0].body).group()
    target.is_active = False
    db.session.commit()
    assert post(client, f"/users/{target.id}/reset-access").status_code == 409
    target.is_active = True
    db.session.commit()
    assert (
        post(
            client,
            "/auth/password/reset",
            {"challenge_id": challenge.id, "code": code, "password": "Recovered-test-only-password-2026"},
        ).status_code
        == 200
    )


def test_admin_cannot_reset_superadmin_access(client):
    login(client, "admin")
    target = User(email="protected@example.org", name="Protegido", role="superadmin")
    target.set_password("Test-only-password-2026")
    db.session.add(target)
    db.session.commit()
    with mail.record_messages() as messages:
        assert post(client, f"/users/{target.id}/reset-access").status_code == 403
    assert not messages
