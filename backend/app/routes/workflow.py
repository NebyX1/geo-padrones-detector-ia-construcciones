import hashlib
import io
import json
import math
from collections import Counter
from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user
from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy import select, func
from ..extensions import db
from ..models import (
    Parcel,
    ImageryScene,
    AIModelVersion,
    Job,
    AnalysisRun,
    ParcelAnalysisResult,
    ImportBatch,
    ImportMapping,
    ImportedParcelDeclaration,
    ComparisonRun,
    ParcelComparisonResult,
    ReviewCase,
    ReviewAction,
    SystemSetting,
)
from ..schemas import AnalysisSchema, ReviewSchema, load
from ..services.queue import new_job, dispatch
from ..services.storage import storage
from ..services.csv_import import preview, reconcile, validate_mapping, csv_reader
from ..services.geospatial import validate_wgs84, reproject, multipolygon
from ..utils.security import require, audit

bp = Blueprint("workflow", __name__)


def pagination():
    return min(max(request.args.get("limit", 50, type=int), 1), 250), max(
        request.args.get("offset", 0, type=int), 0
    )


@bp.post("/analysis/jobs")
@require("analyze")
def create_analysis():
    supplied = request.get_json()
    defaults = db.session.get(SystemSetting, "default_thresholds")
    data = load(
        AnalysisSchema(),
        {**(defaults.value if defaults else {}), **supplied} if isinstance(supplied, dict) else supplied,
    )
    data = json.loads(json.dumps(data, default=str))
    ids = list(dict.fromkeys(data["parcel_ids"]))
    scene, model = (
        db.get_or_404(ImageryScene, data["scene_id"]),
        db.get_or_404(AIModelVersion, data["model_version_id"]),
    )
    if not model.enabled:
        abort(409, "El modelo está deshabilitado.")
    count, area = db.session.execute(
        select(func.count(Parcel.id), func.sum(Parcel.m2_parcela)).where(
            Parcel.id.in_(ids), Parcel.active.is_(True)
        )
    ).one()
    from flask import current_app

    if count != len(ids):
        abort(422, "La selección contiene parcelas inexistentes o inactivas.")
    if count > current_app.config["MAX_ANALYSIS_PARCELS"] or area > current_app.config["MAX_ANALYSIS_AREA"]:
        abort(422, "La selección supera los límites operativos de parcelas o superficie.")
    data["parcel_ids"] = ids
    job, created = new_job(
        "analysis", current_user.id, data, request.headers.get("Idempotency-Key"), len(ids)
    )
    if created:
        db.session.add(
            AnalysisRun(
                job_id=job.id,
                model_version_id=model.id,
                scene_id=scene.id,
                parameters={
                    k: v for k, v in data.items() if k not in {"parcel_ids", "scene_id", "model_version_id"}
                },
            )
        )
        audit("ANALYSIS_REQUEST", job.id, {"parcels": len(ids)})
    db.session.commit()
    dispatch(job)
    return jsonify(job=job.public()), 202


