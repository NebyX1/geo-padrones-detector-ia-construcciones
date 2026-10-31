import io
import json
from flask import Blueprint, abort, jsonify, request, send_file
from sqlalchemy import select, func, text
from ..extensions import db
from ..models import (
    Parcel,
    CadastralLocality,
    ImageryScene,
    AIModelVersion,
    AnalysisRun,
    BuildingFootprint,
    LandUseCategory,
    ReviewAction,
    ImportedParcelDeclaration,
    ParcelComparisonResult,
)
from ..repositories.parcels import base_query, filters, serialize
from ..utils.security import require

bp = Blueprint("cadastre", __name__)


@bp.post("/parcels/select")
@require("read")
def select_polygon():
    from ..services.geospatial import validate_wgs84
    from geoalchemy2.shape import from_shape

    data = request.get_json() or {}
    try:
        geom = validate_wgs84(data.get("geometry"))
    except (ValueError, TypeError, AttributeError):
        abort(422, "Polígono de selección inválido.")
    if geom.area > 0.02:
        abort(422, "Selección demasiado grande; trabaje por sectores.")
    query = (
        select(Parcel.id)
        .where(func.ST_Intersects(Parcel.geom, from_shape(geom, srid=4326)), Parcel.active.is_(True))
        .limit(1001)
    )
    ids = list(db.session.execute(query).scalars())
    if len(ids) > 1000:
        abort(422, "La selección supera 1000 padrones. Reduzca el área.")
    return jsonify(ids=ids)


@bp.get("/localities")
@require("read")
def localities():
    rows = db.session.execute(
        select(CadastralLocality, func.count(Parcel.id), func.ST_Extent(Parcel.geom))
        .outerjoin(Parcel, (Parcel.locality_id == CadastralLocality.id) & Parcel.active.is_(True))
        .group_by(CadastralLocality.id)
        .order_by(CadastralLocality.name)
    ).all()
    return jsonify(
        items=[
            dict(
                id=r.id,
                coddepto=r.coddepto,
                codloccat=r.codloccat,
                name=r.name,
                count=count,
                bbox=[
                    float(n) for n in extent.removeprefix("BOX(").removesuffix(")").replace(",", " ").split()
                ]
                if extent
                else None,
            )
            for r, count, extent in rows
        ]
    )


@bp.get("/parcels")
@bp.get("/parcels/search")
@require("read")
def parcels():
    geometry = request.args.get("format") == "geojson"
    limit = min(max(request.args.get("limit", 100, type=int), 1), 1000 if geometry else 250)
    offset = max(request.args.get("offset", 0, type=int), 0)
    if (
        geometry
        and not request.args.get("bbox")
        and not request.args.get("q")
        and not request.args.get("ids")
    ):
        abort(422, "Indique bbox, búsqueda o selección para consultar geometrías.")
    query = filters(base_query(geometry), request.args).order_by(Parcel.codloccat, Parcel.padron, Parcel.id)
    rows = db.session.execute(query.limit(limit + 1).offset(offset)).all()
    more = len(rows) > limit
    items = [serialize(row, geometry) for row in rows[:limit]]
    if request.args.get("comparison_id") and items:
        states = dict(
            db.session.execute(
                select(ImportedParcelDeclaration.parcel_id, ParcelComparisonResult.state)
                .join(
                    ParcelComparisonResult,
                    ParcelComparisonResult.declaration_id == ImportedParcelDeclaration.id,
                )
                .where(
                    ParcelComparisonResult.run_id == request.args["comparison_id"],
                    ImportedParcelDeclaration.parcel_id.in_([row[0].id for row in rows[:limit]]),
                )
            ).all()
        )
        for item in items:
            properties = item["properties"] if geometry else item
            properties["comparison_state"] = states.get(properties["id"])
    return (
        jsonify(
            type="FeatureCollection",
            features=items,
            truncated=more,
            next_offset=offset + limit if more else None,
        )
        if geometry
        else jsonify(items=items, next_offset=offset + limit if more else None)
    )


@bp.get("/parcels/<identifier>")
@require("read")
def parcel_detail(identifier):
    row = db.session.execute(base_query(True).where(Parcel.id == identifier)).first()
    if not row:
        abort(404)
    feature = serialize(row, True)
    result = row[2]
    evidence = None
    footprints = []
    history = []
    if result:
        run = db.session.get(AnalysisRun, result.run_id)
        scene = db.session.get(ImageryScene, run.scene_id)
        model = db.session.get(AIModelVersion, run.model_version_id)
        evidence = dict(
            captured_at=scene.captured_at,
            source=scene.source,
            resolution_m=scene.resolution_m,
            model=model.model_id,
            revision=model.revision,
            sha256=model.sha256,
            analyzed_at=result.created_at,
            result_error=result.error,
            mask_available=bool(result.mask_key),
            notice="Huella visible desde arriba; no equivale a superficie total edificada. Modelo sin calibración local validada.",
        )
        footprints = [
            json.loads(v)
            for v in db.session.execute(
                select(func.ST_AsGeoJSON(BuildingFootprint.geom)).where(
                    BuildingFootprint.result_id == result.id
                )
            ).scalars()
        ]
        if row[3]:
            history = [
                dict(
                    id=a.id,
                    status=a.status,
                    state=a.state,
                    observations=a.observations,
                    m2=a.corrected_m2,
                    version=a.version,
                    created_at=a.created_at,
                    user_id=a.user_id,
                    geometry=json.loads(geom) if geom else None,
                )
                for a, geom in db.session.execute(
                    select(ReviewAction, func.ST_AsGeoJSON(ReviewAction.corrected_geom))
                    .where(ReviewAction.case_id == row[3].id)
                    .order_by(ReviewAction.version.desc())
                ).all()
            ]
    land_use = (
        db.session.execute(
            text("""SELECT l.properties,
        ST_Area(ST_Transform(ST_Intersection(l.geom, p.geom),5382))/p.m2_parcela AS fraction
        FROM land_use_categories l JOIN parcels p ON ST_Intersects(l.geom,p.geom)
        WHERE p.id=:id AND ST_Area(ST_Intersection(l.geom,p.geom)) > 0"""),
            {"id": identifier},
        )
        .mappings()
        .all()
    )
    return jsonify(
        parcel=feature,
        evidence=evidence,
        footprints=footprints,
        review_history=history,
        land_use=[dict(r) for r in land_use],
    )


