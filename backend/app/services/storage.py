import io
from pathlib import Path, PurePosixPath
from flask import current_app
from minio import Minio
from urllib3 import PoolManager, Timeout, Retry
from redis import Redis
from redis.exceptions import RedisError
from minio.error import S3Error
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
                    self._put_with_quota(key, content, content_type)
                finally:
                    connection.execute(
                        db.text("SELECT pg_advisory_unlock(hashtext(:name))"), {"name": lock_name}
                    )
        return key

    def _put_with_quota(self, key, content, content_type):
        """Global usage cache under the PostgreSQL lock; no full S3 listing per mask.

        Invalidate before writing so interrupted uploads force reconciliation. The
        Redis server run-id rejects stale AOF cache values after a Redis restart.
        """
        counter = Redis.from_url(self.config["REDIS_URL"], socket_connect_timeout=2, socket_timeout=3)
        cache_key = "geopadrones:storage-usage:" + self.bucket
        try:
            server_id = counter.info("server")["run_id"]
            cached = counter.get(cache_key)
            previous_id, _, amount = cached.decode().partition(":") if cached else ("", "", "")
            used = (
                int(amount)
                if previous_id == server_id and amount.isdigit()
                else sum(obj.size for obj in self.client.list_objects(self.bucket, recursive=True))
            )
            try:
                old_size = self.client.stat_object(self.bucket, key).size
            except S3Error as error:
                if error.code not in {"NoSuchKey", "NoSuchObject"}:
                    raise
                old_size = 0
            new_size = max(0, used - old_size) + len(content)
            if new_size > self.config["MAX_STORAGE_BYTES"]:
                raise ValueError("Se alcanzó la cuota de almacenamiento; libere espacio o amplíe el límite.")
            counter.delete(cache_key)
            self.client.put_object(
                self.bucket, key, io.BytesIO(content), len(content), content_type=content_type
            )
            try:
                counter.set(cache_key, f"{server_id}:{new_size}", ex=300)
            except RedisError:
                pass  # The key was invalidated; the next writer reconciles actual objects.
        except RedisError:
            raise ValueError(
                "No se pudo sincronizar la cuota de almacenamiento con Redis. Reintente cuando el servicio esté disponible."
            ) from None
        finally:
            counter.close()

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

    def delete(self, key):
        key = safe_key(key)
        if self.local:
            (self.root / key).unlink(missing_ok=True)
            return
        with db.engine.connect() as connection:
            lock_name = "storage-quota:" + self.bucket
            connection.execute(db.text("SET LOCAL statement_timeout='15s'"))
            connection.execute(db.text("SELECT pg_advisory_lock(hashtext(:name))"), {"name": lock_name})
            try:
                counter = Redis.from_url(self.config["REDIS_URL"], socket_connect_timeout=2, socket_timeout=3)
                try:
                    counter.delete("geopadrones:storage-usage:" + self.bucket)
                    self.client.remove_object(self.bucket, key)
                finally:
                    counter.close()
            finally:
                connection.execute(db.text("SELECT pg_advisory_unlock(hashtext(:name))"), {"name": lock_name})


def storage():
    return ObjectStorage()
