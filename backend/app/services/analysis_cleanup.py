"""Explicit hard deletion of generated analysis data, with a reviewable scope."""

import hashlib
import json
import uuid
from collections import defaultdict
from flask import abort, current_app
from sqlalchemy import select, func, or_, update, delete
from sqlalchemy.dialects.postgresql import insert
from ..extensions import db
from ..models import (
    Job,
    AnalysisRun,
    ParcelAnalysisResult,
    Parcel,
    ReviewCase,
    ReviewAction,
    ReviewAttachment,
    BuildingFootprint,
    BulkSelection,
    BulkSelectionItem,
    ComparisonRun,
    ParcelComparisonResult,
    CleanupEntry,
    AuditLog,
)
from ..repositories.worklists import job_query, review_query, JOB_KEYS, REVIEW_KEYS, ACTIVE
from ..utils.security import audit


def selection(data):
    if not isinstance(data, dict) or set(data) - {
        "target",
        "mode",
        "ids",
        "filters",
        "fingerprint",
        "confirmation",
    }:
        abort(422, "Selección de eliminación inválida.")
    target, mode = data.get("target"), data.get("mode")
    if target not in {"analysis", "reviews"} or mode not in {"ids", "filtered", "all"}:
        abort(422, "Indique qué lista y qué alcance desea eliminar.")
    params = data.get("filters", {})
    allowed = JOB_KEYS if target == "analysis" else REVIEW_KEYS
    if (
        not isinstance(params, dict)
        or set(params) - allowed
        or any(not isinstance(v, str) for v in params.values())
    ):
        abort(422, "Filtros de eliminación inválidos.")
    ids = data.get("ids", [])
    if mode == "ids":
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10000:
            abort(422, "Seleccione entre 1 y 10.000 registros.")
        try:
            ids = sorted({str(uuid.UUID(value)) for value in ids})
        except (ValueError, TypeError, AttributeError):
            abort(422, "Identificadores inválidos.")
    elif ids:
        abort(422, "No combine identificadores con toda la lista.")
    return target, mode, params if mode == "filtered" else {}, ids


