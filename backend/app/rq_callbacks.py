"""Lightweight callbacks also run when loading the inference module fails."""

from . import create_app
from .extensions import db
from .models import Job, utcnow


def failed(rq_job, connection, exc_type, exc_value, traceback):
    with create_app().app_context():
        job = db.session.get(Job, rq_job.id)
        if job and job.status not in {"COMPLETED", "CANCELLED"}:
            job.status = "FAILED"
            job.error = f"Worker: {getattr(exc_type, '__name__', 'error')}"
            job.finished_at = utcnow()
            db.session.commit()
