"""Remove only explicitly named QA databases/buckets created by qa_server.py."""

import argparse
import re
import subprocess
import _bootstrap
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from app import create_app
from app.services.storage import storage
from qa_resources import cleanup_queue

parser = argparse.ArgumentParser()
parser.add_argument("databases", nargs="+")
args = parser.parse_args()
app = create_app()
if app.config["PRODUCTION"]:
    raise SystemExit("No se permite limpieza QA en producción.")
with app.app_context():
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    admin = psycopg.connect(
        host="127.0.0.1" if url.host == "localhost" else url.host,
        port=url.port or 5432,
        dbname="postgres",
        user=url.username,
        password=url.password,
        autocommit=True,
        connect_timeout=5,
    )
    objects = storage()
    for name in args.databases:
        if (
            not re.fullmatch(r"geopadrones_qa_[0-9a-f]{10}", name)
            or not (_bootstrap.ROOT / "data/runtime" / f"{name}.manifest.json").is_file()
        ):
            raise SystemExit("Nombre o evidencia local de propiedad de la base QA inválidos.")
        suffix = name.removeprefix("geopadrones_qa_")
        subprocess.run(
            ["docker", "stop", "--time", "3", f"geopadrones-qa-worker-{suffix}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        bucket = f"geopadrones-qa-{suffix}"
        if objects.client.bucket_exists(bucket):
            for obj in objects.client.list_objects(bucket, recursive=True):
                objects.client.remove_object(bucket, obj.object_name)
            objects.client.remove_bucket(bucket)
        cleanup_queue(bucket, app.config["REDIS_URL"])
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        print(f"Eliminados únicamente base y bucket temporales: {name}", flush=True)
    admin.close()
