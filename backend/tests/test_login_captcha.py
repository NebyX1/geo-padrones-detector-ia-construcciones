from datetime import timedelta
import pytest
from app.extensions import db, mail
from app.models import User, LoginCaptcha, utcnow
from conftest import post, captcha_payload

pytestmark = pytest.mark.integration


def credentials():
    user = User(email="captcha@example.org", name="Captcha test", role="viewer")
    user.set_password("Test-only-password-2026")
    db.session.add(user)
    db.session.commit()
    return {"email": user.email, "password": "Test-only-password-2026"}


def test_captcha_required_wrong_answer_consumed_and_2fa_still_required(client):
    data = credentials()
    assert post(client, "/auth/login", data).status_code == 422
    challenge = captcha_payload(client)
    assert post(client, "/auth/login", {**data, **challenge, "captcha_answer": "99"}).status_code == 422
    assert post(client, "/auth/login", {**data, **challenge}).status_code == 422
    fresh = captcha_payload(client)
    with mail.record_messages() as messages:
        response = post(client, "/auth/login", {**data, **fresh})
    assert response.status_code == 200 and response.json["requires_2fa"] is True
    assert len(messages) == 1
    assert client.get("/api/v1/parcels").status_code == 401
    assert post(client, "/auth/login", {**data, **fresh}).status_code == 422


def test_expired_captcha_and_another_browser_rejected(client):
    data = credentials()
    challenge = captcha_payload(client)
    other = client.application.test_client()
    assert post(other, "/auth/login", {**data, **challenge}).status_code == 422
    entry = db.session.get(LoginCaptcha, challenge["captcha_id"])
    assert entry.consumed_at is None
    entry.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert post(client, "/auth/login", {**data, **challenge}).status_code == 422


def test_refresh_invalidates_previous_sum_and_password_failure_consumes(client):
    data = credentials()
    previous = captcha_payload(client)
    fresh = captcha_payload(client)
    assert previous["captcha_id"] != fresh["captcha_id"]
    assert post(client, "/auth/login", {**data, **previous}).status_code == 422
    assert post(client, "/auth/login", {**data, **fresh, "password": "wrong-password"}).status_code == 401
    assert post(client, "/auth/login", {**data, **fresh}).status_code == 422
