import time
import _bootstrap
from app import create_app
from app.extensions import db
from app.models import Job, CleanupEntry
from app.services.queue import dispatch
from app.services.garbage_collection import collect_garbage
from sqlalchemy import select, func

app = create_app()
while True:
    with app.app_context():
        for job in db.session.execute(select(Job).where(Job.status == "PENDING").limit(100)).scalars():
            dispatch(job)
        removed = collect_garbage(limit=100)
        cleaning = db.session.scalar(select(func.count()).select_from(CleanupEntry)) > 0
    time.sleep(1 if cleaning and removed else 15)
