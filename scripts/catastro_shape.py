"""Read Lavalleja polygon records directly from the DNC zipped shapefiles.

No intermediate uncompressed shapefiles are written. Multiple records with the
same cadastral key are deliberately kept: callers must not overwrite them.
"""

from __future__ import annotations

import math
import struct
import zipfile
from collections.abc import Iterator
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity


def _read_exact(stream, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(f"Archivo truncado: se esperaban {size} bytes y llegaron {len(data)}")
    return data


def _dbf_header(stream) -> tuple[int, int, list[tuple[str, str, int, int]]]:
    header = _read_exact(stream, 32)
    count = struct.unpack_from("<I", header, 4)[0]
    header_length, row_length = struct.unpack_from("<HH", header, 8)
    descriptors = _read_exact(stream, header_length - 32)
    fields = []
    position = 1
    for index in range(0, len(descriptors), 32):
        item = descriptors[index : index + 32]
        if item[0] == 13:
            break
        if len(item) != 32:
            raise ValueError("Descriptor DBF incompleto")
        name = item[:11].split(b"\0")[0].decode("ascii")
        length = item[16]
        fields.append((name, chr(item[11]), position, length))
        position += length
    if position != row_length:
        raise ValueError("Longitud DBF inconsistente")
    return count, row_length, fields


def _dbf_values(row: bytes, fields: list[tuple[str, str, int, int]]) -> dict:
    result = {}
    for name, kind, position, length in fields:
        value = row[position : position + length].decode("utf-8").strip()
        if not value:
            result[name] = None
        elif kind in ("N", "F"):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"Valor DBF no finito: {name}={value}")
            result[name] = int(number) if number.is_integer() else number
        else:
            result[name] = value
    return result


def _polygon_geometry(record: bytes, transform: Transformer) -> tuple[dict | None, str | None]:
    shape_type = struct.unpack_from("<i", record, 0)[0]
    if shape_type == 0:
        return None, "Geometría nula en el archivo de origen"
    if shape_type != 5:
        raise ValueError(f"Tipo de geometría inesperado: {shape_type}")
    parts_count, points_count = struct.unpack_from("<ii", record, 36)
    if parts_count <= 0 or points_count < 4:
        raise ValueError("Polígono sin suficientes partes o puntos")
    points_offset = 44 + 4 * parts_count
    if len(record) < points_offset + 16 * points_count:
        raise ValueError("Geometría SHP truncada")
    starts = list(struct.unpack_from(f"<{parts_count}i", record, 44)) + [points_count]
    if starts[0] != 0 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError("Índices de anillos SHP inválidos")

    rings = []
    for start, end in zip(starts, starts[1:]):
        points = [struct.unpack_from("<2d", record, points_offset + 16 * index) for index in range(start, end)]
        if points[0] != points[-1]:
            points.append(points[0])
        if len(points) < 4:
            raise ValueError("Anillo SHP con menos de cuatro puntos")
        xs, ys = transform.transform(*zip(*points))
        coordinates = list(zip(xs, ys))
        rings.append((coordinates, Polygon(coordinates)))

    # A ring's immediate parent is the smallest larger ring containing it.
    # This preserves disconnected pieces, holes, and islands inside holes even
    # when the source winding order is inconsistent.
    parents: list[int | None] = []
    for index, (_, candidate) in enumerate(rings):
        point = candidate.representative_point()
        containers = [
            j for j, (_, other) in enumerate(rings)
            if j != index and other.area > candidate.area and other.covers(point)
        ]
        parents.append(min(containers, key=lambda j: rings[j][1].area) if containers else None)

    depths = []
    for index in range(len(rings)):
        depth, parent = 0, parents[index]
        while parent is not None:
            depth += 1
            parent = parents[parent]
        depths.append(depth)

    polygons = []
    for index, (shell, _) in enumerate(rings):
        if depths[index] % 2:
            continue
        holes = [rings[j][0] for j, parent in enumerate(parents) if parent == index and depths[j] % 2]
        polygons.append(orient(Polygon(shell, holes), sign=1.0))
    geometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    return mapping(geometry), None if geometry.is_valid else explain_validity(geometry)


def iter_lavalleja_shapes(path: str | Path) -> Iterator[dict]:
    """Yield source rows with WGS84 geometry and validity diagnostics.

    Keys: ``record_number`` (one-based SHP record), ``properties`` (all DBF
    fields), ``geometry`` (GeoJSON geometry or None), ``geometry_problem``
    (None if valid, otherwise Shapely's reason). Invalid geometry is reported,
    never silently repaired. DBF deleted rows are excluded.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()

        def find(extension: str) -> str:
            return next(name for name in names if name.lower().endswith(extension))

        source_crs = CRS.from_wkt(archive.read(find(".prj")).decode("utf-8"))
        transform = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
        with archive.open(find(".dbf")) as dbf, archive.open(find(".shp")) as shp:
            count, row_length, fields = _dbf_header(dbf)
            shape_header = _read_exact(shp, 100)
            if struct.unpack_from(">i", shape_header, 0)[0] != 9994:
                raise ValueError("Cabecera SHP inválida")
            for index in range(count):
                row = _read_exact(dbf, row_length)
                record_header = _read_exact(shp, 8)
                number, words = struct.unpack(">ii", record_header)
                if number != index + 1 or words < 2:
                    raise ValueError(f"Registro SHP inconsistente: {number}")
                contents = _read_exact(shp, words * 2)
                if row[:1] == b"*":
                    continue
                values = _dbf_values(row, fields)
                if values.get("NOMDEPTO") != "LAVALLEJA":
                    continue
                geometry, problem = _polygon_geometry(contents, transform)
                yield {
                    "record_number": number,
                    "properties": values,
                    "geometry": geometry,
                    "geometry_problem": problem,
                }
