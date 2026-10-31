import hashlib
import json
import math
from pathlib import Path
import numpy as np
from flask import current_app
from defusedxml import ElementTree
from rasterio.io import MemoryFile
from rasterio.warp import reproject as raster_reproject, Resampling
from rasterio.transform import from_origin
from rasterio.enums import ColorInterp
from shapely.geometry import box
from sqlalchemy import select
from ..extensions import db
from ..models import ImageryScene, ImageryAsset
from .official import get_bytes, WCS_URL, WMS_URL, MINAS_COVERAGE
from .geospatial import reproject
from .storage import storage


def describe_minas():
    raw = get_bytes(
        WCS_URL, dict(service="WCS", version="2.0.1", request="DescribeCoverage", coverageId=MINAS_COVERAGE)
    )
    root = ElementTree.fromstring(raw)
    ns = {"gml": "http://www.opengis.net/gml/3.2"}
    envelope = root.find(".//gml:Envelope", ns)
    lower = [float(v) for v in envelope.find("gml:lowerCorner", ns).text.split()]
    upper = [float(v) for v in envelope.find("gml:upperCorner", ns).text.split()]
    if not envelope.attrib["srsName"].endswith("/5382"):
        raise ValueError("CRS de cobertura inesperado.")
    return dict(
        bounds=lower + upper,
        bounds_wgs84=list(reproject(box(*(lower + upper)), 5382, 4326).bounds),
        describe_coverage_sha256=hashlib.sha256(raw).hexdigest(),
        date_precision="month",
        capture_date_source="Catálogo IDE: vuelo Minas diciembre 2025",
        license_status="Licencia de DAG de Uruguay (odc-uy), ficha del vuelo comprobada 2026-10-31",
        license_source="https://catalogodatos.gub.uy/dataset/ide-vuelo-fotogrametrico-minas-diciembre-2025",
        analysis_resolution_m=0.2,
    )


def register_minas():
    existing = db.session.execute(
        select(ImageryScene).where(ImageryScene.coverage_id == MINAS_COVERAGE)
    ).scalar_one_or_none()
    if existing:
        existing.license = "Licencia de DAG de Uruguay (odc-uy) · IDE Uruguay · vuelo Minas diciembre 2025"
        existing.metadata_json = {
            **existing.metadata_json,
            "license_status": "odc-uy, ficha comprobada 2026-10-31",
            "license_source": "https://catalogodatos.gub.uy/dataset/ide-vuelo-fotogrametrico-minas-diciembre-2025",
        }
        db.session.commit()
        return existing
    scene = ImageryScene(
        name="Minas · Vuelo diciembre 2025",
        source=WCS_URL,
        coverage_id=MINAS_COVERAGE,
        captured_at="2025-12",
        resolution_m=0.05,
        srid=5382,
        license="Licencia de DAG de Uruguay (odc-uy) · IDE Uruguay · vuelo Minas diciembre 2025",
        metadata_json=describe_minas(),
    )
    db.session.add(scene)
    db.session.commit()
    return scene


def download_crop(scene, bounds, resolution=0.2):
    if scene.coverage_id != MINAS_COVERAGE or scene.srid != 5382:
        raise ValueError("Cobertura aún no habilitada para inferencia.")
    west, south, east, north = [float(v) for v in bounds]
    area = (east - west) * (north - south)
    if (
        not 0 < area <= current_app.config["MAX_ANALYSIS_AREA"]
        or area / resolution**2 > current_app.config["MAX_RASTER_PIXELS"]
    ):
        raise ValueError("El recorte supera el área o cantidad de píxeles permitida.")
    coverage = box(*scene.metadata_json["bounds"])
    if not coverage.intersects(box(*bounds)):
        raise ValueError("Sin cobertura de imagen para esta parcela.")
    requested = box(*bounds).intersection(coverage).bounds
    west, south, east, north = requested
    key = hashlib.sha256(
        json.dumps([scene.coverage_id, requested, resolution], sort_keys=True).encode()
    ).hexdigest()
    existing = db.session.execute(
        select(ImageryAsset).where(ImageryAsset.cache_key == key)
    ).scalar_one_or_none()
    if existing:
        return storage().get(existing.object_key), existing
    raw = get_bytes(
        WCS_URL,
        [
            ("service", "WCS"),
            ("version", "2.0.1"),
            ("request", "GetCoverage"),
            ("coverageId", scene.coverage_id),
            ("subset", f"E({west},{east})"),
            ("subset", f"N({south},{north})"),
            ("scaleFactor", str(scene.resolution_m / resolution)),
            ("format", "image/tiff"),
        ],
        max_bytes=80000000,
    )
    with MemoryFile(raw) as memory:
        with memory.open() as raster:
            if raster.crs is None or raster.crs.to_epsg() != scene.srid or raster.count < 3:
                raise ValueError("Raster sin CRS esperado o sin tres canales RGB.")
            if raster.width * raster.height > current_app.config["MAX_RASTER_PIXELS"]:
                raise ValueError("Raster supera el límite de píxeles.")
            metadata = dict(
                crs=raster.crs.to_string(),
                transform=list(raster.transform),
                width=raster.width,
                height=raster.height,
                resolution=list(raster.res),
                bounds=list(raster.bounds),
            )
    object_key = f"imagery/{scene.id}/{key}.tif"
    storage().put(object_key, raw, "image/tiff")
    asset = ImageryAsset(
        scene_id=scene.id,
        cache_key=key,
        object_key=object_key,
        sha256=hashlib.sha256(raw).hexdigest(),
        metadata_json=metadata,
    )
    db.session.add(asset)
    db.session.commit()
    return raw, asset


