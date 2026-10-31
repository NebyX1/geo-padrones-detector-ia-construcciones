"""Disposable browser-test database and worker. No persistent account or credential file.

All data mutations target a random geopadrones_qa_* database and a private temporary bucket.
The only account is the public test fixture specified in frontend/e2e; finally removes the DB.
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
import _bootstrap
import psycopg
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url
from flask_migrate import upgrade
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, box
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import User, AIModelVersion
from app.services.cadastre import import_file
from app.services.imagery import register_minas
from app.services.geospatial import reproject
from app.services.storage import storage
from qa_resources import cleanup_queue


def main():
    app = create_app()
    if app.config["PRODUCTION"]:
        raise SystemExit("QA temporal está prohibida en producción.")
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    print("QA: creando base temporal", flush=True)
    suffix = uuid.uuid4().hex[:10]
    database, bucket, queue = (
        f"geopadrones_qa_{suffix}",
        f"geopadrones-qa-{suffix}",
        f"geopadrones-qa-{suffix}",
    )
    admin = psycopg.connect(
        host="127.0.0.1" if url.host == "localhost" else url.host,
        port=url.port or 5432,
        dbname="postgres",
        user=url.username,
        password=url.password,
        autocommit=True,
        connect_timeout=5,
    )
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": url.set(database=database).render_as_string(hide_password=False),
            "MINIO_BUCKET": bucket,
            "RQ_QUEUE": queue,
            "MAIL_SUPPRESS_SEND": False,
            "RATELIMIT_ENABLED": True,
        },
    )
    # Testing is used solely for propagation of errors; all production mechanisms (CSRF, sessions,
    # PostGIS, SMTP delivery, RQ, MinIO and actual FLAIR inference) remain enabled.
    worker_name = f"geopadrones-qa-worker-{suffix}"
    process = None
    try:
        with app.app_context():
            print("QA: aplicando migraciones", flush=True)
            upgrade(directory=str(_bootstrap.ROOT / "backend/migrations"))
            storage().init()
            print("QA: cargando muestra real", flush=True)
            # Copy a bounded sample of REAL official geometries near the real benchmark sector.
            sector = reproject(box(661968, 6194614, 662228, 6194874), 5382, 4326)
            features = []
            for line in (_bootstrap.ROOT / "data/raw/lavalleja.ndjson").open(encoding="utf-8"):
                feature = json.loads(line)
                if shape(feature["geometry"]).intersects(sector):
                    features.append(feature)
            source = _bootstrap.ROOT / "data/runtime" / f"{database}.ndjson"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("\n".join(json.dumps(f) for f in features) + "\n", encoding="utf-8")
            import hashlib

            manifest = {
                "source": "https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "count": len(features),
                "scope": "BOUNDED REAL-DATA QA SAMPLE",
            }
            source.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            import_file(source)
            register_minas()
            model = json.loads((_bootstrap.ROOT / "data/models/manifest.json").read_text())
            db.session.add(
                AIModelVersion(
                    model_id=model["model_id"],
                    revision=model["revision"],
                    sha256=model["sha256"],
                    filename=model["filename"],
                    license=model["license"],
                    metadata_json=model,
                )
            )
            user = User(
                email="browser-test@example.org", name="Prueba temporal de navegador", role="superadmin"
            )
            user.set_password("Disposable-browser-test-only-2026")
            db.session.add(user)
            db.session.commit()
            child_env = os.environ.copy()
            for key in ["SECRET_KEY", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]:
                child_env[key] = str(app.config[key])
            child_env.update(
                DATABASE_URL=url.set(host="postgres-postgis", database=database).render_as_string(
                    hide_password=False
                ),
                REDIS_URL="redis://redis:6379/0",
                MINIO_ENDPOINT="minio:9000",
                MINIO_BUCKET=bucket,
                MINIO_SECURE="false",
                RQ_QUEUE=queue,
                FLASK_CONFIG="development",
                MODEL_DIR="/data/models",
                DATA_DIR="/data/runtime",
            )
            command = [
                "docker",
                "run",
                "--rm",
                "--name",
                worker_name,
                "--network",
                "geopadrones_outbound",
                "--cpus",
                "2",
                "--memory",
                "4g",
                "-v",
                f"{_bootstrap.ROOT / 'data/models'}:/data/models:ro",
            ]
            for key in [
                "SECRET_KEY",
                "DATABASE_URL",
                "REDIS_URL",
                "MINIO_ENDPOINT",
                "MINIO_ACCESS_KEY",
                "MINIO_SECRET_KEY",
                "MINIO_BUCKET",
                "MINIO_SECURE",
                "RQ_QUEUE",
                "FLASK_CONFIG",
                "MODEL_DIR",
                "DATA_DIR",
            ]:
                command.extend(["-e", key])  # Values come from environment, never visible process arguments.
            command.append("geopadrones-worker:local")
            process = subprocess.Popen(
                command, env=child_env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            print(
                f"QA temporal lista: http://127.0.0.1:5051 · {len(features)} geometrías reales · sin cuenta persistente",
                flush=True,
            )
        make_server("127.0.0.1", 5051, app, threaded=True).serve_forever()
    finally:
        if process:
            subprocess.run(
                ["docker", "stop", "--time", "5", worker_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            process.wait(timeout=15)
        with app.app_context():
            client = storage()
            if not client.local and client.client.bucket_exists(bucket):
                for obj in client.client.list_objects(bucket, recursive=True):
                    client.client.remove_object(bucket, obj.object_name)
                client.client.remove_bucket(bucket)
            cleanup_queue(queue, app.config["REDIS_URL"])
            db.session.remove()
            db.engine.dispose()
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        admin.close()
        print("Base, cuenta y bucket temporales de QA eliminados.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
