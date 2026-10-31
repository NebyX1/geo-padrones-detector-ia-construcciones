from flask import current_app
from types import SimpleNamespace
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from app.extensions import db
from app.models import AnalysisRun
from app.services.geospatial import measure
from shapely.geometry import box
from app.services.mask_preview import preview_mask
from app.services.storage import storage
from conftest import login
from test_workflow_integration import seed_parcel, seed_result


def test_zero_detection_threshold_cannot_create_buildings():
    measured = measure(box(0, 0, 10, 10), [], box(0, 0, 10, 10), min_area=0, min_occupancy=0)
    assert measured["state"] == "SIN_CONSTRUCCION_VISIBLE"


@pytest.mark.integration
def test_combinable_numeric_temporal_and_model_filters(client):
    user = login(client)
    parcel = seed_parcel()
    result, _ = seed_result(parcel, user.id)
    run = db.session.get(AnalysisRun, result.run_id)
    query = f"/api/v1/parcels?padron_from=12&padron_to=12&min_coverage=0.95&image_from=2025-12&image_to=2025-12&model_version_id={run.model_version_id}"
    response = client.get(query)
    assert response.status_code == 200 and len(response.json["items"]) == 1
    assert client.get("/api/v1/parcels?min_occupancy=0.3").json["items"] == []
    assert client.get("/api/v1/parcels?min_coverage=1.1").status_code == 422
    assert client.get("/api/v1/parcels?image_from=2025-13").status_code == 422
    assert client.get("/api/v1/parcels?analyzed_to=invalid").status_code == 422


@pytest.mark.integration
def test_real_mask_reprojection_and_private_preview(client, tmp_path, monkeypatch):
    login(client)
    monkeypatch.setitem(current_app.config, "DATA_DIR", tmp_path)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=20,
            width=20,
            count=1,
            dtype="uint8",
            crs="EPSG:5382",
            transform=from_origin(662000, 6194700, 0.2, 0.2),
            nodata=255,
        ) as raster:
            values = np.zeros((20, 20), dtype="uint8")
            values[5:15, 5:15] = 1
            raster.write(values, 1)
        key = storage().put("test-fixtures/mask.tif", memory.read(), "image/tiff")
    png, bounds = preview_mask(SimpleNamespace(mask_key=key))
    assert png.startswith(b"\x89PNG")
    assert len(bounds) == 4 and bounds[0] < bounds[2] and bounds[1] < bounds[3]
    assert -56 < bounds[0] < -54


@pytest.mark.integration
def test_storage_quota_enforced(context, tmp_path, monkeypatch):
    monkeypatch.setitem(context.config, "DATA_DIR", tmp_path)
    monkeypatch.setitem(context.config, "MAX_STORAGE_BYTES", 8)
    storage().put("first.bin", b"12345")
    with pytest.raises(ValueError, match="cuota"):
        storage().put("second.bin", b"1234")


@pytest.mark.integration
def test_dashboard_aggregations_respect_evidence_and_date_scope(client):
    user = login(client)
    parcel = seed_parcel()
    seed_result(parcel, user.id)
    response = client.get("/api/v1/dashboard/analytics?locality=AA")
    assert response.status_code == 200
    assert sum(row["count"] for row in response.json["footprint"]) == 1
    assert response.json["visible_by_locality"] == [{"label": "MINAS", "count": 1}]
    assert (
        sum(
            row["count"]
            for row in client.get("/api/v1/dashboard/analytics?from=2100-01-01").json["footprint"]
        )
        == 0
    )
    assert client.get("/api/v1/dashboard/analytics?from=2026-03-02&to=2026-03-01").status_code == 422
    parcel.active = False
    db.session.commit()
    dashboard = client.get("/api/v1/dashboard").json
    assert dashboard["total_parcels"] == 0 and dashboard["analyzed"] == 0
    assert dashboard["states"] == {} and dashboard["localities"] == []


@pytest.mark.integration
def test_wms_wait_does_not_hold_database_connection(client, monkeypatch):
    from app.models import ImageryScene

    user = login(client)
    parcel = seed_parcel()
    result, _ = seed_result(parcel, user.id)
    run = db.session.get(AnalysisRun, result.run_id)
    scene_id = db.session.get(ImageryScene, run.scene_id).id

    def renderer(scene, z, x, y):
        assert scene.id == scene_id
        assert db.engine.pool.checkedout() == 0
        return b"\x89PNG\r\n\x1a\n"

    monkeypatch.setattr("app.services.imagery.render_tile", renderer)
    assert client.get(f"/api/v1/imagery/scenes/{scene_id}/tiles/1/0/0.png").status_code == 200
    assert client.get(f"/api/v1/imagery/scenes/{scene_id}/tiles/1/9/0.png").status_code == 422