def plan(data):
    target, mode, params, identifiers = selection(data)
    reset = target == "analysis" and mode == "all"
    if target == "analysis":
        query = job_query({**params, "kind": "analysis"})
        if mode == "ids":
            query = query.where(Job.id.in_(identifiers))
        chosen_jobs = list(db.session.scalars(query))
        if mode == "ids" and len(chosen_jobs) != len(identifiers):
            abort(409, "Algunos trabajos ya no existen; actualice la lista.")
        delete_jobs = {j.id for j in chosen_jobs}
        runs = list(db.session.scalars(select(AnalysisRun).where(AnalysisRun.job_id.in_(delete_jobs))))
        result_rows = list(
            db.session.scalars(
                select(ParcelAnalysisResult).where(ParcelAnalysisResult.run_id.in_([r.id for r in runs]))
            )
        )
        affected_jobs = chosen_jobs
    else:
        query = review_query(params)
        if mode == "ids":
            query = query.where(ReviewCase.id.in_(identifiers))
        cases = db.session.execute(query).all()
        if mode == "ids" and len(cases) != len(identifiers):
            abort(409, "Algunos casos ya no existen; actualice la lista.")
        result_rows = [row[1] for row in cases]
        runs = list(
            db.session.scalars(select(AnalysisRun).where(AnalysisRun.id.in_({r.run_id for r in result_rows})))
        )
        affected_jobs = list(db.session.scalars(select(Job).where(Job.id.in_({r.job_id for r in runs}))))
        delete_jobs = set()
    result_ids = {r.id for r in result_rows}
    run_jobs = {r.id: r.job_id for r in runs}
    removed_parcels = defaultdict(set)
    for result in result_rows:
        removed_parcels[run_jobs[result.run_id]].add(result.parcel_id)
    remaining_payloads = {}
    if target == "reviews":
        retained = defaultdict(set)
        for job_id, parcel_id in db.session.execute(
            select(AnalysisRun.job_id, ParcelAnalysisResult.parcel_id)
            .join(ParcelAnalysisResult, ParcelAnalysisResult.run_id == AnalysisRun.id)
            .where(
                AnalysisRun.job_id.in_([job.id for job in affected_jobs]),
                ParcelAnalysisResult.id.not_in(result_ids),
            )
        ):
            retained[job_id].add(parcel_id)
        for job in affected_jobs:
            remaining = sorted(
                (
                    {p for p in job.payload.get("parcel_ids", []) if p not in removed_parcels[job.id]}
                    | retained[job.id]
                )
            )
            if remaining:
                remaining_payloads[job.id] = remaining
            else:
                delete_jobs.add(job.id)
    cases = list(
        db.session.scalars(
            select(ReviewCase)
            .where(ReviewCase.result_id.in_(result_ids))
            .execution_options(populate_existing=True)
        )
    )
    case_ids = {c.id for c in cases}
    attachments = list(
        db.session.scalars(select(ReviewAttachment).where(ReviewAttachment.case_id.in_(case_ids)))
    )
    terms = [BulkSelectionItem.job_id.in_(delete_jobs)]
    terms += [
        (BulkSelectionItem.job_id == job_id) & BulkSelectionItem.parcel_id.in_(parcels)
        for job_id, parcels in removed_parcels.items()
    ]
    items = list(db.session.scalars(select(BulkSelectionItem).where(or_(*terms))))
    batch_ids = {item.selection_id for item in items}
    if reset:
        batch_ids = set(db.session.scalars(select(BulkSelection.id)))
    comparisons = (
        list(
            db.session.scalars(
                select(ComparisonRun).where(
                    ComparisonRun.id.in_(
                        select(ParcelComparisonResult.run_id).where(
                            ParcelComparisonResult.result_id.in_(result_ids)
                        )
                    )
                )
            )
        )
        if not reset
        else list(db.session.scalars(select(ComparisonRun)))
    )
    comparison_ids = {c.id for c in comparisons}
    derived_ids = {c.job_id for c in comparisons}
    # Exports have no frozen row manifest: invalidate all old files so none retains a deleted result.
    exports = list(db.session.scalars(select(Job).where(Job.kind == "export"))) if result_ids or reset else []
    derived_ids.update(j.id for j in exports)
    derived_jobs = list(db.session.scalars(select(Job).where(Job.id.in_(derived_ids))))
    blockers = [j for j in [*affected_jobs, *derived_jobs] if j.status in ACTIVE]
    # A running analysis could add a matching review after an all/filtered preview.
    if target == "reviews" and mode != "ids":
        blockers.extend(db.session.scalars(select(Job).where(Job.kind == "analysis", Job.status.in_(ACTIVE))))
    blockers = list({j.id: j for j in blockers}.values())
    action_count = db.session.scalar(
        select(func.count()).select_from(ReviewAction).where(ReviewAction.case_id.in_(case_ids))
    )
    audit_targets = case_ids | result_ids | delete_jobs | derived_ids | comparison_ids | batch_ids
    audit_count = db.session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.entity_id.in_(audit_targets))
    )
    counts = dict(
        analyses=len(delete_jobs),
        results=len(result_ids),
        reviews=len(cases),
        review_actions=action_count,
        attachments=len(attachments),
        comparison_runs=len(comparisons),
        exports=len(exports),
        batches=len(batch_ids),
        audit_records=audit_count,
    )
    signature = dict(
        selection=[target, mode, params, identifiers],
        counts=counts,
        jobs=sorted((j.id, j.status, j.processed) for j in [*affected_jobs, *derived_jobs]),
        results=sorted(result_ids),
        cases=sorted((c.id, c.version) for c in cases),
        attachments=sorted(a.id for a in attachments),
        batches=sorted(batch_ids),
    )
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    return dict(
        counts=counts,
        fingerprint=fingerprint,
        active_jobs=len(blockers),
        blocker_ids=[j.id for j in blockers],
        empty=not affected_jobs and not result_ids and not (reset and (batch_ids or derived_ids)),
        internal=dict(
            result_ids=result_ids,
            case_ids=case_ids,
            result_rows=result_rows,
            attachments=attachments,
            affected_jobs=affected_jobs,
            delete_jobs=delete_jobs,
            remaining_payloads=remaining_payloads,
            item_ids={i.id for i in items},
            batch_ids=batch_ids,
            comparisons=comparison_ids,
            derived_jobs=derived_jobs,
            runs=runs,
            reset=reset,
            audit_targets=audit_targets,
        ),
    )


def public_plan(value):
    return {k: v for k, v in value.items() if k != "internal"}


