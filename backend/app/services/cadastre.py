import hashlib
import json
from pathlib import Path
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select, text
from ..extensions import db
from ..models import (
    CadastralDatasetVersion,
    CadastralLocality,
    Parcel,
    ParcelGeometryVersion,
    LandUseCategory,
)
from .geospatial import validate_wgs84, reproject


def normalize_id(value):
    value = str(value if value is not None else "").strip().upper()
    if not value or len(value) > 40 or not all(c.isalnum() or c in "-_" for c in value):
        raise ValueError("Identificador catastral vacío o inválido.")
    # Leading zeroes remain significant; do not convert to int.
    return value


def import_file(filename, land_use=False):
    filename = Path(filename)
    manifest = json.loads(filename.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    with filename.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("Hash del archivo no coincide con el manifiesto.")
    # Serialize imports, including concurrent import of the same snapshot.
    db.session.execute(text("SELECT pg_advisory_xact_lock(805382)"))
    existing = db.session.execute(
        select(CadastralDatasetVersion).where(CadastralDatasetVersion.sha256 == digest)
    ).scalar_one_or_none()
    if existing:
        return dict(id=existing.id, idempotent=True, count=existing.count)
    version = CadastralDatasetVersion(
        sha256=digest, source=manifest["source"], count=0, metadata_json=manifest
    )
    db.session.add(version)
    db.session.flush()
    localities, parcels, issues, count, repairs, duplicate_keys = {}, {}, [], 0, 0, 0
    for line_number, line in enumerate(filename.open(encoding="utf-8"), start=1):
        feature = json.loads(line)
        try:
            geom = validate_wgs84(feature["geometry"])
            repaired = not shape(feature["geometry"]).is_valid
            repairs += int(repaired)
            props = feature["properties"]
            if land_use:
                row = db.session.execute(
                    select(LandUseCategory).where(LandUseCategory.source_feature_id == feature["id"])
                ).scalar_one_or_none()
                if row is None:
                    row = LandUseCategory(source_feature_id=feature["id"])
                    db.session.add(row)
                row.properties, row.geom, row.source = props, from_shape(geom, srid=4326), manifest["source"]
            else:
                key = tuple(normalize_id(props.get(k)) for k in ("coddepto", "codloccat", "padron"))
                if str(props.get("nomdepto", "")).upper() != "LAVALLEJA":
                    raise ValueError("Parcela fuera del filtro departamental.")
                loc_key = key[:2]
                if loc_key not in localities:
                    loc = db.session.execute(
                        select(CadastralLocality).where(
                            CadastralLocality.coddepto == key[0], CadastralLocality.codloccat == key[1]
                        )
                    ).scalar_one_or_none()
                    if not loc:
                        loc = CadastralLocality(
                            coddepto=key[0], codloccat=key[1], name=props.get("nomloccat") or key[1]
                        )
                        db.session.add(loc)
                        db.session.flush()
                    localities[loc_key] = loc
                parcel = parcels.get(key)
                if parcel:
                    duplicate_keys += 1
                else:
                    parcel = db.session.execute(
                        select(Parcel).where(
                            Parcel.coddepto == key[0], Parcel.codloccat == key[1], Parcel.padron == key[2]
                        )
                    ).scalar_one_or_none()
                    if parcel is None:
                        parcel = Parcel(
                            coddepto=key[0],
                            codloccat=key[1],
                            padron=key[2],
                            locality_id=localities[loc_key].id,
                            geom=from_shape(geom, srid=4326),
                            m2_parcela=reproject(geom).area,
                            source_version_id=version.id,
                        )
                        db.session.add(parcel)
                        db.session.flush()
                    parcels[key] = parcel
                db.session.add(
                    ParcelGeometryVersion(
                        parcel_id=parcel.id,
                        dataset_version_id=version.id,
                        source_feature_id=feature["id"],
                        original=feature,
                        geom=from_shape(geom, srid=4326),
                        repaired=repaired,
                    )
                )
            count += 1
            if count % 500 == 0:
                db.session.flush()
                print(f"Importadas {count} geometrías", flush=True)
        except (ValueError, KeyError) as exc:
            issues.append(dict(line=line_number, feature_id=feature.get("id"), error=str(exc)))
    db.session.flush()
    if not land_use:
        # Exact official geometry remains untouched in history; union only the working identity.
        db.session.execute(
            text("""
            UPDATE parcels p SET current_result_id = CASE WHEN ST_Equals(p.geom,pieces.geom) THEN p.current_result_id ELSE NULL END,
                geom = pieces.geom,
                m2_parcela = ST_Area(ST_Transform(pieces.geom, 5382)), source_version_id = :version,
                active = true
            FROM (SELECT parcel_id, ST_Multi(ST_UnaryUnion(ST_Collect(geom))) AS geom
                  FROM parcel_geometries WHERE dataset_version_id = :version GROUP BY parcel_id) pieces
            WHERE p.id = pieces.parcel_id
        """),
            {"version": version.id},
        )
    if not count:
        raise ValueError("No se importará una versión vacía del catastro.")
    retired = 0
    if not land_use and manifest.get("complete") and not manifest.get("bbox") and not issues:
        missing = db.session.execute(
            text(
                "SELECT count(*) FROM parcels WHERE coddepto=:department AND source_version_id<>:version AND active"
            ),
            {"department": "P", "version": version.id},
        ).scalar()
        if missing > len(parcels):
            raise ValueError(
                "La nueva instantánea retiraría más de la mitad de las identidades. Revise la fuente antes de aplicar una actualización masiva."
            )
        retired = db.session.execute(
            text(
                "UPDATE parcels SET active=false WHERE coddepto=:department AND source_version_id<>:version AND active"
            ),
            {"department": "P", "version": version.id},
        ).rowcount
    version.count = count
    version.metadata_json = {
        **manifest,
        "issues": issues,
        "repairs": repairs,
        "duplicate_keys": duplicate_keys,
        "identity_count": len(parcels),
        "retired_identities": retired,
        "missing_from_new_snapshot_policy": "complete snapshots retire absent identities without deleting history; partial snapshots retain absent identities",
    }
    db.session.commit()
    return dict(
        id=version.id,
        count=count,
        identities=len(parcels),
        repairs=repairs,
        issues=issues,
        duplicate_keys=duplicate_keys,
        retired=retired,
    )
