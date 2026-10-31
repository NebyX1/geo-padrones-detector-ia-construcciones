import time
import _bootstrap
from app import create_app
from app.extensions import db
from app.models import Job
from app.services.queue import dispatch
from sqlalchemy import select

app = create_app()
while True:
    with app.app_context():
        for job in db.session.execute(select(Job).where(Job.status == "PENDING").limit(100)).scalars():
            dispatch(job)
    time.sleep(15)
