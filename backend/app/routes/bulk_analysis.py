import hashlib
import json
from datetime import datetime, timezone
from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import select, func, update
from ..extensions import db
from ..models import (
    BulkSelection,
    BulkSelectionItem,
    Job,
    AnalysisRun,
    ImageryScene,
    AIModelVersion,
    SystemSetting,
    ParcelAnalysisResult,
)
from ..schemas import AnalysisSchema, load
from ..services.bulk_analysis import (
    selection_input,
    selection_rows,
    plan_chunks,
    skip_reason,
    batch_summary,
    job_query,
)
from ..services.queue import new_job, dispatch
from ..repositories.parcels import base_query, filters, serialize, ordered, FILTER_KEYS
from ..utils.security import require, audit

bp = Blueprint("bulk_analysis", __name__)


@bp.post("/bulk-selections/preview")
@require("read")
def preview():
    data = request.get_json()
    bounds, selected_filters = selection_input(data)
    total, rows = selection_rows(bounds, selected_filters)
    scene = db.get_or_404(ImageryScene, data["scene_id"]) if data.get("scene_id") else None
    eligible = [row for row in rows if scene is None or skip_reason(row, scene) is None]
    return jsonify(
        total=total,
        max_parcels=current_app.config["MAX_BULK_PARCELS"],
        can_analyze=0 < total <= current_app.config["MAX_BULK_PARCELS"],
        parcel_area_m2=sum(r.m2_parcela for r in rows),
        chunk_count=len(plan_chunks(rows)),
        unavailable_or_oversized=len(rows) - len(eligible),
        estimated_pixels=round(sum(r.crop_area / 0.2**2 for r in eligible)),
        bounds=bounds,
    )


@bp.route("/bulk-selections", methods=["GET", "POST"])
@require("read")
def selections():
    if request.method == "POST":
        return require("analyze")(create_selection)()
    rows = db.session.scalars(select(BulkSelection).order_by(BulkSelection.created_at.desc()).limit(100))
    return jsonify(items=[dict(id=b.id, name=b.name, total=b.total, created_at=b.created_at) for b in rows])


def create_selection():
    data = request.get_json()
    bounds, selected_filters = selection_input(data)
    if set(data) - {
        "bounds",
        "locality",
        "q",
        "name",
        "scene_id",
        "model_version_id",
        "probability",
        "min_area",
        "min_object_area",
        "min_occupancy",
        "min_coverage",
        "max_image_age_days",
    }:
        abort(422, "Parámetro de análisis múltiple no admitido.")
    name = data.get("name", "Selección múltiple")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        abort(422, "Use un nombre de entre 1 y 120 caracteres.")
    defaults = db.session.get(SystemSetting, "default_thresholds")
    options = load(
        AnalysisSchema(exclude=("parcel_ids",)),
        {
            **(defaults.value if defaults else {}),
            **{k: v for k, v in data.items() if k not in {"bounds", "locality", "q", "name"}},
        },
    )
    options = json.loads(json.dumps(options, default=str))
    scene = db.get_or_404(ImageryScene, options.pop("scene_id"))
    model = db.get_or_404(AIModelVersion, options.pop("model_version_id"))
    if not model.enabled:
        abort(409, "El modelo está deshabilitado.")
    payload = dict(
        name=name.strip(),
        bounds=bounds,
        selection_filters=selected_filters,
        scene_id=scene.id,
        model_version_id=model.id,
        parameters=options,
    )
    key = (
        request.headers.get("Idempotency-Key")
        or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    )
    if not 1 <= len(key) <= 64:
        abort(422, "Clave de idempotencia inválida.")
    db.session.execute(
        db.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"bulk:{current_user.id}:{key}"}
    )
    existing = db.session.scalar(
        select(BulkSelection).where(
            BulkSelection.user_id == current_user.id, BulkSelection.idempotency_key == key
        )
    )
    if existing:
        if existing.request_payload != payload:
            abort(409, "La clave ya corresponde a otra selección o parámetros.")
        return jsonify(batch=batch_summary(existing)), 202
    total, rows = selection_rows(bounds, selected_filters)
    if total == 0:
        abort(422, "No hay padrones activos dentro del rectángulo con estos filtros.")
    if total > current_app.config["MAX_BULK_PARCELS"]:
        abort(
            422,
            f"La selección contiene {total} padrones; el máximo por lote es {current_app.config['MAX_BULK_PARCELS']}. Reduzca el rectángulo.",
        )
    batch = BulkSelection(
        user_id=current_user.id,
        name=name.strip(),
        bounds=bounds,
        selection_filters=selected_filters,
        scene_id=scene.id,
        model_version_id=model.id,
        parameters=options,
        request_payload=payload,
        idempotency_key=key,
        total=total,
    )
    db.session.add(batch)
    db.session.flush()
    jobs = []
    for index, chunk in enumerate(plan_chunks(rows)):
        reasons = {row.id: reason for row in chunk if (reason := skip_reason(row, scene))}
        content = {
            **options,
            "scene_id": scene.id,
            "model_version_id": model.id,
            "bulk_id": batch.id,
            "parcel_ids": [row.id for row in chunk],
            "expected_versions": {row.id: row.source_version_id for row in chunk},
            "skip_reasons": reasons,
        }
        job, _ = new_job(
            "analysis", current_user.id, content, key=f"bulk:{batch.id}:{index}", total=len(chunk)
        )
        db.session.add(
            AnalysisRun(job_id=job.id, scene_id=scene.id, model_version_id=model.id, parameters=options)
        )
        for row in chunk:
            db.session.add(
                BulkSelectionItem(
                    selection_id=batch.id,
                    parcel_id=row.id,
                    parcel_version_id=row.source_version_id,
                    parcel_area_m2=row.m2_parcela,
                    job_id=job.id,
                )
            )
        jobs.append(job)
    audit("BULK_ANALYSIS_REQUEST", batch.id, {"parcels": total, "chunks": len(jobs), "bounds": bounds})
    db.session.commit()
    # The durable outbox dispatches the remainder; API work stays bounded for thousands of parcels.
    for job in jobs[:3]:
        dispatch(job)
    return jsonify(batch=batch_summary(batch)), 202


