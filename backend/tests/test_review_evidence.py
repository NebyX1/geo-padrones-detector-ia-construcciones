import io
import pytest
from PIL import Image
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, box, mapping
from app.extensions import db
from app.services.geospatial import reproject
from conftest import login, post
from test_workflow_integration import seed_parcel, seed_result

pytestmark = pytest.mark.integration


def test_review_uses_original_geometry_after_cadastral_change(client):
    user = login(client, "reviewer")
    parcel = seed_parcel()
    result, case = seed_result(parcel, user.id)
    parcel.geom = from_shape(
        MultiPolygon([reproject(box(663000, 6194700, 663030, 6194730), 5382, 4326)]), srid=4326
    )
    parcel.current_result_id = None
    db.session.commit()
    detail = client.get(f"/api/v1/reviews/{case.id}")
    assert detail.status_code == 200
    assert detail.json["parcel"]["properties"]["m2_parcela"] == pytest.approx(400, abs=0.01)
    corrected = mapping(reproject(box(662000, 6194700, 662010, 6194710), 5382, 4326))
    response = post(
        client,
        f"/reviews/{case.id}",
        {
            "version": 1,
            "status": "CORREGIDO",
            "state": "CON_CONSTRUCCION_VISIBLE",
            "observations": "Fixture: revisión histórica",
            "geometry": corrected,
        },
        method="patch",
    )
    assert response.status_code == 200
    assert result.m2_huella_detectada == 100


def test_private_authorized_attachments_and_reanalysis_request(client, tmp_path, monkeypatch):
    from flask import current_app

    monkeypatch.setitem(current_app.config, "DATA_DIR", tmp_path)
    user = login(client, "reviewer")
    parcel = seed_parcel()
    _, case = seed_result(parcel, user.id)
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, format="PNG")
    raw = image.getvalue()

    def upload(content=raw, authorized="true"):
        token = client.get("/api/v1/auth/csrf").json["csrf_token"]
        return client.post(
            f"/api/v1/reviews/{case.id}/attachments",
            data={"authorized": authorized, "file": (io.BytesIO(content), "SYNTHETIC-QA.png")},
            headers={"X-CSRFToken": token},
        )

    assert upload(authorized="false").status_code == 422
    assert upload(b'<svg onload="alert(1)"/>').status_code == 422
    created = upload()
    assert created.status_code == 201
    attachments = client.get(f"/api/v1/reviews/{case.id}/attachments").json["items"]
    assert len(attachments) == 1 and "object_key" not in attachments[0]
    url = f"/api/v1/reviews/{case.id}/attachments/{created.json['id']}"
    download = client.get(url)
    assert download.data == raw and "attachment;" in download.headers["Content-Disposition"]
    assert download.mimetype == "application/octet-stream"
    assert (
        post(
            client,
            f"/reviews/{case.id}/request-analysis",
            {"observations": "Problema de sombra en la ortofoto"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/reviews?needs_reanalysis=true").json["items"][0]["needs_reanalysis"] is True
    post(client, "/auth/logout")
    assert client.get(url).status_code == 401