@bp.get("/parcels/tiles/<int:z>/<int:x>/<int:y>.pbf")
@require("read")
def vector_tile(z, x, y):
    if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        abort(422)
    tile = db.session.execute(
        text("""WITH bounds AS (SELECT ST_TileEnvelope(:z,:x,:y) geom),
        rows AS (SELECT p.id, p.padron, COALESCE(r.state,'NO_ANALIZADO') state,
            ST_AsMVTGeom(ST_Transform(p.geom,3857), bounds.geom,4096,64,true) geom
            FROM parcels p CROSS JOIN bounds LEFT JOIN parcel_results r ON r.id=p.current_result_id
            WHERE p.active AND p.geom && ST_Transform(ST_Expand(bounds.geom,ST_XMax(bounds.geom)*0+64*40075016.68557849/(4096*power(2,:z))),4326)
            LIMIT 5000) SELECT ST_AsMVT(rows,'parcels',4096,'geom') FROM rows"""),
        dict(z=z, x=x, y=y),
    ).scalar()
    return (
        bytes(tile or b""),
        200,
        {"Content-Type": "application/vnd.mapbox-vector-tile", "Cache-Control": "private,max-age=60"},
    )


@bp.get("/land-use/categories")
@require("read")
def categories():
    if request.args.get("format") == "geojson":
        from ..services.geospatial import validate_wgs84
        from shapely.geometry import box, mapping
        from geoalchemy2.shape import from_shape

        try:
            bounds = [float(v) for v in request.args.get("bbox", "").split(",")]
            if len(bounds) != 4:
                raise ValueError()
            extent = validate_wgs84(mapping(box(*bounds)))
        except (ValueError, TypeError):
            abort(422, "Indique una extensión válida en Uruguay.")
        boundary = from_shape(extent, srid=4326)
        rows = db.session.execute(
            select(LandUseCategory, func.ST_AsGeoJSON(func.ST_Intersection(LandUseCategory.geom, boundary)))
            .where(func.ST_Intersects(LandUseCategory.geom, boundary))
            .limit(200)
        ).all()
        return jsonify(
            type="FeatureCollection",
            features=[
                dict(type="Feature", id=category.id, properties=category.properties, geometry=json.loads(geo))
                for category, geo in rows
            ],
        )
    return jsonify(
        items=[
            dict(id=row.id, properties=row.properties, source=row.source)
            for row in db.session.execute(select(LandUseCategory).limit(200)).scalars()
        ]
    )


@bp.get("/imagery/scenes")
@require("read")
def scenes():
    return jsonify(
        items=[
            dict(
                id=s.id,
                name=s.name,
                source=s.source,
                coverage_id=s.coverage_id,
                captured_at=s.captured_at,
                resolution_m=s.resolution_m,
                srid=s.srid,
                license=s.license,
                metadata=s.metadata_json,
            )
            for s in db.session.execute(select(ImageryScene)).scalars()
        ]
    )


@bp.get("/imagery/scenes/<identifier>")
@require("read")
def scene_detail(identifier):
    scene = db.get_or_404(ImageryScene, identifier)
    return jsonify(id=scene.id, name=scene.name, captured_at=scene.captured_at, metadata=scene.metadata_json)


@bp.get("/imagery/scenes/<identifier>/tiles/<int:z>/<int:x>/<int:y>.png")
@require("read")
def image_tile(identifier, z, x, y):
    from ..services.imagery import render_tile
    from types import SimpleNamespace

    if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        abort(422, "Tesela inválida.")

    scene = db.get_or_404(ImageryScene, identifier)
    source = SimpleNamespace(id=scene.id, coverage_id=scene.coverage_id)
    # Authentication/lookup are complete. Never retain a DB connection during remote WMS I/O.
    db.session.remove()
    return send_file(io.BytesIO(render_tile(source, z, x, y)), mimetype="image/png")


@bp.get("/models")
@require("read")
def models():
    return jsonify(
        items=[
            dict(
                id=m.id,
                model_id=m.model_id,
                revision=m.revision,
                sha256=m.sha256,
                license=m.license,
                enabled=m.enabled,
                metadata=m.metadata_json,
            )
            for m in db.session.execute(select(AIModelVersion)).scalars()
        ]
    )


@bp.get("/imagery/historical/tiles/<int:z>/<int:x>/<int:y>.png")
@require("read")
def historical_tile(z, x, y):
    from ..services.imagery import render_historical_tile

    if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        abort(422, "Tesela inválida.")
    db.session.remove()

    return send_file(io.BytesIO(render_historical_tile(z, x, y)), mimetype="image/png")


@bp.get("/models/<identifier>")
@require("read")
def model_detail(identifier):
    m = db.get_or_404(AIModelVersion, identifier)
    return jsonify(
        id=m.id, model_id=m.model_id, revision=m.revision, sha256=m.sha256, metadata=m.metadata_json
    )
