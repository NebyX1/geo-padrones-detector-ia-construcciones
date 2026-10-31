import csv
import io
import json
from sqlalchemy import select
from ..extensions import db
from ..models import (
    Parcel,
    AnalysisRun,
    ImageryScene,
    AIModelVersion,
    ReviewAction,
    ReviewCase,
    ParcelAnalysisResult,
    ParcelComparisonResult,
    ImportedParcelDeclaration,
)
from ..repositories.parcels import base_query, filters, serialize, ordered
from .storage import storage


def safe_cell(value):
    if value is None:
        return ""
    if isinstance(value, (float, int)):
        return value
    value = str(value)
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_records(params, geometry=True):
    bulk_id = params.get("bulk_id")
    query = filters(base_query(geometry, bulk_id), params)
    query = (
        ordered(query, params.get("sort", "footprint_desc"))
        if params.get("sort") or bulk_id
        else query.order_by(Parcel.id)
    )
    comparison_id = params.get("comparison_id")
    if comparison_id:
        query = (
            query.join(
                ImportedParcelDeclaration, ImportedParcelDeclaration.parcel_id == db.text("parcels.id")
            )
            .join(
                ParcelComparisonResult, ParcelComparisonResult.declaration_id == ImportedParcelDeclaration.id
            )
            .where(ParcelComparisonResult.run_id == comparison_id)
            .add_columns(ParcelComparisonResult, ImportedParcelDeclaration)
        )
        if params.get("comparison_state"):
            query = query.where(ParcelComparisonResult.state == params["comparison_state"])
    for row in db.session.execute(query).yield_per(250):
        parcel, _, result, review = row[:4]
        prefix = (7 if bulk_id else 4) + (1 if geometry else 0)
        data = serialize(row[:prefix], geometry, bulk=bool(bulk_id))
        feature = data if geometry else {"type": "Feature", "geometry": None, "properties": data}
        props = feature["properties"]
        if comparison_id:
            comparison, declaration = row[-2:]
            result = (
                db.session.get(ParcelAnalysisResult, comparison.result_id) if comparison.result_id else None
            )
            review = (
                db.session.execute(
                    select(ReviewCase).where(ReviewCase.result_id == result.id)
                ).scalar_one_or_none()
                if result
                else None
            )
            props.update(
                state=result.state if result else "NO_ANALIZADO",
                result_id=result.id if result else None,
                m2_huella_detectada=result.m2_huella_detectada if result else None,
                coverage=result.coverage if result else None,
                confidence=result.confidence if result else None,
                occupancy=result.occupancy if result else None,
                building_count=result.building_count if result else None,
                review_status=review.status if review else "PENDIENTE_REVISION",
            )
        props["version_catastral_actual"] = parcel.source_version_id
        if bulk_id:
            props.update(
                lote_seleccion=bulk_id,
                estado_proceso=props.pop("processing_status"),
                version_catastral_seleccion=props.pop("selection_version_id"),
            )
        props["version_catastral_analisis"] = result.parcel_version_id if result else None
        props["departamento"] = "LAVALLEJA"
        props["estado_ia"] = props.pop("state")
        props["error_analisis"] = props.pop("error", None)
        props["fecha_imagen"] = props["fuente_imagen"] = props["modelo"] = props["version_modelo"] = props[
            "fecha_analisis"
        ] = None
        if result:
            run = db.session.get(AnalysisRun, result.run_id)
            scene = db.session.get(ImageryScene, run.scene_id)
            model = db.session.get(AIModelVersion, run.model_version_id)
            props.update(
                fecha_imagen=scene.captured_at,
                fuente_imagen=scene.source,
                modelo=model.model_id,
                version_modelo=model.revision,
                fecha_analisis=result.created_at.isoformat(),
            )
        if review:
            action = db.session.execute(
                select(ReviewAction)
                .where(ReviewAction.case_id == review.id)
                .order_by(ReviewAction.version.desc())
                .limit(1)
            ).scalar_one_or_none()
            if action:
                props.update(
                    estado_revisado=action.state,
                    m2_huella_revisada=action.corrected_m2,
                    observaciones=action.observations,
                )
        if comparison_id:
            comparison, declaration = row[-2:]
            props.update(
                construccion_declarada=declaration.declared_building,
                m2_declarados=declaration.declared_m2,
                estado_comparacion=comparison.state,
                diferencia_m2=comparison.difference_m2,
                diferencia_porcentual=comparison.difference_pct,
                advertencia=comparison.warning,
            )
        yield feature

    # Unmatched declarations have no geometry, but remain part of an unspatial comparison export.
    active_keys = {key for key, value in params.items() if value not in (None, "", [])}
    if comparison_id and active_keys <= {"comparison_id", "comparison_state", "department", "locality"}:
        unmatched = (
            select(ParcelComparisonResult, ImportedParcelDeclaration)
            .join(
                ImportedParcelDeclaration,
                ParcelComparisonResult.declaration_id == ImportedParcelDeclaration.id,
            )
            .where(
                ParcelComparisonResult.run_id == comparison_id, ImportedParcelDeclaration.parcel_id.is_(None)
            )
        )
        if params.get("comparison_state"):
            unmatched = unmatched.where(ParcelComparisonResult.state == params["comparison_state"])
        for comparison, declaration in db.session.execute(unmatched).yield_per(250):
            if params.get("department") and declaration.key.get("coddepto") != params["department"]:
                continue
            if params.get("locality") and declaration.key.get("codloccat") != params["locality"]:
                continue
            yield {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    **declaration.key,
                    "estado_ia": "NO_ANALIZADO",
                    "estado_comparacion": comparison.state,
                    "construccion_declarada": declaration.declared_building,
                    "m2_declarados": declaration.declared_m2,
                    "observaciones": declaration.observations,
                    "advertencia": comparison.warning,
                    "fila_declaracion": declaration.row_number,
                    "lote_declaracion": declaration.batch_id,
                },
            }