@bp.get("/bulk-selections/<identifier>")
@require("read")
def detail(identifier):
    return jsonify(batch=batch_summary(db.get_or_404(BulkSelection, identifier)))


@bp.get("/bulk-selections/<identifier>/results")
@require("read")
def results(identifier):
    db.get_or_404(BulkSelection, identifier)
    if set(request.args) - FILTER_KEYS - {"limit", "offset"} or request.args.get("comparison_id"):
        abort(422, "Filtro de lote no admitido.")
    params = {**request.args.to_dict(), "bulk_id": identifier}
    query = filters(base_query(bulk_id=identifier), params)
    scoped = query.with_only_columns(ParcelAnalysisResult.m2_huella_detectada).subquery()
    count, area = db.session.execute(
        select(func.count(), func.coalesce(func.sum(scoped.c.m2_huella_detectada), 0))
    ).one()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 250)
    offset = min(max(request.args.get("offset", 0, type=int), 0), 100000)
    rows = db.session.execute(
        ordered(query, request.args.get("sort", "footprint_desc")).limit(limit).offset(offset)
    ).all()
    return jsonify(
        items=[serialize(row, bulk=True) for row in rows],
        total_filtered=count,
        filtered_footprint_m2=area,
        next_offset=offset + limit if offset + len(rows) < count else None,
    )


@bp.post("/bulk-selections/<identifier>/cancel")
@require("analyze")
def cancel(identifier):
    batch = db.session.scalar(select(BulkSelection).where(BulkSelection.id == identifier).with_for_update())
    if not batch:
        abort(404)
    if batch.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}:
        abort(403)
    if batch.cancel_requested:
        return jsonify(batch=batch_summary(batch))
    if batch_summary(batch)["status"] not in {"QUEUED", "RUNNING"}:
        abort(409, "El lote ya terminó.")
    batch.cancel_requested = True
    ids = job_query(identifier).with_only_columns(Job.id).subquery()
    db.session.execute(
        update(Job)
        .where(Job.id.in_(select(ids.c.id)), Job.status.in_(["PENDING", "QUEUED"]))
        .values(status="CANCELLED", cancel_requested=True, finished_at=datetime.now(timezone.utc))
    )
    db.session.execute(
        update(Job).where(Job.id.in_(select(ids.c.id)), Job.status == "RUNNING").values(cancel_requested=True)
    )
    audit("BULK_CANCEL_REQUEST", identifier)
    db.session.commit()
    return jsonify(batch=batch_summary(batch))
