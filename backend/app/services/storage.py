import io
from pathlib import Path, PurePosixPath
from flask import current_app
from minio import Minio
from urllib3 import PoolManager, Timeout, Retry
from ..extensions import db


def safe_key(key):
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or "\\" in key:
        raise ValueError("Clave de objeto inválida.")
    return str(path)


class ObjectStorage:
    def __init__(self):
        self.config = current_app.config
        self.local = self.config["STORAGE_BACKEND"] == "local"
        self.bucket = self.config["MINIO_BUCKET"]
        if self.local:
            if self.config["PRODUCTION"]:
                raise RuntimeError("Producción requiere almacenamiento MinIO/S3 privado.")
            self.root = Path(self.config["DATA_DIR"]) / "objects"
            self.root.mkdir(parents=True, exist_ok=True)
        else:
            self.client = Minio(
                self.config["MINIO_ENDPOINT"],
                access_key=self.config["MINIO_ACCESS_KEY"],
                secret_key=self.config["MINIO_SECRET_KEY"],
                secure=self.config["MINIO_SECURE"],
                http_client=PoolManager(
                    timeout=Timeout(connect=3, read=30), retries=Retry(total=2, backoff_factor=0.5)
                ),
            )

    def init(self):
        if not self.local and not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def healthy(self):
        return self.root.is_dir() if self.local else self.client.bucket_exists(self.bucket)

    def put(self, key, content, content_type="application/octet-stream"):
        key = safe_key(key)
        if self.local:
            path = self.root / key
            used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file() and p != path)
            if used + len(content) > self.config["MAX_STORAGE_BYTES"]:
                raise ValueError("Se alcanzó la cuota de almacenamiento; libere espacio o amplíe el límite.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        else:
            with db.engine.connect() as connection:
                connection.execute(db.text("SET LOCAL statement_timeout='15s'"))
                lock_name = "storage-quota:" + self.bucket
                connection.execute(db.text("SELECT pg_advisory_lock(hashtext(:name))"), {"name": lock_name})
                try:
                    used = sum(
                        o.size
                        for o in self.client.list_objects(self.bucket, recursive=True)
                        if o.object_name != key
                    )
                    if used + len(content) > self.config["MAX_STORAGE_BYTES"]:
                        raise ValueError(
                            "Se alcanzó la cuota de almacenamiento; libere espacio o amplíe el límite."
                        )
                    self.client.put_object(
                        self.bucket, key, io.BytesIO(content), len(content), content_type=content_type
                    )
                finally:
                    connection.execute(
                        db.text("SELECT pg_advisory_unlock(hashtext(:name))"), {"name": lock_name}
                    )
        return key

    def get(self, key):
        key = safe_key(key)
        if self.local:
            return (self.root / key).read_bytes()
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def storage():
    return ObjectStorage()
