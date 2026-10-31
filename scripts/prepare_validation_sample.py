"""Prepare an independent, unlabeled sample of real parcels; never invent ground truth."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import _bootstrap
from sqlalchemy import select, text
from app import create_app
from app.extensions import db
from app.models import ImageryScene
from app.services.official import MINAS_COVERAGE

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("artifacts/validation/sample-200.csv"))
args = parser.parse_args()
with create_app().app_context():
    scene = db.session.scalar(select(ImageryScene).where(ImageryScene.coverage_id == MINAS_COVERAGE))
    if not scene:
        raise SystemExit("Registre la escena de Minas antes de preparar la muestra.")
    bounds = scene.metadata_json["bounds_wgs84"]
    rows = (
        db.session.execute(
            text("""WITH candidates AS (
        SELECT p.id,p.coddepto,p.codloccat,p.padron,p.m2_parcela,p.source_version_id,l.name locality,
               ntile(4) OVER (ORDER BY p.m2_parcela,p.id) stratum
        FROM parcels p JOIN localities l ON l.id=p.locality_id
        WHERE p.active AND p.m2_parcela BETWEEN 20 AND 10000
          AND ST_CoveredBy(p.geom,ST_MakeEnvelope(:west,:south,:east,:north,4326))
    ), ranked AS (
        SELECT *,row_number() OVER(PARTITION BY stratum ORDER BY md5(coddepto||codloccat||padron||'lavalleja-validation-v1')) position
        FROM candidates
    ) SELECT * FROM ranked WHERE position<=50 ORDER BY stratum,position"""),
            dict(zip(("west", "south", "east", "north"), bounds)),
        )
        .mappings()
        .all()
    )
    if len(rows) != 200:
        raise SystemExit(f"Hay {len(rows)} candidatos: se requieren 50 por cuartil de superficie.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "parcel_id",
        "coddepto",
        "codloccat",
        "padron",
        "locality",
        "parcel_version_id",
        "m2_parcela",
        "scene_id",
        "image_month",
        "stratum",
        "semantic_stratum",
        "true_building",
        "true_footprint_m2",
        "reviewer",
        "reviewed_at",
        "image_valid",
        "observations",
        "predicted_building",
        "predicted_footprint_m2",
    ]
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                dict(
                    parcel_id=row["id"],
                    coddepto=row["coddepto"],
                    codloccat=row["codloccat"],
                    padron=row["padron"],
                    locality=row["locality"],
                    parcel_version_id=row["source_version_id"],
                    m2_parcela=row["m2_parcela"],
                    scene_id=scene.id,
                    image_month=scene.captured_at,
                    stratum=f"area_quartile_{row['stratum']}",
                )
            )
    manifest = dict(
        created_at=datetime.now(timezone.utc).isoformat(),
        count=200,
        independently_labelled=False,
        predictions_generated=False,
        selection="50 per cadastral area quartile, deterministic identity hash; official imagery bounding rectangle only",
        notice="Check valid imagery and semantic strata manually. No geometry or class labels were fabricated.",
        sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
    )
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Muestra REAL sin etiquetas: {len(rows)} padrones · {args.output}")
