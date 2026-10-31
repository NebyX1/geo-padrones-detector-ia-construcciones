"""A comparison remains reproducible when the current cadastral result is invalidated."""

import pytest
from app.extensions import db
from app.models import ImportBatch, ImportedParcelDeclaration, ComparisonRun
from app.services.queue import new_job
from app.tasks import compare_batch
from app.services.exports import export_records
from conftest import login
from test_workflow_integration import seed_parcel, seed_result

pytestmark = pytest.mark.integration


def test_comparison_map_snapshot_export_and_unmatched_rows(client):
    user = login(client)
    parcel = seed_parcel()
    result, _ = seed_result(parcel, user.id)
    batch = ImportBatch(
        user_id=user.id,
        filename="SYNTHETIC TEST ONLY.csv",
        object_key="fixture",
        sha256="f" * 64,
        status="CONFIRMED",
    )
    db.session.add(batch)
    db.session.flush()
    for number, identifier in [(1, parcel.id), (2, None)]:
        db.session.add(
            ImportedParcelDeclaration(
                batch_id=batch.id,
                row_number=number,
                parcel_id=identifier,
                key={"coddepto": "P", "codloccat": "AA", "padron": parcel.padron if identifier else "99999"},
                declared_building=False,
                original={"fixture": "SYNTHETIC TEST ONLY"},
            )
        )
    job, _ = new_job("comparison", user.id, {}, key="comparison-snapshot-test")
    run = ComparisonRun(batch_id=batch.id, user_id=user.id, job_id=job.id, parameters={})
    db.session.add(run)
    db.session.commit()
    compare_batch(job)
    db.session.commit()
    response = client.get(f"/api/v1/parcels?q=00012&format=geojson&comparison_id={run.id}")
    assert (
        response.json["features"][0]["properties"]["comparison_state"] == "POSIBLE_CONSTRUCCION_NO_DECLARADA"
    )
    page = client.get(f"/api/v1/comparisons/{run.id}?limit=1").json
    assert len(page["items"]) == 1 and page["next_offset"] == 1
    parcel.current_result_id = None  # As when a new cadastral geometry invalidates the current result.
    db.session.commit()
    features = list(export_records({"comparison_id": run.id}))
    assert len(features) == 2
    matched = next(f for f in features if f["geometry"])
    assert matched["properties"]["m2_huella_detectada"] == 100
    assert matched["properties"]["result_id"] == result.id
    assert matched["properties"]["fecha_imagen"] == "2025-12"
    unmatched = next(f for f in features if f["geometry"] is None)
    assert unmatched["properties"]["padron"] == "99999"
    assert unmatched["properties"]["estado_comparacion"] == "NO_CONCILIADO"
    selected = list(export_records({"comparison_id": run.id, "ids": [parcel.id]}))
    assert len(selected) == 1 and selected[0]["properties"]["padron"] == parcel.padron
