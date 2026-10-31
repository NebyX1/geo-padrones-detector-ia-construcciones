"""Remove only RQ resources of an explicitly identified disposable QA queue."""

import re
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError


def cleanup_queue(name, redis_url):
    if not re.fullmatch(r"geopadrones-qa-[0-9a-f]{10}", name):
        raise ValueError("Cola QA inválida.")
    connection = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=5)
    queue = Queue(name, connection=connection)
    registries = [
        queue.finished_job_registry,
        queue.failed_job_registry,
        queue.started_job_registry,
        queue.deferred_job_registry,
        queue.scheduled_job_registry,
        queue.canceled_job_registry,
    ]
    identifiers = set(queue.get_job_ids())
    for registry in registries:
        identifiers.update(registry.get_job_ids())
    for identifier in identifiers:
        try:
            job = Job.fetch(identifier, connection=connection)
            if job.origin != name:
                raise ValueError("Un trabajo de otra cola no se elimina.")
            job.delete()
        except NoSuchJobError:
            pass
    queue.delete(delete_jobs=True)
    for registry in registries:
        connection.delete(registry.key)
    connection.close()
