"""Retry object/queue deletion after the database transaction has committed."""

import json
from flask import current_app
from sqlalchemy import select
from rq.job import Job as QueueJob
from rq.exceptions import NoSuchJobError
from ..extensions import db
from ..models import CleanupEntry
from .queue import redis_connection
from .storage import storage


def collect_garbage(limit=30):
    entries = list(
        db.session.scalars(
            select(CleanupEntry)
            .order_by(CleanupEntry.attempts, CleanupEntry.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    removed = 0
    for entry in entries:
        try:
            if entry.kind == "object":
                storage().delete(entry.key)
            elif entry.kind == "rq":
                queue_name, identifier = json.loads(entry.key)
                connection = redis_connection()
                try:
                    try:
                        job = QueueJob.fetch(identifier, connection=connection)
                        if job.origin != queue_name:
                            raise ValueError("La cola no corresponde al trabajo eliminado.")
                        job.delete()
                    except NoSuchJobError:
                        pass
                finally:
                    connection.close()
            else:
                raise ValueError("Tipo de limpieza no reconocido.")
            db.session.delete(entry)
            removed += 1
        except Exception as exc:
            entry.attempts += 1
            current_app.logger.warning(json.dumps({"event": "cleanup_retry", "type": type(exc).__name__}))
    db.session.commit()
    return removed
