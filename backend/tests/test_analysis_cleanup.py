"""All deletion fixtures live in the disposable PostGIS test database."""

from sqlalchemy import select, func
from app.extensions import db
from app.models import (
    Job,
    AnalysisRun,
    ParcelAnalysisResult,
    ReviewCase,
    ReviewAction,
    ReviewAttachment,
    BuildingFootprint,
    Parcel,
    BulkSelection,
    BulkSelectionItem,
    CleanupEntry,
    AuditLog,
    ImportBatch,
    ImportedParcelDeclaration,
    ComparisonRun,
    ParcelComparisonResult,
)
from app.services.storage import storage, ObjectStorage
from app.services.garbage_collection import collect_garbage
from conftest import login, post
from test_bulk_analysis import seed_many
from test_workflow_integration import seed_result


def fixture(client):
    user = login(client, "superadmin")
    parcels, _ = seed_many(3)
    first, case = seed_result(parcels[0], user.id)
    run = db.session.get(AnalysisRun, first.run_id)
    job = db.session.get(Job, run.job_id)
    job.payload = {"parcel_ids": [p.id for p in parcels]}
    job.total = job.processed = 3
    for parcel, area in zip(parcels[1:], [0, 250]):
        result = ParcelAnalysisResult(
            run_id=run.id,
            parcel_id=parcel.id,
            parcel_version_id=parcel.source_version_id,
            state="SIN_CONSTRUCCION_VISIBLE" if area == 0 else "CON_CONSTRUCCION_VISIBLE",
            m2_huella_detectada=area,
            coverage=1,
        )
        db.session.add(result)
        db.session.flush()
        parcel.current_result_id = result.id
        db.session.add(ReviewCase(result_id=result.id))
    first.mask_key = storage().put("masks/test/first.tif", b"SYNTHETIC MASK")
    for suffix in (".png", ".json"):
        storage().put(first.mask_key + suffix, b"SYNTHETIC PREVIEW")
    attachment = ReviewAttachment(
        case_id=case.id,
        user_id=user.id,
        filename="test.png",
        mime="image/png",
        size=4,
        sha256="a" * 64,
        object_key=storage().put("review-evidence/test.png", b"test"),
    )
    db.session.add_all(
        [
            attachment,
            ReviewAction(
                case_id=case.id,
                user_id=user.id,
                status="CONFIRMADO",
                state=first.state,
                observations="SYNTHETIC TEST REVIEW",
                version=1,
            ),
        ]
    )
    db.session.commit()
    return user, parcels, first, case, run, job


def preview(client, target="analysis", mode="all", **extra):
    selection = {"target": target, "mode": mode, **extra}
    response = post(client, "/analysis/cleanup/preview", selection)
    assert response.status_code == 200, response.json
    return {
        **selection,
        "fingerprint": response.json["fingerprint"],
        "confirmation": "ELIMINAR",
    }, response.json


