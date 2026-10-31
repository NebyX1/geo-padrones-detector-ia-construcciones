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
            query = query.where(Parcel.current_result_id.is_(None))
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
        query = query.where(func.ST_Intersects(Parcel.geom, func.ST_MakeEnvelope(*bbox, 4326)))
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
    return query.where(Parcel.active.is_(True))


def base_query(geometry=False):
    columns = [Parcel, CadastralLocality.name.label("locality"), ParcelAnalysisResult, ReviewCase]
    if geometry:
        columns.append(func.ST_AsGeoJSON(Parcel.geom).label("geometry"))
    return (
        select(*columns)
        .join(CadastralLocality, Parcel.locality_id == CadastralLocality.id)
        .outerjoin(ParcelAnalysisResult, Parcel.current_result_id == ParcelAnalysisResult.id)
        .outerjoin(ReviewCase, ParcelAnalysisResult.id == ReviewCase.result_id)
    )


def serialize(row, geometry=False):
    parcel, locality, result, review = row[:4]
    props = dict(
        id=parcel.id,
        coddepto=parcel.coddepto,
        codloccat=parcel.codloccat,
        padron=parcel.padron,
        locality=locality,
        m2_parcela=parcel.m2_parcela,
        state=result.state if result else "NO_ANALIZADO",
        result_id=result.id if result else None,
        m2_huella_detectada=result.m2_huella_detectada if result else None,
        coverage=result.coverage if result else None,
        confidence=result.confidence if result else None,
        occupancy=result.occupancy if result else None,
        building_count=result.building_count if result else None,
        review_id=review.id if review else None,
        review_status=review.status if review else "PENDIENTE_REVISION",
    )
    if geometry:
        return dict(type="Feature", id=parcel.id, geometry=json.loads(row[-1]), properties=props)
    return props
