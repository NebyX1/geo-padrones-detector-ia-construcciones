import hashlib
import json
from flask import abort, current_app
from redis import Redis
from rq import Queue, Retry
from rq.job import Callback
from sqlalchemy import select, update
from ..extensions import db
from ..models import Job


def redis_connection():
    return Redis.from_url(current_app.config["REDIS_URL"], socket_connect_timeout=3, socket_timeout=5)


def new_job(kind, user_id, payload, key=None, total=0):
    payload = json.loads(json.dumps(payload, default=str))
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    key = key or digest
    if len(key) > 64 or not key:
        abort(422, "Clave de idempotencia inválida.")
    # Transactional DB outbox: PENDING is durable even if Redis is temporarily unavailable.
    db.session.execute(
        db.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{user_id}:{kind}:{key}"}
    )
    existing = db.session.execute(
        select(Job).where(Job.user_id == user_id, Job.kind == kind, Job.idempotency_key == key)
    ).scalar_one_or_none()
    if existing:
        if existing.payload != payload:
            abort(409, "La clave de idempotencia ya corresponde a otros parámetros.")
        return existing, False
    job = Job(kind=kind, user_id=user_id, payload=payload, total=total, idempotency_key=key)
    db.session.add(job)
    db.session.flush()
    return job, True


def dispatch(job):
    try:
        connection = redis_connection()
        queue = Queue(current_app.config["RQ_QUEUE"], connection=connection)
        if not queue.fetch_job(job.id):
            queue.enqueue(
                "app.tasks.execute_job",
                job.id,
                job_id=job.id,
                job_timeout=3600,
                retry=Retry(max=1, interval=30),
                result_ttl=86400,
                failure_ttl=604800,
                on_failure=Callback("app.rq_callbacks.failed", timeout=30),
            )
        db.session.execute(
            update(Job).where(Job.id == job.id, Job.status == "PENDING").values(status="QUEUED")
        )
        db.session.commit()
        db.session.refresh(job)
    except Exception:
        db.session.rollback()
        # Dispatcher can safely retry PENDING jobs; never claim Redis accepted a failed enqueue.
        current_app.logger.warning(json.dumps({"event": "queue_unavailable", "job_id": job.id}))
