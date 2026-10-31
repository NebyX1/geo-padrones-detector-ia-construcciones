import hashlib
import io
import json
import pytest
from shapely.geometry import box, mapping, MultiPolygon
from geoalchemy2.shape import from_shape
from sqlalchemy import select, func
from app.extensions import db
from app.models import (
    Parcel,
    CadastralDatasetVersion,
    CadastralLocality,
    ImageryScene,
    AIModelVersion,
    Job,
    AnalysisRun,
    ParcelAnalysisResult,
    ParcelGeometryVersion,
    ReviewCase,
    ReviewAction,
)
from app.services.cadastre import import_file
from app.services.geospatial import reproject
from app.services.csv_import import reconcile
from app.services.queue import new_job
from conftest import login, post

pytestmark = pytest.mark.integration


def seed_parcel(padron="00012"):
    """Explicit synthetic fixture in metric coordinates, never published as an AI observation."""
    version = CadastralDatasetVersion(
        sha256=hashlib.sha256(padron.encode()).hexdigest(), source="SYNTHETIC TEST FIXTURE", count=1
    )
    loc = CadastralLocality(coddepto="P", codloccat="AA", name="MINAS")
    db.session.add_all([version, loc])
    db.session.flush()
    metric = box(662000, 6194700, 662020, 6194720)
    geom = MultiPolygon([reproject(metric, 5382, 4326)])
    parcel = Parcel(
        coddepto="P",
        codloccat="AA",
        padron=padron,
        locality_id=loc.id,
        geom=from_shape(geom, srid=4326),
        m2_parcela=400,
        source_version_id=version.id,
    )
    db.session.add(parcel)
    db.session.flush()
    db.session.add(
        ParcelGeometryVersion(
            parcel_id=parcel.id,
            dataset_version_id=version.id,
            source_feature_id=f"TEST.{padron}",
            original={
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {"fixture": "SYNTHETIC TEST ONLY"},
            },
            geom=from_shape(geom, srid=4326),
        )
    )
    db.session.commit()
    return parcel


def seed_result(parcel, user_id):
    scene = ImageryScene(
        name="SYNTHETIC TEST SCENE",
        source="test://fixture",
        coverage_id="TEST",
        captured_at="2025-12",
        resolution_m=0.2,
        license="test fixture",
    )
    model = AIModelVersion(
        model_id="SYNTHETIC_TEST_MODEL",
        revision="a" * 40,
        sha256="b" * 64,
        filename="test-fixture",
        license="test",
        metadata_json={},
    )
    db.session.add_all([scene, model])
    db.session.flush()
    job = Job(
        user_id=user_id,
        kind="analysis",
        status="COMPLETED",
        idempotency_key="test",
        payload={},
        total=1,
        processed=1,
    )
    db.session.add(job)
    db.session.flush()
    run = AnalysisRun(job_id=job.id, model_version_id=model.id, scene_id=scene.id, parameters={})
    db.session.add(run)
    db.session.flush()
    result = ParcelAnalysisResult(
        run_id=run.id,
        parcel_id=parcel.id,
        parcel_version_id=parcel.source_version_id,
        state="CON_CONSTRUCCION_VISIBLE",
        m2_huella_detectada=100,
        occupancy=0.25,
        building_count=1,
        coverage=1,
    )
    db.session.add(result)
    db.session.flush()
    parcel.current_result_id = result.id
    case = ReviewCase(result_id=result.id)
    db.session.add(case)
    db.session.commit()
    return result, case


def test_real_postgis_area_bbox_and_mvt(client):
    login(client, "viewer")
    parcel = seed_parcel()
    area = db.session.execute(
        select(func.ST_Area(func.ST_Transform(Parcel.geom, 5382))).where(Parcel.id == parcel.id)
    ).scalar()
    assert area == pytest.approx(400, abs=0.01)
    result = client.get("/api/v1/parcels?q=00012&format=geojson")
    assert result.status_code == 200
    assert result.json["features"][0]["properties"]["padron"] == "00012"
    assert client.get("/api/v1/parcels?format=geojson").status_code == 422
    assert client.get("/api/v1/parcels?bbox=NaN,0,1,2").status_code == 422
    tile = client.get("/api/v1/parcels/tiles/10/354/616.pbf")
    assert tile.status_code == 200
    assert tile.content_type == "application/vnd.mapbox-vector-tile"


