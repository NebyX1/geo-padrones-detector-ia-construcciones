from datetime import date
import json
from flask import current_app
from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy import select, text
from rasterio.io import MemoryFile
from ..extensions import db
from ..models import (
    Job,
    AnalysisRun,
    Parcel,
    ParcelAnalysisResult,
    BuildingFootprint,
    ImageryScene,
    AIModelVersion,
    ReviewCase,
    ImportBatch,
    ImportedParcelDeclaration,
    ComparisonRun,
    ParcelComparisonResult,
    utcnow,
)
from ..services.storage import storage


class Cancelled(Exception):
    pass


def progress(job_id, count=None):
    # Separate transaction keeps progress visible without committing partial domain operations.
    with db.engine.begin() as connection:
        cancelled = connection.execute(
            text("SELECT cancel_requested FROM jobs WHERE id=:id"), {"id": job_id}
        ).scalar()
        if cancelled:
            raise Cancelled()
        if count is not None:
            connection.execute(
                text("UPDATE jobs SET processed=:count WHERE id=:id"), {"id": job_id, "count": count}
            )


def analyze(job):
    # Heavy dependencies imported only here, in the RQ worker process.
    from ..services.inference import load_model, segment, vectorize
    from ..services.imagery import download_crop, read_rgb
    from ..services.geospatial import reproject, measure, multipolygon, parcel_confidence

    run = db.session.execute(select(AnalysisRun).where(AnalysisRun.job_id == job.id)).scalar_one()
    scene = db.session.get(ImageryScene, run.scene_id)
    model_version = db.session.get(AIModelVersion, run.model_version_id)
    if not model_version.enabled:
        raise ValueError("El modelo fue deshabilitado.")
    model = None
    params = run.parameters
    for index, parcel_id in enumerate(job.payload["parcel_ids"], start=1):
        progress(job.id)
        existing = db.session.execute(
            select(ParcelAnalysisResult).where(
                ParcelAnalysisResult.run_id == run.id, ParcelAnalysisResult.parcel_id == parcel_id
            )
        ).scalar_one_or_none()
        if existing:
            progress(job.id, index)
            continue
        parcel = db.session.get(Parcel, parcel_id)
        expected_version = job.payload.get("expected_versions", {}).get(parcel_id, parcel.source_version_id)
        result = ParcelAnalysisResult(
            run_id=run.id,
            parcel_id=parcel.id,
            parcel_version_id=expected_version,
            state="ERROR_ANALISIS",
            coverage=0,
        )
        try:
            if parcel.source_version_id != expected_version:
                raise ValueError(
                    "El catastro cambió después de seleccionar la parcela; seleccione y analice nuevamente."
                )
            if not parcel.active:
                raise ValueError("La parcela está inactiva desde la selección; requiere revisión.")
            if reason := job.payload.get("skip_reasons", {}).get(parcel_id):
                raise ValueError(reason)
            metric = reproject(to_shape(parcel.geom))
            bounds = metric.buffer(8).bounds
            raw, asset = download_crop(scene, bounds)
            rgb, valid, affine, crs = read_rgb(raw)
            if model is None:
                model = load_model(
                    str(current_app.config["MODEL_DIR"] / model_version.filename),
                    model_version.sha256,
                    current_app.config["MODEL_DEVICE"],
                )
            probabilities = segment(
                rgb, model, current_app.config["MODEL_DEVICE"], callback=lambda: progress(job.id)
            )
            buildings, coverage, binary = vectorize(
                probabilities, valid, affine, params["probability"], params.get("min_object_area", 2)
            )
            measured = measure(
                metric,
                buildings,
                coverage,
                params["min_area"],
                params["min_coverage"],
                params["min_occupancy"],
            )
            footprints = measured.pop("footprints")
            # Old imagery cannot establish current absence. Preserve values but classify as indeterminate.
            captured = date.fromisoformat(
                scene.captured_at + "-01" if len(scene.captured_at) == 7 else scene.captured_at
            )
            if (date.today() - captured).days > params["max_image_age_days"]:
                measured["state"] = "INDETERMINADO"
                result.error = "Imagen supera la antigüedad máxima configurada."
            for key, value in measured.items():
                setattr(result, key, value)
            result.asset_id = asset.id
            result.confidence = parcel_confidence(probabilities, binary, valid, metric, affine)
            db.session.add(result)
            db.session.flush()
            for geom in footprints:
                db.session.add(
                    BuildingFootprint(
                        result_id=result.id,
                        geom=from_shape(multipolygon(reproject(geom, 5382, 4326)), srid=4326),
                        confidence=result.confidence,
                    )
                )
            with MemoryFile() as memory:
                with memory.open(
                    driver="GTiff",
                    width=binary.shape[1],
                    height=binary.shape[0],
                    count=1,
                    dtype="uint8",
                    crs=crs,
                    transform=affine,
                    compress="deflate",
                    nodata=255,
                ) as raster:
                    raster.write(binary, 1)
                    raster.write_mask(valid.astype("uint8") * 255)
                result.mask_key = storage().put(
                    f"masks/{run.id}/{parcel.id}.tif", memory.read(), "image/tiff"
                )
            from ..services.mask_preview import preview_mask

            png, bounds = preview_mask(result)
            storage().put(result.mask_key + ".png", png, "image/png")
            storage().put(result.mask_key + ".json", json.dumps(bounds).encode(), "application/json")
        except Cancelled:
            raise
        except Exception as exc:
            db.session.rollback()
            # Expose safe operational categories only; not SQL, object keys, passwords or URLs with credentials.
            message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            state = (
                "INDETERMINADO"
                if message.startswith(
                    ("Sin cobertura", "La parcela supera", "El catastro cambió", "La parcela está inactiva")
                )
                else "ERROR_ANALISIS"
            )
            result = ParcelAnalysisResult(
                run_id=run.id,
                parcel_id=parcel.id,
                parcel_version_id=expected_version,
                state=state,
                coverage=0,
                error=message[:300],
            )
            db.session.add(result)
            db.session.flush()
        from ..services.results import promote_result

        promoted = promote_result(result)
        if result.asset_id and promoted:
            db.session.execute(
                db.update(ReviewCase)
                .where(
                    ReviewCase.needs_reanalysis.is_(True),
                    ReviewCase.result_id.in_(
                        select(ParcelAnalysisResult.id).where(ParcelAnalysisResult.parcel_id == parcel.id)
                    ),
                )
                .values(needs_reanalysis=False)
            )
        db.session.add(ReviewCase(result_id=result.id))
        db.session.commit()
        progress(job.id, index)


