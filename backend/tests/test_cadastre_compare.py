"""Verifica el contraste catastral sin presentar evidencia sintética como real."""
import json
from types import SimpleNamespace

import pytest
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import AnalysisRun, BulkSelectionItem, ParcelAnalysisResult
from app.services.cadastre_compare import _read_dataset, outcome, select_records
from conftest import login, post
from test_bulk_analysis import resources, seed_many
from test_workflow_integration import seed_result


@pytest.mark.parametrize(("declared", "state", "expected"), [
    (False, "CON_CONSTRUCCION_VISIBLE", "discrepancia"),
    (True, "SIN_CONSTRUCCION_VISIBLE", "discrepancia"),
    (True, "CON_CONSTRUCCION_VISIBLE", "coincide"),
    (False, "SIN_CONSTRUCCION_VISIBLE", "coincide"),
    (None, "CON_CONSTRUCCION_VISIBLE", "sin_referencia"),
    (None, "SIN_CONSTRUCCION_VISIBLE", "sin_referencia"),
    (False, "INDETERMINADO", "indeterminado"),
    (True, "ERROR_ANALISIS", "indeterminado"),
    (True, None, "pendiente"),
])
def test_outcomes_never_assume_unknown_or_errors_are_contradictions(declared, state, expected):
    assert outcome(declared, None if state is None else SimpleNamespace(state=state)) == expected


def test_rural_selection_without_locality_and_streaming_geojson(tmp_path):
    features = [{"type": "Feature", "geometry": None, "properties": {
        "id_catastral": "P:R:1", "categoria_suelo": "rural", "tipo_padron_catastral": "rural",
        "codigo_localidad": None, "localidad": None, "padron": 1,
        "tiene_construccion_segun_catastro": None,
    }}]
    path = tmp_path / "source.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf8")
    stat = path.stat()
    _, records = _read_dataset(str(path), stat.st_mtime_ns, stat.st_size)
    assert len(select_records(records, {"category": "rural", "locality": "sin_localidad", "state": "desconocido"})) == 1
    assert not select_records(records, {"category": "rural", "locality": "sin_localidad", "state": "no"})
    assert not select_records(records, {"category": "rural", "locality": "sin_localidad", "state": "todos", "padron_desde": 2})
    assert len(select_records(records, {"category": "rural", "locality": "sin_localidad", "state": "todos", "padron_desde": 1, "padron_hasta": 1})) == 1


@pytest.mark.integration
def test_comparison_uses_results_of_its_own_batch(client, monkeypatch, tmp_path):
    user = login(client, "analyst")
    monkeypatch.setattr("app.routes.cadastre_compare.dispatch", lambda job: None)
    parcels, bounds = seed_many(3)
    for index, parcel in enumerate(parcels, 1):
        parcel.padron = str(index)
    db.session.commit()
    seed_result(parcels[0], user.id)
    scene, model = resources(bounds)
    features = []
    for index, declared in enumerate((False, True, None), 1):
        features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {
            "id_catastral": f"P:AA:{index}", "categoria_suelo": "urbano",
            "tipo_padron_catastral": "urbano_suburbano", "codigo_localidad": "AA", "localidad": "MINAS",
            "padron": index, "tiene_construccion_segun_catastro": declared, "tiene_registro_alfanumerico": True,
        }})
    path = tmp_path / "source.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf8")
    monkeypatch.setitem(current_app.config, "CATASTRE_GEOJSON", str(path))
    request = {"category": "urbano", "locality": "AA", "state": "todos",
               "scene_id": scene.id, "model_version_id": model.id, "device": "cpu"}
    preview = post(client, "/catastro-comparar/preview", request)
    assert preview.status_code == 200 and preview.json["available"] == 3
    limited = post(client, "/catastro-comparar/preview", {**request, "padron_desde": 2, "padron_hasta": 2})
    assert limited.status_code == 200 and limited.json["total"] == 1
    assert post(client, "/catastro-comparar/preview", {**request, "padron_desde": 3, "padron_hasta": 2}).status_code == 422
    response = post(client, "/catastro-comparar/runs", request)
    assert response.status_code == 202
    batch = response.json["batch"]
    first = client.get(f"/api/v1/catastro-comparar/runs/{batch['id']}").json
    assert first["summary"]["pendiente"] == 3  # prior current_result must never leak into this batch
    for parcel, state in zip(parcels, ("CON_CONSTRUCCION_VISIBLE", "SIN_CONSTRUCCION_VISIBLE", "INDETERMINADO")):
        item = db.session.scalar(select(BulkSelectionItem).where(BulkSelectionItem.selection_id == batch["id"],
                                 BulkSelectionItem.parcel_id == parcel.id))
        run = db.session.scalar(select(AnalysisRun).where(AnalysisRun.job_id == item.job_id))
        db.session.add(ParcelAnalysisResult(run_id=run.id, parcel_id=parcel.id, parcel_version_id=parcel.source_version_id,
                                          state=state, coverage=1, m2_huella_detectada=10))
    db.session.commit()
    detail = client.get(f"/api/v1/catastro-comparar/runs/{batch['id']}").json
    assert detail["summary"]["discrepancia"] == 2
    assert detail["summary"]["indeterminado"] == 1
    geo = client.get(f"/api/v1/catastro-comparar/runs/{batch['id']}/features?outcome=discrepancia").json
    assert len(geo["features"]) == 2
    assert all(feature["geometry"] for feature in geo["features"])
    bbox = ",".join(str(value) for value in bounds)
    assert len(client.get(f"/api/v1/catastro-comparar/runs/{batch['id']}/features?bbox={bbox}").json["features"]) == 3
    path.write_text(path.read_text(encoding="utf8") + " ", encoding="utf8")
    assert client.get(f"/api/v1/catastro-comparar/runs/{batch['id']}").status_code == 409