def test_full_reset_deletes_results_reviews_files_and_derived_records_but_keeps_inputs(client, monkeypatch):
    user, parcels, first, case, run, job = fixture(client)
    batch = BulkSelection(
        user_id=user.id,
        name="SYNTHETIC",
        bounds=[-56, -35, -55, -34],
        selection_filters={},
        scene_id=run.scene_id,
        model_version_id=run.model_version_id,
        parameters={},
        request_payload={},
        idempotency_key="test",
        total=3,
    )
    db.session.add(batch)
    db.session.flush()
    for parcel in parcels:
        db.session.add(
            BulkSelectionItem(
                selection_id=batch.id,
                parcel_id=parcel.id,
                parcel_version_id=parcel.source_version_id,
                parcel_area_m2=400,
                job_id=job.id,
            )
        )
    source = ImportBatch(user_id=user.id, filename="keep.csv", object_key="imports/keep.csv", sha256="a" * 64)
    db.session.add(source)
    db.session.flush()
    declaration = ImportedParcelDeclaration(
        batch_id=source.id, row_number=1, parcel_id=parcels[0].id, key={}, original={}
    )
    compare_job = Job(
        kind="comparison", user_id=user.id, status="COMPLETED", idempotency_key="compare", payload={}
    )
    exported = Job(
        kind="export",
        user_id=user.id,
        status="COMPLETED",
        idempotency_key="export",
        payload={},
        output_key=storage().put("exports/test.csv", b"test"),
    )
    db.session.add_all([declaration, compare_job, exported])
    db.session.flush()
    comparison = ComparisonRun(batch_id=source.id, user_id=user.id, job_id=compare_job.id, parameters={})
    db.session.add(comparison)
    db.session.flush()
    db.session.add(
        ParcelComparisonResult(
            run_id=comparison.id, declaration_id=declaration.id, result_id=first.id, state="CONCORDANCIA"
        )
    )
    db.session.commit()
    monkeypatch.setattr(
        "app.services.garbage_collection.redis_connection",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    data, info = preview(client)
    assert info["counts"]["results"] == 3 and info["counts"]["reviews"] == 3
    response = post(client, "/analysis/cleanup", data)
    assert response.status_code == 200, response.json
    collect_garbage(limit=100)
    for model in (
        Job,
        AnalysisRun,
        ParcelAnalysisResult,
        ReviewCase,
        ReviewAction,
        ReviewAttachment,
        BuildingFootprint,
        BulkSelection,
        BulkSelectionItem,
        ComparisonRun,
        ParcelComparisonResult,
    ):
        assert db.session.scalar(select(func.count()).select_from(model)) == 0, model
    assert db.session.scalar(select(func.count()).select_from(Parcel)) == 3
    assert all(p.current_result_id is None for p in db.session.scalars(select(Parcel)))
    assert db.session.get(ImportBatch, source.id) is not None
    assert not (storage().root / "masks/test/first.tif").exists()
    assert not (storage().root / "exports/test.csv").exists()
    assert not (storage().root / "review-evidence/test.png").exists()
    # Idempotency rows were deleted too; a new inference can start with the same parameters/key.
    from app.services.queue import new_job

    fresh, created = new_job("analysis", user.id, {"parcel_ids": [parcels[0].id]}, key="test")
    assert created and fresh.id != job.id


def test_deleting_review_erases_its_result_without_resurrecting_old_results(client, monkeypatch):
    user, parcels, first, case, run, job = fixture(client)
    monkeypatch.setattr(
        "app.services.garbage_collection.redis_connection",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    data, _ = preview(client, "reviews", "ids", ids=[case.id])
    response = post(client, "/analysis/cleanup", data)
    assert response.status_code == 200, response.json
    assert db.session.get(ParcelAnalysisResult, first.id) is None
    assert db.session.get(Parcel, parcels[0].id).current_result_id is None
    db.session.refresh(job)
    assert job.total == 2 and job.processed == 2 and parcels[0].id not in job.payload["parcel_ids"]
    assert job.idempotency_key == "cleaned:" + job.id
    assert client.get("/api/v1/reviews").json["total"] == 2


def test_deletion_removes_old_review_observations_from_audit_but_keeps_deletion_audit(client):
    _, _, _, case, _, _ = fixture(client)
    db.session.add(
        AuditLog(action="REANALYSIS_REQUESTED", entity_id=case.id, details={"observations": "nota privada"})
    )
    db.session.commit()
    data, _ = preview(client, "reviews", "ids", ids=[case.id])
    assert post(client, "/analysis/cleanup", data).status_code == 200
    assert db.session.scalar(select(AuditLog).where(AuditLog.entity_id == case.id)) is None
    assert db.session.scalar(select(AuditLog).where(AuditLog.action == "ANALYSIS_DATA_DELETED")) is not None


def test_partial_review_deletion_keeps_other_members_of_bulk_batch(client, monkeypatch):
    user, parcels, _, case, run, job = fixture(client)
    batch = BulkSelection(
        user_id=user.id,
        name="SYNTHETIC",
        bounds=[-56, -35, -55, -34],
        selection_filters={},
        scene_id=run.scene_id,
        model_version_id=run.model_version_id,
        parameters={},
        request_payload={},
        idempotency_key="bulk-partial",
        total=3,
    )
    db.session.add(batch)
    db.session.flush()
    for parcel in parcels:
        db.session.add(
            BulkSelectionItem(
                selection_id=batch.id,
                parcel_id=parcel.id,
                parcel_version_id=parcel.source_version_id,
                parcel_area_m2=400,
                job_id=job.id,
            )
        )
    db.session.commit()
    data, _ = preview(client, "reviews", "ids", ids=[case.id])
    assert post(client, "/analysis/cleanup", data).status_code == 200
    summary = client.get(f"/api/v1/bulk-selections/{batch.id}")
    assert summary.status_code == 200
    assert summary.json["batch"]["total"] == 2
    assert summary.json["batch"]["processed"] == 2
    rows = client.get(f"/api/v1/bulk-selections/{batch.id}/results").json
    assert {row["id"] for row in rows["items"]} == {parcels[1].id, parcels[2].id}


def test_preview_conflict_running_jobs_and_worker_lock_are_rejected(client):
    _, _, _, _, _, job = fixture(client)
    data, _ = preview(client)
    job.status = "RUNNING"
    db.session.commit()
    assert post(client, "/analysis/cleanup", data).status_code == 409
    job.status = "COMPLETED"
    db.session.commit()
    data, _ = preview(client)
    with db.engine.connect() as connection:
        connection.execute(db.text("SELECT pg_advisory_lock(hashtext(:id))"), {"id": job.id})
        try:
            assert post(client, "/analysis/cleanup", data).status_code == 409
        finally:
            connection.execute(db.text("SELECT pg_advisory_unlock(hashtext(:id))"), {"id": job.id})
    data["fingerprint"] = "old-preview"
    assert post(client, "/analysis/cleanup", data).status_code == 409
    assert db.session.scalar(select(func.count()).select_from(ParcelAnalysisResult)) == 3


def test_filters_apply_to_complete_lists_and_deletion_scope(client):
    _, parcels, _, _, run, job = fixture(client)
    jobs = client.get(f"/api/v1/analysis/jobs?kind=analysis&q={parcels[0].padron}&locality=AA").json
    assert jobs["total"] == 1 and jobs["items"][0]["id"] == job.id
    rows = client.get("/api/v1/reviews?state=CON_CONSTRUCCION_VISIBLE&min_area=200&limit=1").json
    assert rows["total"] == 1 and len(rows["items"]) == 1
    data, info = preview(client, "reviews", "filtered", filters={"state": "SIN_CONSTRUCCION_VISIBLE"})
    assert info["counts"]["results"] == 1
    assert client.get("/api/v1/analysis/jobs?device=arbitrary").status_code == 422
    assert client.get("/api/v1/reviews?min_area=NaN").status_code == 422
    data["confirmation"] = ""
    assert post(client, "/analysis/cleanup", data).status_code == 422


def test_file_cleanup_is_retried_after_storage_failure(client, monkeypatch):
    fixture(client)
    with monkeypatch.context() as patch:
        patch.setattr(ObjectStorage, "delete", lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
        data, _ = preview(client, "reviews", "filtered", filters={"min_area": "50"})
        response = post(client, "/analysis/cleanup", data)
        assert response.status_code == 200 and response.json["pending_cleanup"] > 0
    collect_garbage(limit=100)
    assert (
        db.session.scalar(select(func.count()).select_from(CleanupEntry).where(CleanupEntry.kind == "object"))
        == 0
    )
    assert not (storage().root / "masks/test/first.tif").exists()


def test_only_administrators_can_delete_and_csrf_is_required(client):
    login(client, "analyst")
    assert post(client, "/analysis/cleanup/preview", {"target": "analysis", "mode": "all"}).status_code == 403
    assert client.post("/api/v1/analysis/cleanup", json={}).status_code == 400