def compare_batch(job):
    from ..services.comparisons import compare

    run = db.session.execute(select(ComparisonRun).where(ComparisonRun.job_id == job.id)).scalar_one()
    # Atomic snapshot: result_id is captured in this run; later inference cannot rewrite comparisons.
    records = db.session.execute(
        select(ImportedParcelDeclaration, ParcelAnalysisResult)
        .outerjoin(Parcel, Parcel.id == ImportedParcelDeclaration.parcel_id)
        .outerjoin(ParcelAnalysisResult, Parcel.current_result_id == ParcelAnalysisResult.id)
        .where(ImportedParcelDeclaration.batch_id == run.batch_id)
    ).all()
    db.session.execute(db.delete(ParcelComparisonResult).where(ParcelComparisonResult.run_id == run.id))
    job.total = len(records)
    for index, (declaration, result) in enumerate(records, start=1):
        comparison = compare(declaration, result, **run.parameters)
        db.session.add(
            ParcelComparisonResult(
                run_id=run.id,
                declaration_id=declaration.id,
                result_id=result.id if result else None,
                **comparison,
            )
        )
        if index % 250 == 0:
            progress(job.id, index)
    job.processed = len(records)


def execute_job(identifier):
    from app import create_app

    with create_app().app_context():
        # Advisory lock lives on a dedicated connection across transaction boundaries and retries.
        with db.engine.connect() as lock:
            acquired = lock.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:id))"), {"id": identifier}
            ).scalar()
            if not acquired:
                return
            try:
                job = db.session.get(Job, identifier)
                if job is None or job.status in {"COMPLETED", "CANCELLED"}:
                    return
                job.status, job.started_at, job.error = "RUNNING", job.started_at or utcnow(), None
                db.session.commit()
                try:
                    progress(job.id)
                    if job.kind == "analysis":
                        analyze(job)
                    elif job.kind == "import":
                        from ..services.csv_import import process_batch

                        batch = db.session.get(ImportBatch, job.payload["batch_id"])
                        db.session.execute(
                            db.delete(ImportedParcelDeclaration).where(
                                ImportedParcelDeclaration.batch_id == batch.id
                            )
                        )
                        summary = process_batch(
                            batch, storage().get(batch.object_key), lambda n: progress(job.id, n)
                        )
                        job.total, job.processed = summary.get("rows", 0), summary.get("rows", 0)
                    elif job.kind == "comparison":
                        compare_batch(job)
                    elif job.kind == "export":
                        from ..services.exports import generate_export

                        generate_export(job, lambda n: progress(job.id, n))
                    else:
                        raise ValueError("Tipo de trabajo no admitido.")
                    progress(job.id)
                    # Refresh only progress fields changed outside the ORM session.
                    if job.kind == "analysis":
                        db.session.refresh(job)
                    job.status, job.finished_at = "COMPLETED", utcnow()
                    db.session.commit()
                except Cancelled:
                    db.session.rollback()
                    job = db.session.get(Job, identifier)
                    job.status, job.finished_at = "CANCELLED", utcnow()
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    job = db.session.get(Job, identifier)
                    job.status, job.finished_at = "FAILED", utcnow()
                    job.error = str(exc)[:300] if isinstance(exc, ValueError) else type(exc).__name__
                    db.session.commit()
                    raise
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(hashtext(:id))"), {"id": identifier})
