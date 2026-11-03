"""Compare the cadastral declaration against a newly scheduled analysis batch."""
from __future__ import annotations

import json
import math
import uuid
from collections import Counter

from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import and_, func, select

from ..extensions import db
from ..models import (AIModelVersion, AnalysisRun, BulkSelection, BulkSelectionItem, ImageryScene,
                      Job, Parcel, ParcelAnalysisResult, SystemSetting)
from ..repositories.parcels import parcel_geometry
from ..schemas import AnalysisSchema, load
from ..services.bulk_analysis import batch_summary, plan_chunks
from ..services.cadastre_compare import dataset, options, outcome, parcel_rows, reason, select_records, selection_filters
from ..services.queue import dispatch, new_job
from ..utils.security import audit, require

bp = Blueprint("cadastre_compare", __name__)


def _scene(data):
    return db.get_or_404(ImageryScene, data["scene_id"]) if data.get("scene_id") else None


def _preview(data):
    filters = selection_filters(data)
    digest, all_records = dataset()
    selected = select_records(all_records, filters)
    scene = _scene(data)
    mapped = parcel_rows({item["key"]: item for item in selected}, scene)
    no_geom = sum(not item["has_geometry"] and item["key"] not in mapped for item in selected)
    unmatched = sum(item["has_geometry"] and item["key"] not in mapped for item in selected)
    oversized = sum(bool(reason(row)) and "supera" in reason(row) for row in mapped.values())
    uncovered = sum(bool(reason(row)) and "cobertura" in reason(row) for row in mapped.values())
    available = len(mapped) - oversized - uncovered
    limit = current_app.config["MAX_BULK_PARCELS"]
    summary = dict(total=len(selected), available=available, unavailable=len(selected)-available,
                   sin_geometria=no_geom, no_conciliados=unmatched, fuera_cobertura=uncovered,
                   supera_limites=oversized, max_parcels=limit,
                   lineas_sin_resumen=sum(item["orphan_lines"] for item in selected),
                   can_analyze=bool(scene and available and available <= limit),
                   mapped=len(mapped), dataset_sha256=digest)
    return filters, selected, mapped, summary


@bp.get("/catastro-comparar/options")
@require("read")
def compare_options():
    _, records = dataset()
    return jsonify(options(records, request.args.get("category", "todos")))


@bp.post("/catastro-comparar/preview")
@require("read")
def compare_preview():
    return jsonify(_preview(request.get_json())[3])


@bp.post("/catastro-comparar/runs")
@require("analyze")
def compare_start():
    supplied = request.get_json()
    if not isinstance(supplied, dict):
        abort(422, "Se esperaba un objeto JSON.")
    allowed = {"category", "locality", "state", "padron_desde", "padron_hasta", "scene_id", "model_version_id", "device", "probability",
               "min_area", "min_object_area", "min_occupancy", "min_coverage", "max_image_age_days"}
    if set(supplied) - allowed:
        abort(422, "Parámetro de comparación no admitido.")
    defaults = db.session.get(SystemSetting, "default_thresholds")
    params = load(AnalysisSchema(exclude=("parcel_ids",)),
                  {**(defaults.value if defaults else {}), **{k: v for k, v in supplied.items() if k not in {"category", "locality", "state", "padron_desde", "padron_hasta"}}})
    params = json.loads(json.dumps(params, default=str))
    scene = db.get_or_404(ImageryScene, params.pop("scene_id"))
    model = db.get_or_404(AIModelVersion, params.pop("model_version_id"))
    if not model.enabled:
        abort(409, "El modelo está deshabilitado.")
    filters, selected, mapped, preview = _preview({**supplied, "scene_id": scene.id})
    if preview["available"] > current_app.config["MAX_BULK_PARCELS"]:
        abort(422, f"La selección tiene {preview['available']} padrones aptos; el máximo por lote es {current_app.config['MAX_BULK_PARCELS']}. Reduzca los filtros.")
    if not preview["available"]:
        abort(422, "Ningún padrón seleccionado dispone de geometría utilizable e imagen dentro de los límites de análisis.")
    payload = dict(filters=filters, scene_id=scene.id, model_version_id=model.id, parameters=params,
                   dataset_sha256=preview["dataset_sha256"])
    key = request.headers.get("Idempotency-Key") or uuid.uuid4().hex
    if not 1 <= len(key) <= 64:
        abort(422, "Clave de idempotencia inválida.")
    db.session.execute(db.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"compare:{current_user.id}:{key}"})
    old = db.session.scalar(select(BulkSelection).where(BulkSelection.user_id == current_user.id,
                            BulkSelection.idempotency_key == key))
    if old:
        if old.request_payload != payload:
            abort(409, "La clave ya corresponde a otra selección o parámetros.")
        return jsonify(batch=batch_summary(old), preview=old.selection_filters.get("preview")), 202
    eligible = [row for row in mapped.values() if reason(row) is None]
    extent = func.ST_Extent(Parcel.geom)
    bounds = db.session.execute(select(func.ST_XMin(extent), func.ST_YMin(extent),
                                       func.ST_XMax(extent), func.ST_YMax(extent)).where(
        Parcel.id.in_([row.id for row in eligible]))).one()
    batch = BulkSelection(user_id=current_user.id, name="Comparación con Catastro", bounds=list(bounds),
                          selection_filters={**filters, "dataset_sha256": preview["dataset_sha256"], "preview": preview,
                                             "source": "cadastre_compare"},
                          scene_id=scene.id, model_version_id=model.id, parameters=params,
                          request_payload=payload, idempotency_key=key, total=len(eligible))
    db.session.add(batch)
    db.session.flush()
    jobs = []
    for index, chunk in enumerate(plan_chunks(eligible)):
        content = {**params, "scene_id": scene.id, "model_version_id": model.id, "bulk_id": batch.id,
                   "parcel_ids": [row.id for row in chunk],
                   "expected_versions": {row.id: row.source_version_id for row in chunk},
                   "skip_reasons": {row.id: why for row in chunk if (why := reason(row))}}
        job, _ = new_job("analysis", current_user.id, content, key=f"bulk:{batch.id}:{index}", total=len(chunk))
        db.session.add(AnalysisRun(job_id=job.id, scene_id=scene.id, model_version_id=model.id, parameters=params))
        for row in chunk:
            db.session.add(BulkSelectionItem(selection_id=batch.id, parcel_id=row.id,
                                            parcel_version_id=row.source_version_id,
                                            parcel_area_m2=row.m2_parcela, job_id=job.id))
        jobs.append(job)
    audit("CADASTRE_COMPARE_REQUEST", batch.id, {"selected": len(selected), "mapped": len(mapped), "preview": preview})
    db.session.commit()
    for job in jobs[:3]:
        dispatch(job)
    return jsonify(batch=batch_summary(batch), preview=preview), 202


