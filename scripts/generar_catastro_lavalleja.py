"""Genera un GeoJSON de padrones de Lavalleja a partir de los ZIP de DNC.

Uso desde la raíz: .venv/Scripts/python.exe scripts/generar_catastro_lavalleja.py
"""
from __future__ import annotations

import hashlib
import gzip
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.catastro_shape import iter_lavalleja_shapes
from scripts.catastro_suelo import LandUseIndex
from scripts.catastro_tabular import cargar_datos

INPUT = ROOT / "data" / "catastro"
OUTPUT = INPUT / "lavalleja_procesado"
LAND_USE = ROOT / "data" / "raw" / "land-use.ndjson"
SOURCES = {
    "datos_alfanumericos": INPUT / "datosabiertosdnc2026-10.zip",
    "geometria_urbana": INPUT / "paisurbano_shp.zip",
    "geometria_rural": INPUT / "paisrural_shp.zip",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def collect_shapes(path, urban):
    groups = defaultdict(list)
    for record in iter_lavalleja_shapes(path):
        props = record["properties"]
        if props["CODDEPTO"] != "P":
            raise ValueError(f"Código de departamento inesperado: {props['CODDEPTO']}")
        key = (props["CODLOCCAT"], int(props["PADRON"])) if urban else int(props["PADRON"])
        groups[key].append(record)
    return groups


def merge_geometry(records):
    geometries = [shape(row["geometry"]) for row in records if row["geometry"] is not None]
    problems = [f"Registro {r['record_number']}: {r['geometry_problem']}" for r in records if r["geometry_problem"]]
    if not geometries:
        return None, problems
    if len(geometries) == 1:
        return mapping(geometries[0]), problems
    if problems:
        # Retain the original components instead of silently repairing them.
        return mapping(GeometryCollection(geometries)), problems
    try:
        combined = unary_union(geometries)
        if not combined.is_valid:
            raise ValueError("unión inválida")
        return mapping(combined), problems
    except Exception as exc:
        problems.append(f"No se pudieron unir las piezas: {exc}")
        return mapping(GeometryCollection(geometries)), problems


def main():
    data = cargar_datos(SOURCES["datos_alfanumericos"])
    land_use = LandUseIndex.from_path(LAND_USE)
    groups = {
        "urbano_suburbano": collect_shapes(SOURCES["geometria_urbana"], True),
        "rural": collect_shapes(SOURCES["geometria_rural"], False),
    }
    tables = {"urbano_suburbano": data.urbanos, "rural": data.rurales}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    sources = {k: {"archivo": v.name, "sha256": digest(v)} for k, v in SOURCES.items()}
    sources["categoria_de_suelo"] = {**land_use.source, "sha256": digest(LAND_USE)}
    metadata = {
        "titulo": "Padrones de Lavalleja y construcción informada por Catastro",
        "fecha_datos_alfanumericos": "2026-10",
        "fecha_geometrias": None,
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "coordenadas": "WGS 84 / longitud, latitud (GeoJSON RFC 7946)",
        "fuentes": sources,
    }
    out = OUTPUT / "padrones_lavalleja.geojson"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write('{"type":"FeatureCollection","metadata":')
        json.dump(metadata, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        f.write(',"features":[\n')
        first = True
        for kind in ("urbano_suburbano", "rural"):
            shapes = groups[kind]
            table = tables[kind]
            line_only = data.lineas_sin_padron_urbano if kind == "urbano_suburbano" else {}
            keys = sorted(set(shapes) | set(table) | set(line_only))
            for key in keys:
                urban = kind == "urbano_suburbano"
                records = shapes.get(key, [])
                official = table.get(key)
                geometry, problems = merge_geometry(records)
                loc_code, number = key if urban else (None, key)
                shape_props = records[0]["properties"] if records else {}
                loc = (shape_props.get("NOMLOCCAT") or data.localidades.get(loc_code)) if urban else None
                orphan_lines = line_only.get(key)
                estado = official.get("tiene_construccion") if official else (
                    True if orphan_lines and orphan_lines["cantidad_lineas_area_positiva"] else None
                )
                land_class = land_use.classify_geojson(geometry)
                land_class.pop("fuente", None)
                identity = f"P:{loc_code}:{number}" if urban else f"P:R:{number}"
                properties = {
                    "id_catastral": identity,
                    "departamento": "LAVALLEJA",
                    "codigo_departamento": "P",
                    "padron": number,
                    "localidad": loc,
                    "codigo_localidad": loc_code,
                    "tipo_padron_catastral": kind,
                    "categoria_suelo": land_class["categoria_principal"],
                    "detalle_categoria_suelo": land_class,
                    "tiene_construccion_segun_catastro": estado,
                    "area_edificada_m2": official.get("area_edificada_m2") if official else None,
                    "datos_catastrales": official,
                    "lineas_sin_resumen_urbano": orphan_lines,
                    "tiene_geometria": geometry is not None,
                    "tiene_registro_alfanumerico": official is not None,
                    "cantidad_piezas_geometricas": len(records),
                    "registros_geometricos_origen": [r["record_number"] for r in records],
                    "problemas_geometria": problems,
                }
                if not first:
                    f.write(',\n')
                first = False
                json.dump({"type": "Feature", "id": identity, "geometry": geometry, "properties": properties},
                          f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                counts["total"] += 1
                counts[kind] += 1
                counts["con_geometria" if geometry is not None else "sin_geometria"] += 1
                counts["con_registro_alfanumerico" if official else "sin_registro_alfanumerico"] += 1
                counts["construccion_" + ("si" if estado is True else "no" if estado is False else "desconocida")] += 1
                counts["suelo_" + (land_class["categoria_principal"] or "sin_clase_unica")] += 1
                if land_class["categorias_mixtas"]:
                    counts["suelo_mixto"] += 1
                if land_class["cobertura_incompleta"]:
                    counts["suelo_cobertura_incompleta"] += 1
                if problems:
                    counts["geometria_con_problemas"] += 1
                if len(records) > 1:
                    counts["padrones_con_varias_piezas"] += 1
        f.write('\n]}\n')
    with out.open("rb") as src, gzip.open(str(out) + ".gz", "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    summary = {"metadata": metadata, "conteos": dict(counts),
               "claves_alfanumericas": {kind: len(table) for kind, table in tables.items()},
               "claves_geometricas": {kind: len(rows) for kind, rows in groups.items()},
               "piezas_geometricas": {kind: sum(map(len, rows.values())) for kind, rows in groups.items()}}
    (OUTPUT / "resumen_y_fuentes.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["conteos"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
