"""Aggregations over persisted evidence, with explicit time/locality scope."""

from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, abort
from sqlalchemy import select, func, case
from ..extensions import db
from ..models import (
    Parcel,
    ParcelAnalysisResult as Result,
    AnalysisRun,
    ImageryScene,
    CadastralLocality,
    ReviewCase,
    ParcelComparisonResult as Comparison,
    ImportedParcelDeclaration as Declaration,
    ComparisonRun,
)
from ..utils.security import require

bp = Blueprint("analytics", __name__)


@bp.get("/dashboard/analytics")
@require("read")
def analytics():
    start, end = None, None
    try:
        if request.args.get("from"):
            start = datetime.strptime(request.args["from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if request.args.get("to"):
            end = datetime.strptime(request.args["to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(
                days=1
            )
        if start and end and start >= end:
            raise ValueError()
    except ValueError:
        abort(422, "Rango de fechas inválido; use AAAA-MM-DD.")
    locality = request.args.get("locality")
    base = (
        select(
            Result.state,
            Result.m2_huella_detectada.label("area"),
            Result.occupancy,
            Result.coverage,
            Result.confidence,
            Result.created_at,
            CadastralLocality.name.label("locality"),
            ImageryScene.captured_at,
            ReviewCase.status.label("review_status"),
        )
        .join(Parcel, Parcel.current_result_id == Result.id)
        .join(CadastralLocality, Parcel.locality_id == CadastralLocality.id)
        .join(AnalysisRun, Result.run_id == AnalysisRun.id)
        .join(ImageryScene, AnalysisRun.scene_id == ImageryScene.id)
        .outerjoin(ReviewCase, ReviewCase.result_id == Result.id)
        .where(Parcel.active.is_(True))
    )
    if locality:
        base = base.where(Parcel.codloccat == locality)
    if start:
        base = base.where(Result.created_at >= start)
    if end:
        base = base.where(Result.created_at < end)
    evidence = base.subquery()

    def grouped(column):
        return [
            {"label": label or "Sin dato", "count": count}
            for label, count in db.session.execute(
                select(column, func.count()).select_from(evidence).group_by(column).order_by(column)
            )
        ]

    def histogram(column, edges, labels):
        bucket = case(*[(column <= edge, index) for index, edge in enumerate(edges)], else_=len(edges))
        counts = dict(
            db.session.execute(
                select(bucket, func.count()).select_from(evidence).where(column.is_not(None)).group_by(bucket)
            ).all()
        )
        return [{"label": label, "count": counts.get(index, 0)} for index, label in enumerate(labels)]

    visible = [
        {"label": name, "count": count}
        for name, count in db.session.execute(
            select(evidence.c.locality, func.count())
            .where(evidence.c.state == "CON_CONSTRUCCION_VISIBLE")
            .group_by(evidence.c.locality)
            .order_by(func.count().desc())
        )
    ]
    timeline = select(func.date(Result.created_at), func.count()).join(Parcel, Result.parcel_id == Parcel.id)
    if locality:
        timeline = timeline.where(Parcel.codloccat == locality)
    if start:
        timeline = timeline.where(Result.created_at >= start)
    if end:
        timeline = timeline.where(Result.created_at < end)
    days = [
        {"label": day.isoformat(), "count": count}
        for day, count in db.session.execute(
            timeline.group_by(func.date(Result.created_at)).order_by(func.date(Result.created_at)).limit(366)
        )
    ]
    comparisons = (
        select(Comparison.state, func.count())
        .join(ComparisonRun, Comparison.run_id == ComparisonRun.id)
        .join(Declaration, Comparison.declaration_id == Declaration.id)
    )
    if locality:
        comparisons = comparisons.where(Declaration.key["codloccat"].as_string() == locality)
    if start:
        comparisons = comparisons.where(ComparisonRun.created_at >= start)
    if end:
        comparisons = comparisons.where(ComparisonRun.created_at < end)
    return jsonify(
        visible_by_locality=visible,
        footprint=histogram(
            evidence.c.area,
            [0, 50, 100, 200, 500],
            ["0 m²", "0–50 m²", "50–100 m²", "100–200 m²", "200–500 m²", ">500 m²"],
        ),
        occupancy=histogram(
            evidence.c.occupancy, [0.25, 0.5, 0.75], ["0–25 %", "25–50 %", "50–75 %", "75–100 %"]
        ),
        coverage=histogram(evidence.c.coverage, [0.5, 0.95], ["0–50 %", "50–95 %", "95–100 %"]),
        confidence=histogram(evidence.c.confidence, [0.5, 0.7, 0.9], ["≤0,5", "0,5–0,7", "0,7–0,9", ">0,9"]),
        imagery=grouped(evidence.c.captured_at),
        reviews=grouped(evidence.c.review_status),
        timeline=days,
        comparisons=[
            {"label": state, "count": count}
            for state, count in db.session.execute(comparisons.group_by(Comparison.state))
        ],
        notice="Distribuciones de resultados actuales por fecha de análisis UTC. Evolución incluye reanálisis; se muestran hasta 366 días. Probabilidad del modelo sin calibración local.",
    )