@bp.get("/catastro-comparar/runs")
@require("read")
def compare_history():
    batches = db.session.scalars(select(BulkSelection).where(
        BulkSelection.selection_filters["source"].as_string() == "cadastre_compare"
    ).order_by(BulkSelection.created_at.desc(), BulkSelection.id).limit(30)).all()
    return jsonify(items=[batch_summary(batch) for batch in batches])


def _batch(identifier):
    batch = db.get_or_404(BulkSelection, identifier)
    if batch.selection_filters.get("source") != "cadastre_compare":
        abort(404)
    digest, records = dataset()
    if batch.selection_filters.get("dataset_sha256") != digest:
        abort(409, "La referencia catastral cambió desde esta comparación; restaure el archivo original.")
    return batch, records


def _rows(identifier, geometry=False, bbox=None):
    run = select(AnalysisRun.id).where(AnalysisRun.job_id == BulkSelectionItem.job_id).correlate(BulkSelectionItem).scalar_subquery()
    cols = [Parcel.id, Parcel.codloccat, Parcel.padron, BulkSelectionItem.job_id, Job.status,
            ParcelAnalysisResult]
    # Wrap the scalar geometry subquery: GeoAlchemy otherwise treats a
    # SELECT as the record overload of ST_AsGeoJSON.
    geom = func.ST_Multi(parcel_geometry(True))
    if geometry:
        cols.append(func.ST_AsGeoJSON(geom).label("geometry"))
    query = (select(*cols).select_from(BulkSelectionItem)
             .join(Parcel, Parcel.id == BulkSelectionItem.parcel_id)
             .join(Job, Job.id == BulkSelectionItem.job_id)
             .outerjoin(ParcelAnalysisResult, and_(ParcelAnalysisResult.parcel_id == Parcel.id,
                                                  ParcelAnalysisResult.run_id == run))
             .where(BulkSelectionItem.selection_id == identifier))
    if bbox:
        query = query.where(func.ST_Intersects(geom, func.ST_MakeEnvelope(*bbox, 4326)))
    return db.session.execute(query).all()


def _feature_props(row, records):
    parcel_id, loc, number, _, job_status, result = row[:6]
    ref = records.get((loc, number))
    if not ref:
        abort(409, "La identidad del padrón ya no existe en la referencia catastral.")
    result_outcome = outcome(ref["declared_building"], result)
    if result_outcome == "pendiente" and job_status in {"FAILED", "CANCELLED"}:
        result_outcome = "indeterminado"
    return dict(id=parcel_id, parcel_id=parcel_id, padron=number, locality=ref["localidad"],
                codigo_localidad=ref["codigo_localidad"], categoria_suelo=ref["categoria_suelo"],
                declared_building=ref["declared_building"], model_state=result.state if result else "NO_ANALIZADO",
                outcome=result_outcome, m2_huella_detectada=result.m2_huella_detectada if result else None,
                result_id=result.id if result else None, coverage=result.coverage if result else None,
                error=result.error if result else None, processing_status=job_status,
                tiene_registro_alfanumerico=ref["has_summary"], lineas_sin_resumen=ref["orphan_lines"])


@bp.get("/catastro-comparar/runs/<identifier>")
@require("read")
def compare_detail(identifier):
    batch, records = _batch(identifier)
    counts = Counter(_feature_props(row, records)["outcome"] for row in _rows(identifier))
    summary = {key: counts[key] for key in ("discrepancia", "coincide", "sin_referencia", "indeterminado", "pendiente")}
    summary["total"] = sum(counts.values())
    return jsonify(batch=batch_summary(batch), summary=summary, preview=batch.selection_filters.get("preview"))


@bp.get("/catastro-comparar/runs/<identifier>/features")
@require("read")
def compare_features(identifier):
    _, records = _batch(identifier)
    bbox = request.args.get("bbox")
    if bbox:
        try:
            bbox = [float(v) for v in bbox.split(",")]
            if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox) or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                raise ValueError()
        except ValueError:
            abort(422, "Extensión geográfica inválida.")
    wanted = request.args.get("outcome", "todos")
    if wanted not in {"todos", "discrepancia", "coincide", "sin_referencia", "indeterminado", "pendiente"}:
        abort(422, "Filtro de resultado inválido.")
    features = []
    for row in _rows(identifier, geometry=True, bbox=bbox):
        props = _feature_props(row, records)
        if wanted == "todos" or props["outcome"] == wanted:
            features.append(dict(type="Feature", id=props["id"], geometry=json.loads(row[-1]) if row[-1] else None, properties=props))
    return jsonify(type="FeatureCollection", features=features)