@bp.get("/analysis/jobs")
@require("read")
def jobs():
    limit, offset = pagination()
    from ..repositories.worklists import job_query, count

    query = job_query(request.args)
    total = count(query)
    records = db.session.execute(
        query.add_columns(AnalysisRun, AIModelVersion.model_id)
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return jsonify(
        items=[
            {
                **job.public(),
                "model_id": model,
                "model_version_id": run.model_version_id if run else None,
                "device": run.parameters.get("device", "cpu") if run else None,
            }
            for job, run, model in records
        ],
        total=total,
        next_offset=offset + limit if offset + len(records) < total else None,
    )


@bp.get("/analysis/jobs/<identifier>")
@require("read")
def job_detail(identifier):
    job = db.get_or_404(Job, identifier)
    run = db.session.execute(select(AnalysisRun).where(AnalysisRun.job_id == job.id)).scalar_one_or_none()
    return jsonify(job=job.public(), run_id=run.id if run else None)


@bp.post("/analysis/jobs/<identifier>/cancel")
@require("analyze")
def cancel_job(identifier):
    job = db.session.execute(select(Job).where(Job.id == identifier).with_for_update()).scalar_one_or_none()
    if not job:
        abort(404)
    if current_user.id != job.user_id and current_user.role not in {"admin", "superadmin"}:
        abort(403)
    if job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
        abort(409, "El proceso ya terminó.")
    job.cancel_requested = True
    audit("JOB_CANCEL_REQUEST", job.id)
    db.session.commit()
    return jsonify(job=job.public())


@bp.get("/analysis/runs/<identifier>/results")
@require("read")
def run_results(identifier):
    db.get_or_404(AnalysisRun, identifier)
    limit, offset = pagination()
    rows = db.session.execute(
        select(ParcelAnalysisResult)
        .where(ParcelAnalysisResult.run_id == identifier)
        .order_by(ParcelAnalysisResult.id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return jsonify(
        items=[
            dict(
                id=r.id,
                parcel_id=r.parcel_id,
                state=r.state,
                m2_huella_detectada=r.m2_huella_detectada,
                coverage=r.coverage,
                confidence=r.confidence,
                error=r.error,
            )
            for r in rows
        ]
    )


@bp.get("/analysis/results/<identifier>/mask")
@require("read")
def result_mask(identifier):
    result = db.get_or_404(ParcelAnalysisResult, identifier)
    if not result.mask_key:
        abort(404)
    return send_file(
        io.BytesIO(storage().get(result.mask_key)),
        mimetype="image/tiff",
        as_attachment=True,
        download_name="mascara-georreferenciada.tif",
    )


@bp.get("/analysis/results/<identifier>/overlay.json")
@require("read")
def mask_metadata(identifier):
    result = db.get_or_404(ParcelAnalysisResult, identifier)
    if not result.mask_key:
        abort(404)
    try:
        bounds = json.loads(storage().get(result.mask_key + ".json"))
    except Exception:
        abort(404, "Reprocese este resultado para generar la previsualización de máscara.")
    return jsonify(bounds=bounds, url=f"/api/v1/analysis/results/{identifier}/overlay.png")


@bp.get("/analysis/results/<identifier>/overlay.png")
@require("read")
def mask_image(identifier):
    result = db.get_or_404(ParcelAnalysisResult, identifier)
    if not result.mask_key:
        abort(404)
    return send_file(io.BytesIO(storage().get(result.mask_key + ".png")), mimetype="image/png")


@bp.post("/imports/csv")
@require("import")
def upload_csv():
    upload = request.files.get("file")
    if not upload or not (upload.filename or "").lower().endswith((".csv", ".tsv")):
        abort(422, "Seleccione un archivo CSV o TSV.")
    options = {"encoding": request.form.get("encoding", "utf-8-sig")}
    raw = upload.read()
    try:
        sample = preview(raw, options)
    except (ValueError, UnicodeError) as exc:
        abort(422, str(exc))
    from werkzeug.utils import secure_filename

    digest = hashlib.sha256(raw).hexdigest()
    batch = ImportBatch(
        user_id=current_user.id,
        filename=secure_filename(upload.filename)[:200],
        sha256=digest,
        object_key=f"imports/{current_user.id}/{digest}.csv",
        options={**options, "delimiter": sample["delimiter"]},
    )
    try:
        storage().put(batch.object_key, raw, "text/csv")
    except ValueError as exc:
        abort(413, str(exc))
    db.session.add(batch)
    db.session.flush()
    audit("IMPORT_UPLOAD", batch.id, {"sha256": digest})
    db.session.commit()
    return jsonify(id=batch.id, preview=sample), 201


@bp.get("/imports")
@require("read")
def imports():
    limit, offset = pagination()
    rows = db.session.execute(
        select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return jsonify(
        items=[
            dict(
                id=b.id,
                filename=b.filename,
                status=b.status,
                summary=b.summary,
                created_at=b.created_at,
                job_id=b.job_id,
            )
            for b in rows
        ]
    )


@bp.get("/imports/<identifier>")
@require("read")
def import_detail(identifier):
    batch = db.get_or_404(ImportBatch, identifier)
    limit, offset = pagination()
    rows = db.session.execute(
        select(ImportedParcelDeclaration)
        .where(ImportedParcelDeclaration.batch_id == identifier)
        .order_by(ImportedParcelDeclaration.row_number)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return jsonify(
        id=batch.id,
        filename=batch.filename,
        status=batch.status,
        summary=batch.summary,
        mapping=batch.mapping,
        job_id=batch.job_id,
        options=batch.options,
        items=[
            dict(
                id=r.id,
                row=r.row_number,
                parcel_id=r.parcel_id,
                key=r.key,
                declared_building=r.declared_building,
                declared_m2=r.declared_m2,
                issues=r.issues,
            )
            for r in rows
        ],
    )


@bp.post("/imports/<identifier>/validate")
@require("import")
def validate_import(identifier):
    batch = db.get_or_404(ImportBatch, identifier)
    if batch.status != "PREVIEW":
        abort(409, "Este lote ya fue confirmado.")
    data = request.get_json() or {}
    options = {**batch.options, **data.get("options", {})}
    mapping = data.get("mapping", {})
    try:
        records = []
        # Preview is bounded; full validation runs asynchronously when confirmed.
        for index, row in enumerate(reconcile(storage().get(batch.object_key), mapping, options)):
            if index == 100:
                break
            records.append({k: v for k, v in row.items() if k != "original"})
    except (ValueError, UnicodeError) as exc:
        abort(422, str(exc))
    batch.mapping, batch.options = mapping, options
    db.session.commit()
    return jsonify(
        items=records,
        preview_only=True,
        sampled=len(records),
        summary=dict(Counter("issues" if r["issues"] else "matched" for r in records)),
    )


@bp.post("/imports/<identifier>/confirm")
@require("import")
def confirm_import(identifier):
    batch = db.session.execute(
        select(ImportBatch).where(ImportBatch.id == identifier).with_for_update()
    ).scalar_one_or_none()
    if not batch:
        abort(404)
    if batch.job_id:
        return jsonify(job=db.session.get(Job, batch.job_id).public()), 202
    try:
        _, columns, _ = csv_reader(storage().get(batch.object_key), batch.options)
        validate_mapping(batch.mapping, columns)
    except ValueError as exc:
        abort(422, str(exc))
    job, _ = new_job("import", current_user.id, {"batch_id": batch.id}, key=batch.id)
    batch.job_id, batch.status = job.id, "QUEUED"
    audit("IMPORT_CONFIRM", batch.id)
    db.session.commit()
    dispatch(job)
    return jsonify(job=job.public()), 202


@bp.route("/imports/mappings", methods=["GET", "POST"])
@require("import")
def mappings():
    if request.method == "POST":
        data = request.get_json() or {}
        if not isinstance(data.get("mapping"), dict) or not 1 <= len(str(data.get("name", ""))) <= 100:
            abort(422)
        row = ImportMapping(
            user_id=current_user.id,
            name=data["name"],
            mapping=data["mapping"],
            options=data.get("options", {}),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify(id=row.id), 201
    return jsonify(
        items=[
            dict(id=m.id, name=m.name, mapping=m.mapping, options=m.options)
            for m in db.session.execute(
                select(ImportMapping).where(ImportMapping.user_id == current_user.id)
            ).scalars()
        ]
    )


@bp.post("/comparisons")
@require("import")
def create_comparison():
    data = request.get_json() or {}
    batch = db.get_or_404(ImportBatch, data.get("batch_id"))
    if batch.status != "CONFIRMED":
        abort(409, "Espere a que termine la conciliación del CSV.")
    parameters = {}
    for key in ["absolute_tolerance", "percent_tolerance"]:
        try:
            value = float(data.get(key, 20))
            if not math.isfinite(value) or not 0 <= value <= 100000:
                raise ValueError()
        except (TypeError, ValueError):
            abort(422, "Tolerancia inválida.")
        parameters[key] = value
    parameters["comparable_area"] = data.get("comparable_area") is True
    payload = {"batch_id": batch.id, **parameters}
    job, created = new_job("comparison", current_user.id, payload, request.headers.get("Idempotency-Key"))
    if created:
        run = ComparisonRun(batch_id=batch.id, user_id=current_user.id, parameters=parameters, job_id=job.id)
        db.session.add(run)
        db.session.flush()
        audit("COMPARISON_REQUEST", run.id)
    else:
        run = db.session.execute(select(ComparisonRun).where(ComparisonRun.job_id == job.id)).scalar_one()
    db.session.commit()
    dispatch(job)
    return jsonify(id=run.id, job=job.public()), 202


@bp.get("/comparisons")
@require("read")
def comparisons():
    rows = db.session.execute(
        select(ComparisonRun).order_by(ComparisonRun.created_at.desc()).limit(100)
    ).scalars()
    return jsonify(
        items=[dict(id=r.id, batch_id=r.batch_id, created_at=r.created_at, job_id=r.job_id) for r in rows]
    )


@bp.get("/comparisons/<identifier>")
@bp.get("/comparisons/<identifier>/results")
@require("read")
def comparison_results(identifier):
    run = db.get_or_404(ComparisonRun, identifier)
    query = (
        select(ParcelComparisonResult, ImportedParcelDeclaration)
        .join(
            ImportedParcelDeclaration, ImportedParcelDeclaration.id == ParcelComparisonResult.declaration_id
        )
        .where(ParcelComparisonResult.run_id == identifier)
    )
    if request.args.get("state"):
        query = query.where(ParcelComparisonResult.state == request.args["state"])
    limit, offset = pagination()
    rows = db.session.execute(
        query.order_by(ImportedParcelDeclaration.row_number).limit(limit + 1).offset(offset)
    ).all()
    summary = dict(
        db.session.execute(
            select(ParcelComparisonResult.state, func.count())
            .where(ParcelComparisonResult.run_id == identifier)
            .group_by(ParcelComparisonResult.state)
        ).all()
    )
    return jsonify(
        id=run.id,
        job=db.session.get(Job, run.job_id).public(),
        summary=summary,
        next_offset=offset + limit if len(rows) > limit else None,
        items=[
            dict(
                id=c.id,
                parcel_id=d.parcel_id,
                key=d.key,
                state=c.state,
                declared_building=d.declared_building,
                declared_m2=d.declared_m2,
                difference_m2=c.difference_m2,
                warning=c.warning,
            )
            for c, d in rows[:limit]
        ],
    )


@bp.get("/reviews")
@require("read")
def reviews():
    limit, offset = pagination()
    from ..repositories.worklists import review_query, count

    query = review_query(request.args)
    total = count(query)
    rows = db.session.execute(
        query.order_by(ReviewCase.created_at.desc(), ReviewCase.id).limit(limit).offset(offset)
    ).all()
    return jsonify(
        items=[
            dict(
                id=c.id,
                status=c.status,
                version=c.version,
                result_id=r.id,
                parcel_id=p.id,
                padron=p.padron,
                state=r.state,
                m2_huella_detectada=r.m2_huella_detectada,
                needs_reanalysis=c.needs_reanalysis,
                locality=locality,
                codloccat=p.codloccat,
                model_id=model,
                created_at=r.created_at,
                device=params.get("device", "cpu"),
            )
            for c, r, p, locality, model, params in rows
        ],
        total=total,
        next_offset=offset + limit if offset + len(rows) < total else None,
    )


@bp.patch("/reviews/<identifier>")
@require("review")
def review_case(identifier):
    data = load(ReviewSchema(), request.get_json())
    case = db.session.execute(
        select(ReviewCase).where(ReviewCase.id == identifier).with_for_update()
    ).scalar_one_or_none()
    if not case:
        abort(404)
    if case.version != data["version"]:
        abort(409, "Otro revisor actualizó este caso. Recargue antes de guardar.")
    result = db.session.get(ParcelAnalysisResult, case.result_id)
    from ..services.reviews import original_geometry

    boundary = to_shape(original_geometry(result))
    if data["status"] == "CONFIRMADO" and data["state"] != result.state:
        abort(422, "Para cambiar el resultado utilice CORREGIDO o RECHAZADO.")
    geom, area = None, None
    if data.get("geometry"):
        try:
            geom = multipolygon(validate_wgs84(data["geometry"]).intersection(boundary))
            area = reproject(geom).area
        except ValueError as exc:
            abort(422, str(exc))
        if geom.is_empty and data["state"] == "CON_CONSTRUCCION_VISIBLE":
            abort(422, "La huella corregida no intersecta la parcela.")
    elif data["status"] == "CORREGIDO" and data["state"] == "CON_CONSTRUCCION_VISIBLE":
        abort(422, "Dibuje la huella corregida para calcular su superficie.")
    if data["state"] == "SIN_CONSTRUCCION_VISIBLE" and area and area > 0:
        abort(422, "Un resultado sin construcción no puede contener una huella.")
    case.version += 1
    case.status = data["status"]
    case.assigned_to = current_user.id
    action = ReviewAction(
        case_id=case.id,
        user_id=current_user.id,
        status=data["status"],
        state=data["state"],
        observations=data["observations"],
        corrected_geom=from_shape(geom, srid=4326) if geom is not None else None,
        corrected_m2=area
        if area is not None
        else (0 if data["state"] == "SIN_CONSTRUCCION_VISIBLE" else None),
        version=case.version,
    )
    db.session.add(action)
    audit(
        "REVIEW_ACTION",
        case.id,
        {"version": case.version, "status": case.status, "original_result": result.id},
    )
    db.session.commit()
    return jsonify(id=case.id, status=case.status, version=case.version)


@bp.post("/exports")
@require("export")
def create_export():
    data = request.get_json() or {}
    if data.get("format", "csv") not in {"csv", "geojson"} or not isinstance(data.get("filters", {}), dict):
        abort(422)
    from ..repositories.parcels import FILTER_KEYS

    allowed = FILTER_KEYS
    if set(data.get("filters", {})) - allowed:
        abort(422, "Filtro no admitido.")
    values = data.get("filters", {})
    if values.get("bulk_id"):
        from ..models import BulkSelection

        db.get_or_404(BulkSelection, values["bulk_id"])
        if values.get("comparison_id") or values.get("comparison_state"):
            abort(422, "Exporte la selección múltiple y la comparación por separado.")
    for key, value in values.items():
        if key == "ids":
            if not isinstance(value, (str, list)) or (
                isinstance(value, list) and (len(value) > 10000 or any(not isinstance(v, str) for v in value))
            ):
                abort(422, "Selección inválida.")
        elif value is not None and not isinstance(value, (str, int, float)):
            abort(422, "Tipo de filtro inválido.")
    from ..repositories.parcels import filters, base_query

    filters(base_query(bulk_id=values.get("bulk_id")), values)  # Validate filters before durable enqueue.
    job, _ = new_job("export", current_user.id, data, request.headers.get("Idempotency-Key"))
    audit("EXPORT_REQUEST", job.id, {"filters": data.get("filters", {})})
    db.session.commit()
    dispatch(job)
    return jsonify(job=job.public()), 202


@bp.get("/exports/<identifier>")
@require("export")
def export_status(identifier):
    job = db.get_or_404(Job, identifier)
    if job.kind != "export" or (
        job.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}
    ):
        abort(403)
    return jsonify(job=job.public())


@bp.get("/exports/<identifier>/download")
@require("export")
def download_export(identifier):
    job = db.get_or_404(Job, identifier)
    if job.kind != "export" or (
        job.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}
    ):
        abort(403)
    if job.status != "COMPLETED" or not job.output_key:
        abort(409, "La exportación todavía no está disponible.")
    audit("EXPORT_DOWNLOAD", job.id)
    db.session.commit()
    file_format = job.payload.get("format", "csv")
    return send_file(
        io.BytesIO(storage().get(job.output_key)),
        as_attachment=True,
        mimetype="text/csv" if file_format == "csv" else "application/geo+json",
        download_name=f"geopadrones-{job.id}.{file_format}",
    )