def generate_export(job, callback):
    params, file_format = job.payload.get("filters", {}), job.payload.get("format", "csv")
    if file_format == "geojson":
        output = io.StringIO()
        output.write('{"type":"FeatureCollection","features":[')
        count = 0
        for feature in export_records(params):
            if count:
                output.write(",")
            output.write(json.dumps(feature, ensure_ascii=False))
            count += 1
            if count % 250 == 0:
                callback(count)
        output.write("]}")
        content, content_type = output.getvalue().encode("utf-8"), "application/geo+json"
    else:
        output, count, writer = io.StringIO(newline=""), 0, None
        fields = [
            "departamento",
            "coddepto",
            "codloccat",
            "locality",
            "padron",
            "id",
            "m2_parcela",
            "version_catastral_actual",
            "version_catastral_analisis",
            "estado_ia",
            "m2_huella_detectada",
            "occupancy",
            "building_count",
            "coverage",
            "confidence",
            "fecha_imagen",
            "fuente_imagen",
            "modelo",
            "version_modelo",
            "fecha_analisis",
            "review_status",
            "estado_revisado",
            "m2_huella_revisada",
            "observaciones",
            "construccion_declarada",
            "m2_declarados",
            "estado_comparacion",
            "diferencia_m2",
            "diferencia_porcentual",
            "advertencia",
            "lote_seleccion",
            "estado_proceso",
            "version_catastral_seleccion",
            "error_analisis",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for feature in export_records(params, geometry=False):
            writer.writerow({k: safe_cell(v) for k, v in feature["properties"].items()})
            count += 1
            if count % 250 == 0:
                callback(count)
        content, content_type = output.getvalue().encode("utf-8-sig"), "text/csv"
    key = f"exports/{job.user_id}/{job.id}.{file_format}"
    storage().put(key, content, content_type)
    job.output_key, job.total, job.processed = key, count, count
