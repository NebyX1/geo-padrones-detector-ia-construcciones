import json
import statistics
import time
from pathlib import Path
import _bootstrap
from app import create_app
from app.extensions import db

with create_app().app_context():
    statement = db.text("""SELECT id,ST_AsGeoJSON(geom) FROM parcels
        WHERE active AND ST_Intersects(geom,ST_Transform(ST_MakeEnvelope(661968,6194614,662228,6194874,5382),4326)) LIMIT 1000""")
    elapsed = []
    count = 0
    for _ in range(20):
        start = time.perf_counter()
        rows = db.session.execute(statement).all()
        elapsed.append((time.perf_counter() - start) * 1000)
        count = len(rows)
    plan = db.session.execute(db.text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(statement))).scalar()
    report = {
        "real_database": True,
        "scope": "sector real Minas 260x260 m",
        "iterations": 20,
        "returned_parcels": count,
        "median_ms": statistics.median(elapsed),
        "p95_ms": sorted(elapsed)[18],
        "first_ms": elapsed[0],
        "plan": plan,
        "notice": "Medición local con caché caliente; no sustituye una prueba de carga concurrente.",
    }
    target = Path("artifacts/spatial-benchmark.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "plan"}, indent=2))
