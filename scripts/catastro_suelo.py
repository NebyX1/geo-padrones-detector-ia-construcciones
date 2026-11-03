"""Cruce espacial informativo con la capa IDE de categorías de suelo.

La categoría territorial no es lo mismo que el ámbito catastral. Una parcela
puede intersectar varias categorías o quedar parcialmente fuera de la capa.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, prepare
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree


def _ambito(categoria: str) -> str | None:
    # «Rural ... potencialmente transformable a suburbano» sigue siendo rural.
    nombre = categoria.strip().casefold()
    for valor in ("urbano", "suburbano", "rural"):
        if nombre.startswith(valor):
            return valor
    return None


def _dividir_en_malla(geom, lado=10000):
    """Parte geometrías extensas en cuadrados métricos sin perder superficie."""
    xmin, ymin, xmax, ymax = geom.bounds
    if xmax - xmin <= lado and ymax - ymin <= lado:
        yield geom
        return
    prepare(geom)
    for x in range(math.floor(xmin / lado), math.ceil(xmax / lado)):
        for y in range(math.floor(ymin / lado), math.ceil(ymax / lado)):
            cell = box(x * lado, y * lado, (x + 1) * lado, (y + 1) * lado)
            if not geom.intersects(cell):
                continue
            part = geom.intersection(cell)
            if not part.is_empty and part.area > 0:
                yield part


class LandUseIndex:
    """Índice espacial reutilizable para geometrías GeoJSON en WGS 84."""

    def __init__(self, geometries, names, source):
        self.geometries = geometries
        self.names = names
        self.source = source
        self.tree = STRtree(geometries)
        for geom in geometries:
            prepare(geom)
        self.project = Transformer.from_crs(4326, 32721, always_xy=True).transform

    @classmethod
    def from_path(cls, path: str | Path) -> LandUseIndex:
        path = Path(path)
        project = Transformer.from_crs(4326, 32721, always_xy=True).transform
        geometries, names = [], []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                feature = json.loads(line)
                name = feature.get("properties", {}).get("categoria")
                if not name or not feature.get("geometry"):
                    continue
                geom = shape(feature["geometry"])
                if not geom.is_valid:
                    geom = make_valid(geom)
                geom = transform(project, geom)
                if not geom.is_empty:
                    for part in _dividir_en_malla(geom):
                        geometries.append(part)
                        names.append(name)
        if not geometries:
            raise ValueError("La capa de categorías de suelo no contiene geometrías utilizables")
        source = {
            "archivo": str(path).replace("\\", "/"),
            "capa": "ideuy:uyla_dir_categsuelo",
            "url": "https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs",
            "crs_calculo": "EPSG:32721",
            "metodo": "intersección espacial por área; no acredita categoría jurídica vigente",
        }
        manifest_path = path.with_name("land-use.manifest.json")
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source["sha256"] = manifest.get("sha256")
            source["adquirida_el"] = manifest.get("acquired_at")
            source["fecha_datos"] = manifest.get("capture_date")
        return cls(geometries, names, source)

    def classify_geojson(self, geometry: dict | None) -> dict:
        """Clasifica sin extrapolar fuera de los polígonos territoriales.

        Las áreas de categorías distintas pueden solaparse; la cobertura total
        usa la unión de las intersecciones y nunca su suma. Una categoría
        principal requiere que una sola clase cubra al menos el 99 % del predio.
        """
        result = {
            "estado": "sin_geometria",
            "categoria_principal": None,
            "categorias_mixtas": None,
            "cobertura_incompleta": None,
            "cobertura_porcentaje": None,
            "categorias": [],
            "fuente": self.source,
        }
        if not geometry:
            return result
        geom = shape(geometry)
        repaired = not geom.is_valid
        if repaired:
            geom = make_valid(geom)
        geom = transform(self.project, geom)
        area = geom.area
        if geom.is_empty or area <= 0:
            result["estado"] = "sin_area"
            return result
        grouped = defaultdict(list)
        all_parts = []
        for index in self.tree.query(geom):
            category_geom = self.geometries[index]
            if category_geom.covers(geom):
                part = geom
            elif category_geom.intersects(geom):
                part = geom.intersection(category_geom)
            else:
                continue
            if not part.is_empty and part.area > 0:
                grouped[self.names[index]].append(part)
                all_parts.append(part)
        if any(part is geom for part in all_parts):
            coverage = 1.0
        else:
            coverage = min(1.0, unary_union(all_parts).area / area) if all_parts else 0.0
        classes = defaultdict(list)
        entries = []
        for name, parts in grouped.items():
            merged = geom if any(part is geom for part in parts) else unary_union(parts)
            clase = _ambito(name)
            entries.append({
                "nombre": name,
                "clase": clase,
                "area_m2": round(merged.area, 2),
                "porcentaje_predio": round(100 * merged.area / area, 4),
            })
            if clase:
                classes[clase].append(merged)
        proportions = {
            name: (1.0 if any(part is geom for part in parts) else min(1.0, unary_union(parts).area / area))
            for name, parts in classes.items()
        }
        dominant = [name for name, fraction in proportions.items() if fraction >= 0.99]
        result.update({
            "estado": "con_cobertura" if all_parts else "sin_cobertura",
            "categoria_principal": dominant[0] if len(dominant) == 1 else None,
            "categorias_mixtas": len(proportions) > 1,
            "cobertura_incompleta": coverage < 0.99,
            "cobertura_porcentaje": round(100 * coverage, 4),
            "categorias": sorted(entries, key=lambda item: (-item["area_m2"], item["nombre"])),
            "geometria_reparada": repaired,
        })
        return result
