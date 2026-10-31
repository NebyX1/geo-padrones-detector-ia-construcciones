"""CPU worker; one model instance per process, no inference in Gunicorn."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import create_app
from redis import Redis
from rq import Worker

if __name__ == "__main__":
    with create_app().app_context() as context:
        connection = Redis.from_url(context.app.config["REDIS_URL"])
        Worker([context.app.config["RQ_QUEUE"]], connection=connection).work(with_scheduler=True)
