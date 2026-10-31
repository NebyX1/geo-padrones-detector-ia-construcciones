from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from app.extensions import db
from app.models import Job
from conftest import login, post
from test_workflow_integration import seed_parcel, seed_result

pytestmark = pytest.mark.integration


def concurrent_post(client, path, payload, method="post", headers=None):
    app = client.application
    token = client.get("/api/v1/auth/csrf").json["csrf_token"]
    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    barrier = Barrier(2)

    def send(_):
        isolated = app.test_client()
        isolated.set_cookie(app.config["SESSION_COOKIE_NAME"], cookie.value)
        barrier.wait(timeout=10)
        response = getattr(isolated, method)(
            "/api/v1" + path, json=payload, headers={"X-CSRFToken": token, **(headers or {})}
        )
        return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(send, range(2)))


def test_simultaneous_review_cannot_overwrite(client):
    user = login(client, "reviewer")
    parcel = seed_parcel()
    _, case = seed_result(parcel, user.id)
    responses = concurrent_post(
        client,
        f"/reviews/{case.id}",
        {
            "version": 1,
            "status": "CONFIRMADO",
            "state": "CON_CONSTRUCCION_VISIBLE",
            "observations": "Fixture de concurrencia real",
        },
        method="patch",
    )
    assert sorted(status for status, _ in responses) == [200, 409]


def test_simultaneous_idempotent_export_is_one_job(client, monkeypatch):
    login(client, "analyst")
    monkeypatch.setattr("app.routes.workflow.dispatch", lambda job: None)
    responses = concurrent_post(
        client,
        "/exports",
        {"format": "csv", "filters": {}},
        headers={"Idempotency-Key": "simultaneous-export-test"},
    )
    assert [status for status, _ in responses] == [202, 202]
    assert responses[0][1]["job"]["id"] == responses[1][1]["job"]["id"]
    assert db.session.query(Job).count() == 1


def test_redis_failure_keeps_durable_outbox_pending(client, monkeypatch):
    login(client, "analyst")

    def unavailable():
        raise ConnectionError("Simulated unavailable Redis")

    monkeypatch.setattr("app.services.queue.redis_connection", unavailable)
    response = post(client, "/exports", {"format": "csv", "filters": {}})
    assert response.status_code == 202
    assert response.json["job"]["status"] == "PENDING"
    assert db.session.query(Job).one().status == "PENDING"
