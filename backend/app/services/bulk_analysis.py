"""Server-side rectangular selection and bounded, durable analysis planning."""

import math
from flask import abort, current_app
from sqlalchemy import select, func
from shapely.geometry import box, mapping
from ..extensions import db
from ..models import Parcel, CadastralLocality, BulkSelectionItem, Job, ParcelAnalysisResult
from ..repositories.parcels import base_query
from .geospatial import validate_wgs84


def selection_input(data):
    if not isinstance(data, dict):
        abort(422, "Se esperaba un objeto JSON.")
    bounds = data.get("bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in bounds)
    ):
        abort(422, "Rectángulo inválido: indique oeste, sur, este y norte.")
    west, south, east, north = map(float, bounds)
    if not west < east or not south < north:
        abort(422, "El rectángulo debe tener una superficie positiva.")
    try:
        validate_wgs84(mapping(box(west, south, east, north)))
    except ValueError:
        abort(422, "El rectángulo debe estar dentro de Uruguay.")
    filters = {key: str(data.get(key) or "").strip() for key in ("locality", "q")}
    if len(filters["locality"]) > 40 or len(filters["q"]) > 80:
        abort(422, "Filtro de selección demasiado largo.")
    return [west, south, east, north], filters


def candidates(bounds, filters):
    crop = func.ST_Area(func.ST_Expand(func.ST_Envelope(func.ST_Transform(Parcel.geom, 5382)), 8))
    query = (
        select(Parcel.id, Parcel.source_version_id, Parcel.m2_parcela, crop.label("crop_area"), Parcel.geom)
        .join(CadastralLocality, Parcel.locality_id == CadastralLocality.id)
        .where(Parcel.active.is_(True), func.ST_Intersects(Parcel.geom, func.ST_MakeEnvelope(*bounds, 4326)))
    )
    if filters.get("locality"):
        query = query.where(Parcel.codloccat == filters["locality"])
    if filters.get("q"):
        query = query.where(Parcel.padron.ilike(f"%{filters['q']}%"))
    return query.order_by(Parcel.codloccat, Parcel.padron, Parcel.id)


def selection_rows(bounds, filters):
    query = candidates(bounds, filters)
    total = db.session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    maximum = current_app.config["MAX_BULK_PARCELS"]
    if total > maximum:
        return total, []
    return total, list(db.session.execute(query).all())


def plan_chunks(rows):
    maximum = min(current_app.config["MAX_ANALYSIS_PARCELS"], max(1, current_app.config["BULK_CHUNK_SIZE"]))
    area_limit = current_app.config["MAX_ANALYSIS_AREA"]
    chunks = []
    chunk = []
    area = 0
    for row in rows:
        cost = (
            0
            if row.crop_area > area_limit or row.crop_area / 0.2**2 > current_app.config["MAX_RASTER_PIXELS"]
            else float(row.crop_area)
        )
        if chunk and (len(chunk) >= maximum or area + cost > area_limit):
            chunks.append(chunk)
            chunk = []
            area = 0
        chunk.append(row)
        area += cost
    if chunk:
        chunks.append(chunk)
    return chunks


def skip_reason(row, scene):
    if (
        row.crop_area > current_app.config["MAX_ANALYSIS_AREA"]
        or row.crop_area / 0.2**2 > current_app.config["MAX_RASTER_PIXELS"]
    ):
        return "La parcela supera el área o tamaño de recorte permitido para una inferencia."
    coverage = scene.metadata_json.get("bounds_wgs84")
    if coverage:
        from geoalchemy2.shape import to_shape

        if not to_shape(row.geom).intersects(box(*coverage)):
            return "Sin cobertura de imagen registrada para esta parcela."
    return None


def job_query(identifier):
    return select(Job).where(
        Job.id.in_(select(BulkSelectionItem.job_id).where(BulkSelectionItem.selection_id == identifier))
    )


def batch_summary(batch):
    jobs = list(db.session.scalars(job_query(batch.id)))
    query = base_query(bulk_id=batch.id).with_only_columns(
        ParcelAnalysisResult.state,
        func.count(),
        func.coalesce(func.sum(ParcelAnalysisResult.m2_huella_detectada), 0),
    )
    grouped = db.session.execute(query.group_by(ParcelAnalysisResult.state)).all()
    states = {state or "NO_ANALIZADO": count for state, count, _ in grouped}
    processed = batch.total - states.get("NO_ANALIZADO", 0)
    active = any(j.status in {"PENDING", "QUEUED", "RUNNING"} for j in jobs)
    if batch.cancel_requested:
        status = "CANCELLING" if active else "CANCELLED"
    elif any(j.status == "RUNNING" for j in jobs):
        status = "RUNNING"
    elif active:
        status = "QUEUED"
    elif any(j.status == "FAILED" for j in jobs) or states.get("ERROR_ANALISIS", 0):
        status = "PARTIAL" if processed else "FAILED"
    elif any(j.status == "CANCELLED" for j in jobs):
        status = "PARTIAL" if processed else "CANCELLED"
    elif states.get("NO_ANALIZADO", 0):
        status = "PARTIAL" if processed else "FAILED"
    else:
        status = "COMPLETED"
    return dict(
        id=batch.id,
        name=batch.name,
        bounds=batch.bounds,
        total=batch.total,
        created_at=batch.created_at,
        scene_id=batch.scene_id,
        model_version_id=batch.model_version_id,
        parameters=batch.parameters,
        selection_filters=batch.selection_filters,
        states=states,
        processed=processed,
        status=status,
        footprint_m2=sum(float(area) for _, _, area in grouped),
        cancel_requested=batch.cancel_requested,
        jobs=[j.public() for j in jobs],
    )
