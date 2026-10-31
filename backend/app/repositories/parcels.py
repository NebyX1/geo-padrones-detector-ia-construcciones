import json
import math
from flask import abort
from sqlalchemy import select, func, or_, case, cast, Numeric, exists
from ..models import (
    Parcel,
    CadastralLocality,
    ParcelAnalysisResult,
    ReviewCase,
    ReviewAction,
    AnalysisRun,
    ImageryScene,
    LandUseCategory,
    ImportedParcelDeclaration,
    ParcelComparisonResult,
    BulkSelectionItem,
    ParcelGeometryVersion,
    Job,
)

FILTER_KEYS = {
    "locality",
    "q",
    "state",
    "min_area",
    "max_area",
    "bbox",
    "ids",
    "review_status",
    "department",
    "padron_from",
    "padron_to",
    "min_coverage",
    "min_confidence",
    "min_occupancy",
    "max_occupancy",
    "min_buildings",
    "max_buildings",
    "image_from",
    "image_to",
    "analyzed_from",
    "analyzed_to",
    "model_version_id",
    "batch_id",
    "land_use",
    "assigned_to",
    "has_notes",
    "comparison_id",
    "comparison_state",
    "bulk_id",
    "sort",
}


def filters(query, params):
    if params.get("department"):
        query = query.where(Parcel.coddepto == str(params["department"]))
    if params.get("locality"):
        query = query.where(Parcel.codloccat == str(params["locality"]))
    if params.get("q"):
        q = str(params["q"])[:80]
        query = query.where(or_(Parcel.padron.ilike(f"%{q}%"), CadastralLocality.name.ilike(f"%{q}%")))
    if params.get("state"):
        if params["state"] == "NO_ANALIZADO":
            query = query.where(ParcelAnalysisResult.id.is_(None))
        else:
            query = query.where(ParcelAnalysisResult.state == params["state"])
    for field, op in [("min_area", ">="), ("max_area", "<=")]:
        if params.get(field) not in (None, ""):
            try:
                value = float(params[field])
                if not math.isfinite(value) or value < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                abort(422, "Superficie inválida.")
            query = query.where(
                ParcelAnalysisResult.m2_huella_detectada >= value
                if op == ">="
                else ParcelAnalysisResult.m2_huella_detectada <= value
            )
    if params.get("bbox"):
        try:
            bbox = [float(v) for v in str(params["bbox"]).split(",")]
            if (
                len(bbox) != 4
                or not all(math.isfinite(v) for v in bbox)
                or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90)
            ):
                raise ValueError()
        except (ValueError, TypeError):
            abort(422, "Extensión geográfica inválida.")
        query = query.where(
            func.ST_Intersects(
                parcel_geometry(bool(params.get("bulk_id"))), func.ST_MakeEnvelope(*bbox, 4326)
            )
        )
    if params.get("ids"):
        ids = params["ids"] if isinstance(params["ids"], list) else str(params["ids"]).split(",")
        query = query.where(Parcel.id.in_(ids[:10000]))
    if params.get("review_status"):
        query = query.where(ReviewCase.status == params["review_status"])
    number_fields = {
        "min_coverage": (ParcelAnalysisResult.coverage, "min", 1),
        "min_confidence": (ParcelAnalysisResult.confidence, "min", 1),
        "min_occupancy": (ParcelAnalysisResult.occupancy, "min", 1),
        "max_occupancy": (ParcelAnalysisResult.occupancy, "max", 1),
        "min_buildings": (ParcelAnalysisResult.building_count, "min", 100000),
        "max_buildings": (ParcelAnalysisResult.building_count, "max", 100000),
        "padron_from": (
            case((Parcel.padron.op("~")("^[0-9]+$"), cast(Parcel.padron, Numeric)), else_=None),
            "min",
            1e18,
        ),
        "padron_to": (
            case((Parcel.padron.op("~")("^[0-9]+$"), cast(Parcel.padron, Numeric)), else_=None),
            "max",
            1e18,
        ),
    }
    for name, (column, direction, maximum) in number_fields.items():
        if params.get(name) not in (None, ""):
            try:
                value = float(params[name])
                if not math.isfinite(value) or not 0 <= value <= maximum:
                    raise ValueError()
            except (ValueError, TypeError):
                abort(422, f"Filtro numérico inválido: {name}.")
            query = query.where(column >= value if direction == "min" else column <= value)
    run_terms = [AnalysisRun.id == ParcelAnalysisResult.run_id]
    if params.get("model_version_id"):
        run_terms.append(AnalysisRun.model_version_id == params["model_version_id"])
    import re

    for name, direction in [("image_from", "min"), ("image_to", "max")]:
        if params.get(name):
            value = str(params[name])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
                abort(422, "Use un mes de imagen AAAA-MM.")
            run_terms.append(
                exists(
                    select(ImageryScene.id).where(
                        ImageryScene.id == AnalysisRun.scene_id,
                        func.substr(ImageryScene.captured_at, 1, 7) >= value
                        if direction == "min"
                        else func.substr(ImageryScene.captured_at, 1, 7) <= value,
                    )
                )
            )
    if len(run_terms) > 1:
        query = query.where(exists(select(AnalysisRun.id).where(*run_terms)))
    from datetime import datetime, timezone, timedelta

    for name, direction in [("analyzed_from", "min"), ("analyzed_to", "max")]:
        if params.get(name):
            try:
                value = datetime.strptime(str(params[name]), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                abort(422, "Use una fecha de análisis AAAA-MM-DD.")
            query = query.where(
                ParcelAnalysisResult.created_at >= value
                if direction == "min"
                else ParcelAnalysisResult.created_at < value + timedelta(days=1)
            )
    if params.get("land_use"):
        query = query.where(
            exists(
                select(LandUseCategory.id).where(
                    func.ST_Intersects(LandUseCategory.geom, Parcel.geom),
                    LandUseCategory.properties["categoria"].as_string() == params["land_use"],
                )
            )
        )
    if params.get("batch_id"):
        query = query.where(
            exists(
                select(ImportedParcelDeclaration.id).where(
                    ImportedParcelDeclaration.parcel_id == Parcel.id,
                    ImportedParcelDeclaration.batch_id == params["batch_id"],
                )
            )
        )
    if params.get("assigned_to"):
        query = query.where(ReviewCase.assigned_to == params["assigned_to"])
    if params.get("has_notes") in {"true", "false"}:
        notes = exists(
            select(ReviewAction.id).where(
                ReviewAction.case_id == ReviewCase.id, func.length(func.trim(ReviewAction.observations)) > 0
            )
        )
        query = query.where(notes if params["has_notes"] == "true" else ~notes)
    if params.get("comparison_id") or params.get("comparison_state"):
        terms = [
            ImportedParcelDeclaration.parcel_id == Parcel.id,
            ParcelComparisonResult.declaration_id == ImportedParcelDeclaration.id,
        ]
        if params.get("comparison_id"):
            terms.append(ParcelComparisonResult.run_id == params["comparison_id"])
        if params.get("comparison_state"):
            terms.append(ParcelComparisonResult.state == params["comparison_state"])
        query = query.where(
            exists(
                select(ParcelComparisonResult.id)
                .join(
                    ImportedParcelDeclaration,
                    ParcelComparisonResult.declaration_id == ImportedParcelDeclaration.id,
                )
                .where(*terms)
            )
        )
    if params.get("sort") and params["sort"] not in {
        "footprint_desc",
        "footprint_asc",
        "padron",
        "occupancy_desc",
    }:
        abort(422, "Orden no admitido.")
    return query if params.get("bulk_id") else query.where(Parcel.active.is_(True))


def parcel_geometry(bulk=False):
    if not bulk:
        return Parcel.geom
    return (
        select(func.ST_Multi(func.ST_UnaryUnion(func.ST_Collect(ParcelGeometryVersion.geom))))
        .where(
            ParcelGeometryVersion.parcel_id == BulkSelectionItem.parcel_id,
            ParcelGeometryVersion.dataset_version_id == BulkSelectionItem.parcel_version_id,
        )
        .correlate(BulkSelectionItem)
        .scalar_subquery()
    )


def base_query(geometry=False, bulk_id=None):
    columns = [Parcel, CadastralLocality.name.label("locality"), ParcelAnalysisResult, ReviewCase]
    geometry_column = parcel_geometry(bool(bulk_id))
    if bulk_id:
        columns.extend(
            [
                BulkSelectionItem.parcel_area_m2,
                Job.status.label("processing_status"),
                BulkSelectionItem.parcel_version_id,
            ]
        )
    if geometry:
        # The wrapper also prevents GeoAlchemy's record overload from treating a scalar SELECT as a table.
        columns.append(func.ST_AsGeoJSON(func.ST_Multi(geometry_column)).label("geometry"))
    query = (
        select(*columns)
        .select_from(Parcel)
        .join(CadastralLocality, Parcel.locality_id == CadastralLocality.id)
    )
    if bulk_id:
        run = (
            select(AnalysisRun.id)
            .where(AnalysisRun.job_id == BulkSelectionItem.job_id)
            .correlate(BulkSelectionItem)
            .scalar_subquery()
        )
        query = (
            query.join(BulkSelectionItem, BulkSelectionItem.parcel_id == Parcel.id)
            .join(Job, Job.id == BulkSelectionItem.job_id)
            .outerjoin(
                ParcelAnalysisResult,
                (ParcelAnalysisResult.parcel_id == Parcel.id) & (ParcelAnalysisResult.run_id == run),
            )
            .where(BulkSelectionItem.selection_id == bulk_id)
        )
    else:
        query = query.outerjoin(ParcelAnalysisResult, Parcel.current_result_id == ParcelAnalysisResult.id)
    return query.outerjoin(ReviewCase, ParcelAnalysisResult.id == ReviewCase.result_id)


def ordered(query, sort="footprint_desc"):
    columns = {
        "footprint_desc": ParcelAnalysisResult.m2_huella_detectada.desc().nullslast(),
        "footprint_asc": ParcelAnalysisResult.m2_huella_detectada.asc().nullslast(),
        "occupancy_desc": ParcelAnalysisResult.occupancy.desc().nullslast(),
        "padron": case((Parcel.padron.op("~")("^[0-9]+$"), cast(Parcel.padron, Numeric)), else_=None)
        .asc()
        .nullslast(),
    }
    if sort not in columns:
        abort(422, "Orden no admitido.")
    return query.order_by(columns[sort], Parcel.codloccat, Parcel.padron, Parcel.id)


def serialize(row, geometry=False, bulk=False):
    parcel, locality, result, review = row[:4]
    props = dict(
        id=parcel.id,
        coddepto=parcel.coddepto,
        codloccat=parcel.codloccat,
        padron=parcel.padron,
        locality=locality,
        m2_parcela=row[4] if bulk else parcel.m2_parcela,
        state=result.state if result else "NO_ANALIZADO",
        result_id=result.id if result else None,
        m2_huella_detectada=result.m2_huella_detectada if result else None,
        coverage=result.coverage if result else None,
        confidence=result.confidence if result else None,
        occupancy=result.occupancy if result else None,
        building_count=result.building_count if result else None,
        error=result.error if result else None,
        review_id=review.id if review else None,
        review_status=review.status if review else "PENDIENTE_REVISION",
    )
    if bulk:
        props.update(processing_status=row[5], selection_version_id=row[6])
    if geometry:
        return dict(type="Feature", id=parcel.id, geometry=json.loads(row[-1]), properties=props)
    return props