def erase(data):
    if data.get("confirmation") != "ELIMINAR":
        abort(422, "Escriba ELIMINAR para confirmar.")
    # Serialize against new jobs, dispatcher and progress; never race a running inference/export.
    db.session.execute(db.text("LOCK TABLE jobs IN SHARE ROW EXCLUSIVE MODE"))
    value = plan(data)
    p = value["internal"]
    for identifier in sorted({j.id for j in [*p["affected_jobs"], *p["derived_jobs"]]}):
        if not db.session.scalar(
            db.text("SELECT pg_try_advisory_xact_lock(hashtext(:id))"), {"id": identifier}
        ):
            abort(409, "Un trabajo sigue ejecutándose. Cancélelo y espere a que termine.")
    if value["active_jobs"]:
        abort(409, "Hay trabajos en curso. Cancélelos y espere antes de eliminar.")
    list(
        db.session.scalars(
            select(ReviewCase)
            .where(ReviewCase.id.in_(p["case_ids"]))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    value = plan(data)
    p = value["internal"]
    if data.get("fingerprint") != value["fingerprint"]:
        abort(409, "La lista cambió. Revise de nuevo el alcance antes de eliminar.")
    if value["empty"]:
        abort(422, "No hay registros para eliminar.")
    object_keys = set()
    for result in p["result_rows"]:
        if result.mask_key:
            object_keys.update((result.mask_key, result.mask_key + ".png", result.mask_key + ".json"))
    object_keys.update(a.object_key for a in p["attachments"])
    object_keys.update(j.output_key for j in p["derived_jobs"] if j.output_key)
    db.session.execute(
        update(Parcel).where(Parcel.current_result_id.in_(p["result_ids"])).values(current_result_id=None)
    )
    db.session.execute(delete(ReviewAttachment).where(ReviewAttachment.case_id.in_(p["case_ids"])))
    db.session.execute(delete(ReviewAction).where(ReviewAction.case_id.in_(p["case_ids"])))
    db.session.execute(delete(ReviewCase).where(ReviewCase.id.in_(p["case_ids"])))
    db.session.execute(delete(BuildingFootprint).where(BuildingFootprint.result_id.in_(p["result_ids"])))
    db.session.execute(
        delete(ParcelComparisonResult).where(ParcelComparisonResult.run_id.in_(p["comparisons"]))
    )
    db.session.execute(delete(ComparisonRun).where(ComparisonRun.id.in_(p["comparisons"])))
    db.session.execute(delete(ParcelAnalysisResult).where(ParcelAnalysisResult.id.in_(p["result_ids"])))
    db.session.execute(delete(BulkSelectionItem).where(BulkSelectionItem.id.in_(p["item_ids"])))
    for batch in db.session.scalars(select(BulkSelection).where(BulkSelection.id.in_(p["batch_ids"]))):
        batch.total = db.session.scalar(
            select(func.count())
            .select_from(BulkSelectionItem)
            .where(BulkSelectionItem.selection_id == batch.id)
        )
        if batch.total == 0:
            db.session.delete(batch)
    for job in p["affected_jobs"]:
        if job.id in p["remaining_payloads"]:
            ids = p["remaining_payloads"][job.id]
            payload = {**job.payload, "parcel_ids": ids}
            for name in ("expected_versions", "skip_reasons"):
                if name in payload:
                    payload[name] = {key: val for key, val in payload[name].items() if key in ids}
            job.payload = payload
            job.idempotency_key = "cleaned:" + job.id
            job.total = len(ids)
            job.processed = db.session.scalar(
                select(func.count())
                .select_from(ParcelAnalysisResult)
                .join(AnalysisRun)
                .where(AnalysisRun.job_id == job.id)
            )
    db.session.execute(delete(AnalysisRun).where(AnalysisRun.job_id.in_(p["delete_jobs"])))
    removed_jobs = p["delete_jobs"] | {j.id for j in p["derived_jobs"]}
    db.session.execute(delete(Job).where(Job.id.in_(removed_jobs)))
    db.session.execute(delete(AuditLog).where(AuditLog.entity_id.in_(p["audit_targets"])))
    cleanup_rows = [{"kind": "object", "key": key} for key in object_keys]
    cleanup_rows += [
        {"kind": "rq", "key": json.dumps([current_app.config["RQ_QUEUE"], identifier])}
        for identifier in removed_jobs
    ]
    for start in range(0, len(cleanup_rows), 500):
        db.session.execute(
            insert(CleanupEntry)
            .values(cleanup_rows[start : start + 500])
            .on_conflict_do_nothing(index_elements=["kind", "key"])
        )
    audit(
        "ANALYSIS_DATA_DELETED", details={"target": data["target"], "mode": data["mode"], **value["counts"]}
    )
    db.session.commit()
    return value["counts"]
