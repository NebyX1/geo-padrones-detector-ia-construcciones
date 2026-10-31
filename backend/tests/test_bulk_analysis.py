"""Bulk fixtures are explicitly synthetic; browser QA separately runs real FLAIR."""

import csv
import io
import hashlib
import pytest
from shapely.geometry import box, MultiPolygon, mapping
from shapely import union_all
from geoalchemy2.shape import from_shape
from sqlalchemy import select
from flask import current_app
from app.extensions import db
from app.models import (
    Parcel,
    ParcelGeometryVersion,
    CadastralDatasetVersion,
    ImageryScene,
    AIModelVersion,
    BulkSelection,
    BulkSelectionItem,
    Job,
    AnalysisRun,
    ParcelAnalysisResult,
    uid,
)
from app.services.geospatial import reproject
from app.services.exports import generate_export, export_records
from app.services.storage import storage
from app.tasks import analyze
from conftest import login, post
from test_workflow_integration import seed_parcel, seed_result

pytestmark = pytest.mark.integration


def seed_many(count):
    first = seed_parcel("00000")
    parcels = [first]
    polygons = [box(662000, 6194700, 662020, 6194720)]
    for index in range(1, count):
        x, y = index % 40, index // 40
        metric = box(662000 + x * 22, 6194700 + y * 22, 662020 + x * 22, 6194720 + y * 22)
        geometry = MultiPolygon([reproject(metric, 5382, 4326)])
        parcel = Parcel(
            id=uid(),
            coddepto="P",
            codloccat="AA",
            padron=f"{index:05}",
            locality_id=first.locality_id,
            source_version_id=first.source_version_id,
            m2_parcela=400,
            geom=from_shape(geometry, srid=4326),
        )
        db.session.add(parcel)
        db.session.add(
            ParcelGeometryVersion(
                parcel_id=parcel.id,
                dataset_version_id=first.source_version_id,
                source_feature_id=f"SYNTHETIC.{index}",
                original={
                    "type": "Feature",
                    "geometry": mapping(geometry),
                    "properties": {"fixture": "SYNTHETIC TEST ONLY"},
                },
                geom=from_shape(geometry, srid=4326),
            )
        )
        parcels.append(parcel)
        polygons.append(metric)
    db.session.commit()
    bounds = list(reproject(union_all(polygons).envelope.buffer(1).envelope, 5382, 4326).bounds)
    return parcels, bounds


def resources(bounds):
    scene = ImageryScene(
        name="SYNTHETIC BULK TEST",
        source="test://fixture",
        coverage_id="BULK_TEST",
        captured_at="2025-12",
        resolution_m=0.05,
        license="SYNTHETIC TEST ONLY",
        metadata_json={"bounds_wgs84": bounds},
    )
    model = AIModelVersion(
        model_id="SYNTHETIC_BULK_TEST",
        revision="a" * 40,
        sha256="b" * 64,
        filename="test-only-no-checkpoint",
        license="test",
        metadata_json={},
    )
    db.session.add_all([scene, model])
    db.session.commit()
    return scene, model


def start(client, bounds, scene, model, key="bulk-test"):
    return post(
        client,
        "/bulk-selections",
        {
            "name": "SYNTHETIC BULK TEST ONLY",
            "bounds": bounds,
            "scene_id": scene.id,
            "model_version_id": model.id,
        },
        headers={"Idempotency-Key": key},
    )


