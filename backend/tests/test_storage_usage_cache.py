from types import SimpleNamespace
import pytest
from minio.error import S3Error
from redis.exceptions import RedisError
from app.services.storage import ObjectStorage


class Cache:
    def __init__(self):
        self.values = {}
        self.run_id = "first-run"

    def info(self, *args):
        return {"run_id": self.run_id}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        self.values[key] = value.encode()

    def delete(self, key):
        self.values.pop(key, None)

    def close(self):
        pass


class Bucket:
    def __init__(self):
        self.objects = {}
        self.listings = 0
        self.interrupt = False

    def list_objects(self, *args, **kwargs):
        self.listings += 1
        return [SimpleNamespace(size=len(raw), object_name=key) for key, raw in self.objects.items()]

    def stat_object(self, bucket, key):
        if key not in self.objects:
            raise S3Error(None, "NoSuchKey", "test missing", key, "test", "test")
        return SimpleNamespace(size=len(self.objects[key]))

    def put_object(self, bucket, key, source, length, **kwargs):
        self.objects[key] = source.read(length)
        if self.interrupt:
            self.interrupt = False
            raise RuntimeError("Simulated interruption after S3 commit")


@pytest.fixture
def objects(context, monkeypatch):
    monkeypatch.setitem(context.config, "STORAGE_BACKEND", "minio")
    monkeypatch.setitem(context.config, "MAX_STORAGE_BYTES", 10)
    cache = Cache()
    bucket = Bucket()
    monkeypatch.setattr("app.services.storage.Redis.from_url", lambda *args, **kwargs: cache)
    instance = ObjectStorage()
    instance.client = bucket
    return instance, cache, bucket


def test_many_uploads_and_overwrites_share_exact_usage_without_relisting(objects):
    storage, cache, bucket = objects
    storage.put("a", b"12345")
    storage.put("b", b"1234")
    with pytest.raises(ValueError, match="cuota"):
        storage.put("c", b"12")
    storage.put("a", b"12")
    storage.put("c", b"1234")
    assert sum(map(len, bucket.objects.values())) == 10 and bucket.listings == 1


def test_interrupted_upload_and_redis_restart_reconcile_real_bytes(objects):
    storage, cache, bucket = objects
    bucket.interrupt = True
    with pytest.raises(RuntimeError):
        storage.put("a", b"123456")
    with pytest.raises(ValueError, match="cuota"):
        storage.put("b", b"12345")
    storage.put("b", b"12")
    bucket.objects["external-recovery"] = b"12"
    cache.run_id = "restarted"
    with pytest.raises(ValueError, match="cuota"):
        storage.put("c", b"1")
    assert "c" not in bucket.objects


def test_unavailable_quota_cache_refuses_writes(objects, monkeypatch):
    storage, cache, bucket = objects

    def offline(*args):
        raise RedisError("test outage")

    monkeypatch.setattr(cache, "info", offline)
    with pytest.raises(ValueError, match="Redis"):
        storage.put("a", b"1")
    assert bucket.objects == {}
