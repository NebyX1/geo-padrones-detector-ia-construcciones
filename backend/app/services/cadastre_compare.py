"""Selection and interpretation of the public cadastral reference dataset."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from flask import abort, current_app
from sqlalchemy import func, literal, select, tuple_

from ..extensions import db
from ..models import Parcel


def dataset_path():
    return Path(current_app.config.get("CATASTRE_GEOJSON") or os.getenv("CATASTRE_GEOJSON") or
                Path(__file__).resolve().parents[3] / "data/catastro/lavalleja_procesado/padrones_lavalleja.geojson")


def _features(path):
    """Stream the generated collection without holding all geometries in RAM."""
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as stream:
        buffer = ""
        while True:
            more = stream.read(65536)
            if not more:
                raise ValueError("No se encontró la colección de entidades")
            buffer += more
            match = re.search(r'"features"\s*:\s*\[', buffer)
            if match:
                buffer = buffer[match.end():]
                break
            if len(buffer) > 1024 * 1024:
                raise ValueError("No se encontró la colección de entidades")
        eof = False
        while True:
            buffer = buffer.lstrip(" \t\r\n,")
            if not buffer and not eof:
                more = stream.read(65536)
                eof = not more
                buffer += more
                continue
            if buffer.startswith("]"):
                tail = buffer[1:] + stream.read()
                if tail.strip() != "}":
                    raise ValueError("GeoJSON catastral incompleto o con contenido adicional")
                return
            try:
                feature, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if eof:
                    raise ValueError("GeoJSON catastral incompleto")
                more = stream.read(65536)
                eof = not more
                buffer += more
                if len(buffer) > 32 * 1024 * 1024:
                    raise ValueError("Entidad catastral demasiado grande")
                continue
            yield feature
            buffer = buffer[end:]


@lru_cache(maxsize=1)
def _read_dataset(filename, mtime, size):
    path = Path(filename)
    initial = path.stat()
    if initial.st_mtime_ns != mtime or initial.st_size != size:
        raise ValueError("El archivo catastral cambió durante la lectura")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    records = {}
    for feature in _features(path):
        p = feature["properties"]
        category = p.get("categoria_suelo") or "sin_clase"
        if category not in {"urbano", "suburbano", "rural", "sin_clase"}:
            category = "sin_clase"
        declared = p.get("tiene_construccion_segun_catastro")
        if declared is not None and type(declared) is not bool:
            raise ValueError("Estado declarado inválido en archivo catastral")
        urban = p["tipo_padron_catastral"] == "urbano_suburbano"
        key = (str(p["codigo_localidad"]) if urban else "R", str(p["padron"]))
        if key in records:
            raise ValueError("Clave catastral duplicada")
        records[key] = dict(
            key=key, id_catastral=p["id_catastral"], categoria_suelo=category,
            codigo_localidad=p.get("codigo_localidad"), localidad=p.get("localidad"),
            padron=str(p["padron"]), declared_building=declared,
            has_geometry=bool(feature.get("geometry")),
            has_summary=bool(p.get("tiene_registro_alfanumerico")),
            orphan_lines=bool(p.get("lineas_sin_resumen_urbano")),
        )
    final = path.stat()
    if (initial.st_mtime_ns, initial.st_size, initial.st_ino) != (final.st_mtime_ns, final.st_size, final.st_ino):
        raise ValueError("El archivo catastral cambió durante la lectura")
    return digest, records


def dataset():
    path = dataset_path()
    try:
        stat = path.stat()
        return _read_dataset(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, KeyError, TypeError):
        abort(503, "La referencia catastral no está disponible o es inválida; revise el archivo y vuelva a intentar.")


def selection_filters(data):
    if not isinstance(data, dict):
        abort(422, "Se esperaba un objeto con filtros.")
    filters = {key: data.get(key) or "todos" for key in ("category", "locality", "state")}
    if filters["category"] not in {"todos", "urbano", "suburbano", "rural", "sin_clase"}:
        abort(422, "Categoría de suelo inválida.")
    if filters["state"] not in {"todos", "si", "no", "desconocido"}:
        abort(422, "Estado de construcción inválido.")
    if not isinstance(filters["locality"], str) or len(filters["locality"]) > 40:
        abort(422, "Localidad inválida.")
    for key in ("padron_desde", "padron_hasta"):
        raw = data.get(key)
        if raw is None or raw == "":
            filters[key] = None
        elif isinstance(raw, bool) or not re.fullmatch(r"[0-9]{1,9}", str(raw)):
            abort(422, "El rango de padrones debe contener números enteros válidos.")
        else:
            filters[key] = int(raw)
    if filters["padron_desde"] is not None and filters["padron_hasta"] is not None and filters["padron_desde"] > filters["padron_hasta"]:
        abort(422, "El padrón inicial no puede ser mayor que el final.")
    return filters


def select_records(records, filters):
    result = []
    for item in records.values():
        if filters["category"] != "todos" and item["categoria_suelo"] != filters["category"]:
            continue
        loc = item["codigo_localidad"] or "sin_localidad"
        if filters["locality"] != "todos" and loc != filters["locality"]:
            continue
        state = "desconocido" if item["declared_building"] is None else "si" if item["declared_building"] else "no"
        if filters["state"] != "todos" and state != filters["state"]:
            continue
        number = int(item["padron"])
        if filters.get("padron_desde") is not None and number < filters["padron_desde"]:
            continue
        if filters.get("padron_hasta") is not None and number > filters["padron_hasta"]:
            continue
        result.append(item)
    return result


def options(records, category):
    filters = selection_filters({"category": category})
    categories = Counter(r["categoria_suelo"] for r in records.values())
    scoped = select_records(records, filters)
    localities = Counter(r["codigo_localidad"] or "sin_localidad" for r in scoped)
    locality_names = {}
    for item in scoped:
        code = item["codigo_localidad"] or "sin_localidad"
        name = item["localidad"] or "Sin localidad"
        if code not in locality_names or len(name) > len(locality_names[code]):
            locality_names[code] = name
    states = Counter("desconocido" if r["declared_building"] is None else "si" if r["declared_building"] else "no" for r in scoped)
    names = {"urbano": "Urbano", "suburbano": "Suburbano", "rural": "Rural", "sin_clase": "Sin categoría única"}
    state_names = {"si": "Con construcción declarada", "no": "Sin construcción declarada", "desconocido": "No definido"}
    return dict(
        categories=[dict(value=k, label=names[k], count=categories[k]) for k in names],
        localities=[dict(value=code, label=locality_names[code], count=count) for code, count in sorted(localities.items(), key=lambda x: locality_names[x[0]])],
        states=[dict(value=k, label=state_names[k], count=states[k]) for k in state_names],
    )


def parcel_rows(records, scene):
    """Resolve keys without confusing rural and urban or transferring geometry to Python."""
    keys = list(records)
    crop = func.ST_Area(func.ST_Expand(func.ST_Envelope(func.ST_Transform(Parcel.geom, 5382)), 8))
    bounds = scene.metadata_json.get("bounds_wgs84") if scene else None
    if scene and not bounds:
        abort(409, "La imagen seleccionada no tiene cobertura geográfica registrada.")
    inside = func.ST_Intersects(Parcel.geom, func.ST_MakeEnvelope(*bounds, 4326)) if bounds else literal(True)
    result = {}
    for offset in range(0, len(keys), 2000):
        query = select(Parcel.id, Parcel.codloccat, Parcel.padron, Parcel.source_version_id,
                       Parcel.m2_parcela, crop.label("crop_area"), inside.label("inside")) .where(
            Parcel.active.is_(True), Parcel.coddepto == "P",
            tuple_(Parcel.codloccat, Parcel.padron).in_(keys[offset:offset + 2000]),
        )
        for row in db.session.execute(query):
            result[(row.codloccat, row.padron)] = row
    return result


def reason(row):
    if row.crop_area > current_app.config["MAX_ANALYSIS_AREA"] or row.crop_area / 0.2**2 > current_app.config["MAX_RASTER_PIXELS"]:
        return "La parcela supera el área o tamaño de recorte permitido para una inferencia."
    if not row.inside:
        return "Sin cobertura de imagen registrada para esta parcela."
    return None


def outcome(declared, result):
    if result is None:
        return "pendiente"
    if result.state not in {"CON_CONSTRUCCION_VISIBLE", "SIN_CONSTRUCCION_VISIBLE"}:
        return "indeterminado"
    if declared is None:
        return "sin_referencia"
    detected = result.state == "CON_CONSTRUCCION_VISIBLE"
    return "coincide" if declared == detected else "discrepancia"
