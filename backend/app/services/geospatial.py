from functools import lru_cache
from shapely import make_valid, union_all
from shapely.geometry import shape, MultiPolygon, Polygon, GeometryCollection
from shapely.ops import transform
from pyproj import Transformer

METRIC_SRID = 5382


def parcel_confidence(probabilities, binary, valid, parcel, affine):
    """Mean building probability of valid detected pixels inside this parcel only."""
    from rasterio.features import geometry_mask
    from shapely.geometry import mapping

    inside = geometry_mask([mapping(parcel)], out_shape=valid.shape, transform=affine, invert=True)
    selected = probabilities[(binary == 1) & valid & inside]
    return float(selected.mean()) if selected.size else None


@lru_cache(maxsize=16)
def transformer(source, target):
    return Transformer.from_crs(source, target, always_xy=True)


def reproject(geom, source=4326, target=METRIC_SRID):
    return transform(transformer(source, target).transform, geom)


def multipolygon(geom):
    geom = make_valid(geom)
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, GeometryCollection):
        polygons = []
        for part in geom.geoms:
            if isinstance(part, Polygon):
                polygons.append(part)
            elif isinstance(part, MultiPolygon):
                polygons.extend(part.geoms)
        return MultiPolygon(polygons)
    raise ValueError("Se esperaba una geometría poligonal no vacía.")


def validate_wgs84(geojson):
    geom = multipolygon(shape(geojson))
    if geom.is_empty or not geom.is_valid:
        raise ValueError("Geometría vacía o inválida.")
    west, south, east, north = geom.bounds
    # Uruguay and a small margin; catches accidental axis swaps and wrong CRS.
    if not (-59.5 <= west <= east <= -52.5 and -36 <= south <= north <= -29.5):
        raise ValueError("Coordenadas fuera de Uruguay; verifique CRS y orden lon/lat.")
    return geom


def measure(
    parcel_metric, buildings_metric, valid_imagery_metric, min_area=8, min_coverage=0.95, min_occupancy=0.01
):
    """All inputs MUST be in the same metric CRS. Union before measuring intersections."""
    parcel = multipolygon(parcel_metric)
    if parcel.area <= 0:
        raise ValueError("La parcela tiene superficie nula.")
    coverage_geom = make_valid(valid_imagery_metric).intersection(parcel)
    coverage = min(1.0, coverage_geom.area / parcel.area)
    buildings = (
        union_all([make_valid(g) for g in buildings_metric]) if buildings_metric else GeometryCollection()
    )
    clipped = buildings.intersection(parcel).intersection(coverage_geom)
    pieces = list(multipolygon(clipped).geoms) if not clipped.is_empty else []
    # Artifact filtering is separate from the minimum parcel-level detection area.
    area = sum(p.area for p in pieces)
    occupancy = area / parcel.area
    if coverage < min_coverage:
        state = "INDETERMINADO"
    elif area > 0 and area >= min_area and occupancy >= min_occupancy:
        state = "CON_CONSTRUCCION_VISIBLE"
    elif area > 0:
        state = "INDETERMINADO"
    else:
        state = "SIN_CONSTRUCCION_VISIBLE"
    return dict(
        state=state,
        m2_huella_detectada=area if coverage else None,
        occupancy=occupancy if coverage else None,
        building_count=len(pieces) if coverage else None,
        coverage=coverage,
        footprints=pieces,
    )