def test_selection_exceeds_map_cap_and_splits_into_bounded_idempotent_jobs(client, monkeypatch):
    login(client, "analyst")
    monkeypatch.setattr("app.routes.bulk_analysis.dispatch", lambda job: None)
    parcels, bounds = seed_many(1005)
    scene, model = resources(bounds)
    preview = post(client, "/bulk-selections/preview", {"bounds": bounds, "scene_id": scene.id})
    assert preview.status_code == 200 and preview.json["total"] == 1005
    response = start(client, bounds, scene, model)
    assert response.status_code == 202
    batch = response.json["batch"]
    assert batch["total"] == 1005 and batch["processed"] == 0 and batch["states"] == {"NO_ANALIZADO": 1005}
    assert len(batch["jobs"]) > 1
    jobs = list(db.session.scalars(select(Job)))
    assert sum(job.total for job in jobs) == 1005
    assert all(job.total <= 50 for job in jobs)
    assert db.session.query(BulkSelectionItem).count() == 1005
    assert start(client, bounds, scene, model).json["batch"]["id"] == batch["id"]
    assert db.session.query(BulkSelection).count() == 1
    assert (
        post(
            client,
            "/bulk-selections",
            {"name": "different", "bounds": bounds, "scene_id": scene.id, "model_version_id": model.id},
            headers={"Idempotency-Key": "bulk-test"},
        ).status_code
        == 409
    )
    cancelled = post(client, f"/bulk-selections/{batch['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json["batch"]["status"] == "CANCELLED"
    assert all(job.cancel_requested for job in db.session.scalars(select(Job)))


def test_filter_sort_and_csv_use_only_the_frozen_batch_results(client, monkeypatch, tmp_path):
    user = login(client, "analyst")
    monkeypatch.setattr("app.routes.bulk_analysis.dispatch", lambda job: None)
    monkeypatch.setattr("app.routes.workflow.dispatch", lambda job: None)
    monkeypatch.setitem(current_app.config, "DATA_DIR", tmp_path)
    parcels, bounds = seed_many(3)
    seed_result(parcels[0], user.id)  # A prior current result must not appear as a result of this batch.
    scene, model = resources(bounds)
    batch = start(client, bounds, scene, model).json["batch"]
    assert (
        client.get(f"/api/v1/bulk-selections/{batch['id']}/results").json["items"][0]["m2_huella_detectada"]
        is None
    )
    for parcel, area in zip(parcels, [120, 0, 300]):
        item = db.session.scalar(
            select(BulkSelectionItem).where(
                BulkSelectionItem.selection_id == batch["id"], BulkSelectionItem.parcel_id == parcel.id
            )
        )
        run = db.session.scalar(select(AnalysisRun).where(AnalysisRun.job_id == item.job_id))
        db.session.add(
            ParcelAnalysisResult(
                run_id=run.id,
                parcel_id=parcel.id,
                parcel_version_id=item.parcel_version_id,
                state="CON_CONSTRUCCION_VISIBLE" if area else "SIN_CONSTRUCCION_VISIBLE",
                m2_huella_detectada=area,
                coverage=1,
                occupancy=area / 400,
                building_count=1 if area else 0,
            )
        )
        job = db.session.get(Job, item.job_id)
        job.status = "COMPLETED"
        job.processed = job.total
    db.session.commit()
    newest = CadastralDatasetVersion(
        sha256=hashlib.sha256(b"new bulk test version").hexdigest(), source="SYNTHETIC TEST", count=1
    )
    db.session.add(newest)
    db.session.flush()
    parcels[2].source_version_id = newest.id
    parcels[2].m2_parcela = 900
    parcels[2].geom = from_shape(
        MultiPolygon([reproject(box(663000, 6194700, 663030, 6194730), 5382, 4326)]), srid=4326
    )
    db.session.commit()
    url = f"/api/v1/bulk-selections/{batch['id']}/results"
    descending = client.get(url + "?sort=footprint_desc").json
    assert [row["m2_huella_detectada"] for row in descending["items"]] == [300, 120, 0]
    assert descending["items"][0]["m2_parcela"] == 400
    assert [row["m2_huella_detectada"] for row in client.get(url + "?sort=footprint_asc").json["items"]] == [
        0,
        120,
        300,
    ]
    assert client.get(url + "?state=SIN_CONSTRUCCION_VISIBLE").json["total_filtered"] == 1
    assert client.get(url + "?min_area=100&max_area=200").json["total_filtered"] == 1
    assert client.get(url + "?sort=arbitrary_sql").status_code == 422
    summary = client.get(f"/api/v1/bulk-selections/{batch['id']}").json["batch"]
    assert summary["footprint_m2"] == 420 and summary["processed"] == 3 and summary["status"] == "COMPLETED"
    page = client.get(url + "?state=CON_CONSTRUCCION_VISIBLE&limit=1").json
    assert len(page["items"]) == 1 and page["total_filtered"] == 2 and page["next_offset"] == 1
    values = {"bulk_id": batch["id"], "state": "CON_CONSTRUCCION_VISIBLE", "sort": "footprint_desc"}
    export = post(client, "/exports", {"format": "csv", "filters": values})
    assert export.status_code == 202
    job = db.session.get(Job, export.json["job"]["id"])
    generate_export(job, lambda n: None)
    records = list(csv.DictReader(io.StringIO(storage().get(job.output_key).decode("utf-8-sig"))))
    assert len(records) == 2 and [float(row["m2_huella_detectada"]) for row in records] == [300, 120]
    assert all(row["lote_seleccion"] == batch["id"] and row["fecha_imagen"] == "2025-12" for row in records)
    assert records[0]["modelo"] == "SYNTHETIC_BULK_TEST"
    historical = list(export_records(values))[0]
    assert historical["properties"]["m2_parcela"] == 400
    assert historical["geometry"]["coordinates"][0][0][0][0] < -55


def test_caps_empty_and_permissions(client, monkeypatch):
    login(client, "viewer")
    parcels, bounds = seed_many(4)
    scene, model = resources(bounds)
    monkeypatch.setitem(current_app.config, "MAX_BULK_PARCELS", 3)
    assert start(client, bounds, scene, model).status_code == 403
    preview = post(client, "/bulk-selections/preview", {"bounds": bounds})
    assert preview.json["total"] == 4 and preview.json["can_analyze"] is False
    assert post(client, "/bulk-selections/preview", {"bounds": ["wrong", 1, 2, 3]}).status_code == 422
    assert post(client, "/bulk-selections/preview", {"bounds": [-55, -34, -56, -35]}).status_code == 422


def test_no_coverage_is_indeterminate_without_loading_model(client, monkeypatch):
    login(client, "analyst")
    monkeypatch.setattr("app.routes.bulk_analysis.dispatch", lambda job: None)
    parcels, bounds = seed_many(2)
    scene, model = resources([-58, -34, -57.9, -33.9])
    batch = start(client, bounds, scene, model).json["batch"]

    def forbidden(*args, **kwargs):
        raise AssertionError("No model may load for missing imagery")

    monkeypatch.setattr("app.services.inference.load_model", forbidden)
    for job in db.session.scalars(select(Job)):
        analyze(job)
    rows = client.get(f"/api/v1/bulk-selections/{batch['id']}/results").json["items"]
    assert len(rows) == 2 and all(
        row["state"] == "INDETERMINADO" and row["m2_huella_detectada"] is None for row in rows
    )
