"""Shared, validated filters for paginated work lists and their deletion previews."""

from datetime import datetime, timedelta, timezone
import math
from flask import abort
from sqlalchemy import select, func, exists, cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from ..models import (
    Job,
    AnalysisRun,
    AIModelVersion,
    Parcel,
    CadastralLocality,
    ReviewCase,
    ParcelAnalysisResult,
)

ACTIVE = {"PENDING", "QUEUED", "RUNNING"}
JOB_STATES = ACTIVE | {"COMPLETED", "FAILED", "CANCELLED"}
REVIEW_STATES = {"PENDIENTE_REVISION", "CONFIRMADO", "CORREGIDO", "RECHAZADO"}
RESULT_STATES = {"CON_CONSTRUCCION_VISIBLE", "SIN_CONSTRUCCION_VISIBLE", "INDETERMINADO", "ERROR_ANALISIS"}
COMMON_KEYS = {"q", "locality", "model_version_id", "date_from", "date_to"}
JOB_KEYS = COMMON_KEYS | {"status", "device", "kind"}
REVIEW_KEYS = COMMON_KEYS | {"status", "state", "min_area", "max_area", "needs_reanalysis"}


def dates(query, column, params):
    for name in ("date_from", "date_to"):
        if params.get(name):
            try:
                value = datetime.strptime(str(params[name]), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                abort(422, "Use una fecha AAAA-MM-DD.")
            query = query.where(
                column >= value if name == "date_from" else column < value + timedelta(days=1)
            )
    if params.get("date_from") and params.get("date_to") and params["date_from"] > params["date_to"]:
        abort(422, "La fecha inicial debe ser anterior a la final.")
    return query


def job_query(params):
    query = (
        select(Job)
        .select_from(Job)
        .outerjoin(AnalysisRun, AnalysisRun.job_id == Job.id)
        .outerjoin(AIModelVersion, AIModelVersion.id == AnalysisRun.model_version_id)
    )
    if params.get("kind"):
        if params["kind"] not in {"analysis", "comparison", "export", "import"}:
            abort(422, "Tipo de trabajo inválido.")
        query = query.where(Job.kind == params["kind"])
    if params.get("status"):
        if params["status"] not in JOB_STATES:
            abort(422, "Estado de trabajo inválido.")
        query = query.where(Job.status == params["status"])
    if params.get("device"):
        if params["device"] not in {"cpu", "cuda"}:
            abort(422, "Procesador inválido.")
        query = query.where(
            func.coalesce(AnalysisRun.parameters["device"].as_string(), "cpu") == params["device"]
        )
    if params.get("model_version_id"):
        query = query.where(AnalysisRun.model_version_id == params["model_version_id"])
    if params.get("q") or params.get("locality"):
        terms = [func.jsonb_exists(cast(Job.payload, JSONB)["parcel_ids"], Parcel.id)]
        if params.get("locality"):
            terms.append(Parcel.codloccat == str(params["locality"]))
        if params.get("q"):
            value = f"%{str(params['q'])[:80]}%"
            terms.append(
                or_(Parcel.padron.ilike(value), CadastralLocality.name.ilike(value), Job.id.ilike(value))
            )
        query = query.where(exists(select(Parcel.id).join(CadastralLocality).where(*terms)))
    return dates(query, Job.created_at, params)


def review_query(params):
    query = (
        select(
            ReviewCase,
            ParcelAnalysisResult,
            Parcel,
            CadastralLocality.name,
            AIModelVersion.model_id,
            AnalysisRun.parameters,
        )
        .select_from(ReviewCase)
        .join(ParcelAnalysisResult, ParcelAnalysisResult.id == ReviewCase.result_id)
        .join(Parcel, Parcel.id == ParcelAnalysisResult.parcel_id)
        .join(CadastralLocality, CadastralLocality.id == Parcel.locality_id)
        .join(AnalysisRun, AnalysisRun.id == ParcelAnalysisResult.run_id)
        .join(AIModelVersion, AIModelVersion.id == AnalysisRun.model_version_id)
    )
    if params.get("status"):
        if params["status"] not in REVIEW_STATES:
            abort(422, "Estado de revisión inválido.")
        query = query.where(ReviewCase.status == params["status"])
    if params.get("state"):
        if params["state"] not in RESULT_STATES:
            abort(422, "Estado de detección inválido.")
        query = query.where(ParcelAnalysisResult.state == params["state"])
    if params.get("locality"):
        query = query.where(Parcel.codloccat == params["locality"])
    if params.get("q"):
        value = f"%{str(params['q'])[:80]}%"
        query = query.where(or_(Parcel.padron.ilike(value), CadastralLocality.name.ilike(value)))
    if params.get("model_version_id"):
        query = query.where(AnalysisRun.model_version_id == params["model_version_id"])
    if params.get("needs_reanalysis"):
        if str(params["needs_reanalysis"]) not in {"true", "false"}:
            abort(422, "Filtro de nueva inferencia inválido.")
        query = query.where(ReviewCase.needs_reanalysis.is_(str(params["needs_reanalysis"]) == "true"))
    for key in ("min_area", "max_area"):
        if params.get(key) not in (None, ""):
            try:
                area = float(params[key])
                if not math.isfinite(area) or area < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                abort(422, "Superficie inválida.")
            query = query.where(
                ParcelAnalysisResult.m2_huella_detectada >= area
                if key == "min_area"
                else ParcelAnalysisResult.m2_huella_detectada <= area
            )
    return dates(query, ParcelAnalysisResult.created_at, params)


def count(query):
    from ..extensions import db

    return db.session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