def test_import_keeps_parts_and_is_idempotent(context, tmp_path):
    geoms = [
        reproject(box(662000, 6194700, 662020, 6194720), 5382, 4326),
        reproject(box(662010, 6194700, 662030, 6194720), 5382, 4326),
    ]
    features = [
        {
            "type": "Feature",
            "id": f"TEST.{i}",
            "geometry": mapping(MultiPolygon([g])),
            "properties": {
                "nomdepto": "LAVALLEJA",
                "coddepto": "P",
                "codloccat": "AA",
                "nomloccat": "MINAS",
                "padron": "001",
            },
        }
        for i, g in enumerate(geoms)
    ]
    path = tmp_path / "test.ndjson"
    path.write_text("\n".join(json.dumps(f) for f in features) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".manifest.json").write_text(
        json.dumps({"source": "SYNTHETIC TEST WFS", "sha256": digest, "count": 2}), encoding="utf-8"
    )
    first = import_file(path)
    second = import_file(path)
    assert first["duplicate_keys"] == 1 and first["identities"] == 1
    assert second["idempotent"]
    assert db.session.execute(select(Parcel)).scalar_one().m2_parcela == pytest.approx(600, abs=0.01)


def test_csv_reconciliation_preserves_identifiers_and_issues(context):
    parcel = seed_parcel()
    raw = b"departamento;localidad;padron;construido;m2\nP;AA;00012;NO;0\nP;AA;00012;SI;100\nP;AA;99999;NO;0\nP;;00012;NO;0\n"
    mapping_ = {
        "department": "departamento",
        "locality": "localidad",
        "padron": "padron",
        "declared_building": "construido",
        "declared_m2": "m2",
    }
    rows = list(reconcile(raw, mapping_))
    assert rows[0]["parcel_id"] == parcel.id
    assert rows[0]["key"]["padron"] == "00012"
    assert rows[0]["declared_building"] is False
    assert set(rows[1]["issues"]) == {"DUPLICADO", "DECLARACION_CONTRADICTORIA"}
    assert rows[2]["issues"] == ["NO_CONCILIADO"]
    assert "LOCALIDAD_FALTANTE" in rows[3]["issues"]


def test_review_preserves_original_and_detects_concurrent_update(client):
    user = login(client, "superadmin")
    parcel = seed_parcel()
    result, case = seed_result(parcel, user.id)
    original = result.m2_huella_detectada
    payload = {
        "version": 1,
        "status": "CORREGIDO",
        "state": "SIN_CONSTRUCCION_VISIBLE",
        "observations": "Fixture: falso positivo verificado",
    }
    assert post(client, f"/reviews/{case.id}", payload, method="patch").status_code == 200
    assert post(client, f"/reviews/{case.id}", payload, method="patch").status_code == 409
    db.session.refresh(result)
    assert result.m2_huella_detectada == original and result.state == "CON_CONSTRUCCION_VISIBLE"
    action = db.session.execute(select(ReviewAction)).scalar_one()
    assert action.corrected_m2 == 0 and action.state == "SIN_CONSTRUCCION_VISIBLE"


def test_job_idempotency_and_conflicting_parameters(client):
    user = login(client)
    first, created = new_job("export", user.id, {"format": "csv"}, key="unique-test-request")
    db.session.commit()
    second, created_again = new_job("export", user.id, {"format": "csv"}, key="unique-test-request")
    assert created and not created_again and first.id == second.id


def test_upload_validation_and_confirmation(client, monkeypatch):
    login(client, "analyst")
    seed_parcel()
    monkeypatch.setattr("app.routes.workflow.dispatch", lambda job: None)
    csrf = client.get("/api/v1/auth/csrf").json["csrf_token"]
    response = client.post(
        "/api/v1/imports/csv",
        data={"file": (io.BytesIO(b"coddepto;codloccat;padron;construido\nP;AA;00012;NO\n"), "test.csv")},
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 201
    identifier = response.json["id"]
    mapping_ = {
        "department": "coddepto",
        "locality": "codloccat",
        "padron": "padron",
        "declared_building": "construido",
    }
    validation = post(client, f"/imports/{identifier}/validate", {"mapping": mapping_})
    assert validation.status_code == 200
    assert validation.json["summary"] == {"matched": 1}
    confirmation = post(client, f"/imports/{identifier}/confirm")
    assert confirmation.status_code == 202
    assert post(client, f"/imports/{identifier}/confirm").json["job"]["id"] == confirmation.json["job"]["id"]