def read_rgb(raw, resolution=0.2):
    with MemoryFile(raw) as memory:
        with memory.open() as source:
            if source.width * source.height > current_app.config["MAX_RASTER_PIXELS"]:
                raise ValueError("Raster demasiado grande.")
            rgb = source.read([1, 2, 3]).astype(np.float32)
            if ColorInterp.alpha in source.colorinterp:
                valid = source.read(source.colorinterp.index(ColorInterp.alpha) + 1) > 0
            else:
                valid = (source.dataset_mask() > 0) & np.any(rgb != 0, axis=0)
            if not np.isclose(source.res[0], resolution, rtol=0.01) or not np.isclose(
                source.res[1], resolution, rtol=0.01
            ):
                width = math.ceil((source.bounds.right - source.bounds.left) / resolution)
                height = math.ceil((source.bounds.top - source.bounds.bottom) / resolution)
                target_transform = from_origin(source.bounds.left, source.bounds.top, resolution, resolution)
                target = np.zeros((3, height, width), dtype=np.float32)
                target_valid = np.zeros((height, width), dtype=np.uint8)
                for channel in range(3):
                    raster_reproject(
                        rgb[channel],
                        target[channel],
                        src_transform=source.transform,
                        src_crs=source.crs,
                        dst_transform=target_transform,
                        dst_crs=source.crs,
                        resampling=Resampling.bilinear,
                    )
                raster_reproject(
                    valid.astype(np.uint8),
                    target_valid,
                    src_transform=source.transform,
                    src_crs=source.crs,
                    dst_transform=target_transform,
                    dst_crs=source.crs,
                    resampling=Resampling.nearest,
                )
                return target, target_valid.astype(bool), target_transform, source.crs
            return rgb, valid, source.transform, source.crs


def render_tile(scene, z, x, y):
    if scene.coverage_id != MINAS_COVERAGE:
        raise ValueError("Fuente no habilitada.")
    # Stable official coverage key also reuses identical public tiles across isolated QA databases.
    return render_wms_tile(MINAS_COVERAGE, WMS_URL, "ortofotos:minas_lavalleja_mosaico_2025_geotiff", z, x, y)


def render_historical_tile(z, x, y):
    # Capabilities title establishes 2017–2018, irrespective of the misleading ORTOFOTOS_2019 alias.
    # Visualization only: neither the local image date nor its native resolution is inferred per parcel.
    # The geoservicios catalogue URL returns capabilities for every request; use its advertised service.
    return render_wms_tile("historical-2017-2018", WMS_URL, "ortofotos:ortofoto_urbana", z, x, y)


def render_wms_tile(cache_id, url, layer, z, x, y):
    if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise ValueError("Tesela inválida.")
    cache = Path(current_app.config["DATA_DIR"]) / "tiles" / cache_id / str(z) / str(x) / f"{y}.png"
    if cache.exists():
        return cache.read_bytes()
    span = 40075016.68557849 / 2**z
    west = -20037508.342789244 + x * span
    north = 20037508.342789244 - y * span
    raw = get_bytes(
        url,
        dict(
            service="WMS",
            version="1.1.1",
            request="GetMap",
            layers=layer,
            styles="",
            srs="EPSG:3857",
            bbox=f"{west},{north - span},{west + span},{north}",
            width=256,
            height=256,
            format="image/png",
            transparent="true",
        ),
        max_bytes=2000000,
        timeout=(5, 15),
        retries=1,
    )
    if not raw.startswith(b"\x89PNG"):
        raise ValueError("El WMS no devolvió una imagen PNG.")
    cache.parent.mkdir(parents=True, exist_ok=True)
    # Bounded cache; operational cleanup command handles old tiles.
    if sum(p.stat().st_size for p in cache.parents[4].rglob("*.png")) < min(
        current_app.config["MAX_STORAGE_BYTES"] // 10, 1000000000
    ):
        cache.write_bytes(raw)
    return raw
