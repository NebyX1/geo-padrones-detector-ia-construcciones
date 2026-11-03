"""Comprueba que la salida conserve las claves y evidencias de los tres ZIP.

Uso: .venv/Scripts/python.exe scripts/verificar_catastro_lavalleja.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.catastro_shape import iter_lavalleja_shapes
from scripts.catastro_tabular import cargar_datos

DATA = ROOT / "data" / "catastro"


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    path = DATA / "lavalleja_procesado" / "padrones_lavalleja.geojson"
    with path.open(encoding="utf-8") as source:
        document = json.load(source)
    check(document.get("type") == "FeatureCollection", "La salida no es un FeatureCollection")
    cadastre = cargar_datos(DATA / "datosabiertosdnc2026-10.zip")
    sources = {
        "urbano_suburbano": ("paisurbano_shp.zip", cadastre.urbanos),
        "rural": ("paisrural_shp.zip", cadastre.rurales),
    }
    groups = {}
    for kind, (filename, _) in sources.items():
        rows = defaultdict(list)
        for source in iter_lavalleja_shapes(DATA / filename):
            props = source["properties"]
            key = (props["CODLOCCAT"], props["PADRON"]) if kind == "urbano_suburbano" else props["PADRON"]
            rows[key].append(source["record_number"])
        groups[kind] = rows

    expected = {}
    for kind, (_, table) in sources.items():
        line_only = cadastre.lineas_sin_padron_urbano if kind == "urbano_suburbano" else {}
        for key in set(groups[kind]) | set(table) | set(line_only):
            loc, number = key if kind == "urbano_suburbano" else ("R", key)
            expected[f"P:{loc}:{number}"] = (kind, key)

    features = document["features"]
    ids = [f.get("id") for f in features]
    check(len(ids) == len(set(ids)), "Hay IDs de padrón duplicados")
    check(set(ids) == set(expected), "Las claves del resultado no coinciden con la unión de las fuentes")
    counts = Counter()
    for feature in features:
        identity = feature["id"]
        props = feature["properties"]
        kind, key = expected[identity]
        official = sources[kind][1].get(key)
        geometry = feature["geometry"]
        check(props["id_catastral"] == identity, f"ID inconsistente: {identity}")
        check(props["tipo_padron_catastral"] == kind, f"Tipo incorrecto: {identity}")
        check(props["padron"] == (key[1] if isinstance(key, tuple) else key), f"Padrón incorrecto: {identity}")
        check(props["tiene_registro_alfanumerico"] == (official is not None), f"Cruce incorrecto: {identity}")
        check(props["tiene_geometria"] == (geometry is not None), f"Bandera de geometría incorrecta: {identity}")
        check(props["registros_geometricos_origen"] == groups[kind].get(key, []),
              f"Piezas perdidas o cambiadas: {identity}")
        check(props["cantidad_piezas_geometricas"] == len(groups[kind].get(key, [])),
              f"Conteo de piezas incorrecto: {identity}")
        state = props["tiene_construccion_segun_catastro"]
        check(state is None or type(state) is bool, f"Estado de construcción inválido: {identity}")
        land = props["detalle_categoria_suelo"]
        category = props["categoria_suelo"]
        check(category in (None, "urbano", "suburbano", "rural"), f"Categoría de suelo inválida: {identity}")
        check(category == land["categoria_principal"], f"Categoría de suelo inconsistente: {identity}")
        coverage = land["cobertura_porcentaje"]
        check(coverage is None or 0 <= coverage <= 100, f"Cobertura de suelo inválida: {identity}")
        for entry in land["categorias"]:
            check(entry["area_m2"] >= 0 and 0 <= entry["porcentaje_predio"] <= 100.001,
                  f"Detalle de categoría de suelo inválido: {identity}")
        counts["suelo_" + (category or "sin_clase_unica")] += 1
        if official is not None:
            check(state == official["tiene_construccion"], f"Construcción difiere de origen: {identity}")
            check(props["area_edificada_m2"] == official["area_edificada_m2"], f"Área difiere de origen: {identity}")
        if kind == "rural":
            check(state is None, f"Estado rural supuesto sin evidencia: {identity}")
        if geometry is not None:
            spatial = shape(geometry)
            check(not spatial.is_empty, f"Geometría vacía: {identity}")
            west, south, east, north = spatial.bounds
            check(-56 < west <= east < -53 and -35 < south <= north < -33,
                  f"Coordenadas fuera de Lavalleja: {identity}")
            check(spatial.is_valid or bool(props["problemas_geometria"]),
                  f"Geometría inválida no informada: {identity}")
            counts["geometria_invalida"] += not spatial.is_valid
        counts["total"] += 1
        counts["construccion_" + ("si" if state is True else "no" if state is False else "desconocida")] += 1
        counts["con_geometria" if geometry is not None else "sin_geometria"] += 1
        counts["con_registro_alfanumerico" if official is not None else "sin_registro_alfanumerico"] += 1
    print(json.dumps({"resultado": "correcto", "comprobaciones": dict(counts)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
