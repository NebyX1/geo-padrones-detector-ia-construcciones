"""Importa identidades faltantes del GeoJSON preparado, sin sustituir el WFS.

La importación es explícita y transaccional. Conserva resultados, geometrías y
versiones ya existentes; las identidades rurales usan la localidad técnica R.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select, text

from ..extensions import db
from ..models import CadastralDatasetVersion, CadastralLocality, Parcel, ParcelGeometryVersion, uid
from .cadastre import normalize_id
from .geospatial import reproject, validate_wgs84


def _features(path):
    """Lee en streaming el FeatureCollection generado por GeoPadrones.

    El generador escribe una cabecera seguida de una feature completa por
    línea; se valida la envoltura y se falla ante archivos truncados o formato
    distinto en vez de importar silenciosamente solo una parte.
    """
    with Path(path).open(encoding="utf-8") as stream:
        header = stream.readline()
        prefix, marker, suffix = header.partition('"features":[')
        if not marker or suffix.strip() or not prefix.rstrip().endswith(","):
            raise ValueError("Formato GeoJSON preparado inesperado en la cabecera.")
        document = json.loads(prefix.rstrip()[:-1] + "}")
        if document.get("type") != "FeatureCollection":
            raise ValueError("Se esperaba un FeatureCollection.")
        needs_item = False
        saw_item = False
        for line in stream:
            value = line.strip()
            if not value:
                continue
            if value == "]}":
                if needs_item or stream.read().strip():
                    raise ValueError("GeoJSON incompleto o con contenido adicional.")
                return
            if saw_item and not needs_item:
                raise ValueError("Falta una coma entre elementos GeoJSON.")
            needs_item = value.endswith(",")
            feature = json.loads(value[:-1] if needs_item else value)
            if feature.get("type") != "Feature":
                raise ValueError("Se esperaba una feature GeoJSON.")
            saw_item = True
            yield feature
        raise ValueError("GeoJSON truncado: falta el cierre de la colección.")


def _import_geojson_parcels(filename):
    """Añade parcelas faltantes con geometría y retorna conteos de auditoría.

    Nunca actualiza ni reactiva un padrón preexistente. Se preservan geometría
    original y versión catastral propia; se omiten identidades sin geometría.
    Puede llamarse de nuevo sin duplicados. La transacción solo se confirma si
    se llega al final válido del archivo.
    """
    filename = Path(filename)
    with filename.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    db.session.execute(text("SELECT pg_advisory_xact_lock(805382)"))
    existing = db.session.scalar(
        select(CadastralDatasetVersion).where(CadastralDatasetVersion.sha256 == digest)
    )
    if existing:
        result = {"id": existing.id, "idempotent": True, **existing.metadata_json.get("import_summary", {})}
        db.session.commit()
        return result

    version = CadastralDatasetVersion(
        sha256=digest,
        source="GeoJSON de Catastro y geometrías de Lavalleja preparado por GeoPadrones",
        count=0,
        metadata_json={},
    )
    db.session.add(version)
    db.session.flush()
    # Reserve the same namespace that appears in the GeoJSON identity P:R:n.
    localities = {
        (loc.coddepto, loc.codloccat): loc
        for loc in db.session.scalars(select(CadastralLocality).where(CadastralLocality.coddepto == "P"))
    }
    existing_keys = {
        (coddepto, loc, number)
        for coddepto, loc, number in db.session.execute(
            select(Parcel.coddepto, Parcel.codloccat, Parcel.padron).where(Parcel.coddepto == "P")
        )
    }
    summary = {"importadas": 0, "existentes": 0, "sin_geometria": 0, "geometria_invalida": 0,
               "reparadas": 0, "urbanas": 0, "rurales": 0}
    seen = set()
    for feature in _features(filename):
        props = feature.get("properties") or {}
        kind = props.get("tipo_padron_catastral")
        if props.get("codigo_departamento") != "P" or kind not in ("rural", "urbano_suburbano"):
            raise ValueError("La colección contiene un departamento o ámbito inesperado.")
        locality = "R" if kind == "rural" else normalize_id(props.get("codigo_localidad"))
        if kind == "urbano_suburbano" and locality == "R":
            raise ValueError("La localidad R está reservada para padrones rurales.")
        number = normalize_id(props.get("padron"))
        key = ("P", locality, number)
        if key in seen:
            raise ValueError(f"Identidad catastral duplicada: {':'.join(key)}")
        seen.add(key)
        if feature.get("id") != ":".join(key) or props.get("id_catastral") != ":".join(key):
            raise ValueError(f"Identidad de fuente inconsistente: {':'.join(key)}")
        geometry = feature.get("geometry")
        if not geometry:
            summary["sin_geometria"] += 1
            continue
        if key in existing_keys:
            summary["existentes"] += 1
            continue
        try:
            original_geom = shape(geometry)
            geom = validate_wgs84(geometry)
            area = reproject(geom).area
            if area <= 0:
                raise ValueError("Superficie nula")
        except (ValueError, KeyError, TypeError):
            summary["geometria_invalida"] += 1
            continue
        loc_key = ("P", locality)
        if loc_key not in localities:
            localities[loc_key] = CadastralLocality(
                coddepto="P", codloccat=locality,
                name="Rural (sin localidad catastral)" if kind == "rural" else props.get("localidad") or locality,
            )
            db.session.add(localities[loc_key])
            db.session.flush()
        parcel = Parcel(
            id=uid(), coddepto="P", codloccat=locality, padron=number,
            locality_id=localities[loc_key].id, geom=from_shape(geom, srid=4326),
            m2_parcela=area, source_version_id=version.id,
        )
        db.session.add(parcel)
        repaired = not original_geom.is_valid
        db.session.add(ParcelGeometryVersion(
            parcel_id=parcel.id, dataset_version_id=version.id,
            source_feature_id=feature["id"], original=feature,
            geom=from_shape(geom, srid=4326), repaired=repaired,
        ))
        existing_keys.add(key)
        summary["importadas"] += 1
        summary["reparadas"] += int(repaired)
        summary["rurales" if kind == "rural" else "urbanas"] += 1
        if summary["importadas"] % 250 == 0:
            db.session.flush()
    if not seen:
        raise ValueError("No se importará una colección vacía.")
    version.count = summary["importadas"]
    version.metadata_json = {"archivo": filename.name, "sha256": digest, "import_summary": summary,
                             "namespace_rural": "R", "no_reemplaza_padrones_existentes": True}
    db.session.commit()
    return {"id": version.id, "idempotent": False, **summary}


def import_geojson_parcels(filename):
    """Ejecuta la importación como una operación transaccional independiente."""
    try:
        return _import_geojson_parcels(filename)
    except Exception:
        db.session.rollback()
        raise
