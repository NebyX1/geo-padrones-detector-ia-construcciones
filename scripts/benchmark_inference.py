import argparse
import json
import time
from pathlib import Path
import _bootstrap
import numpy as np
from PIL import Image
from shapely.geometry import mapping
from rasterio.io import MemoryFile
from app import create_app
from app.services.imagery import read_rgb
from app.services.inference import load_model, segment, vectorize
from app.services.geospatial import reproject

parser = argparse.ArgumentParser(description="Inferencia FLAIR verdadera; no genera resultados simulados.")
parser.add_argument("--raster", default="data/raw/minas-sector.tif")
parser.add_argument("--manifest", default="data/models/manifest.json")
parser.add_argument("--output", default="artifacts/benchmark")
args = parser.parse_args()
destination = Path(args.output)
destination.mkdir(parents=True, exist_ok=True)
manifest_path = Path(args.manifest)
manifest = json.loads(manifest_path.read_text())
with create_app().app_context():
    rgb, valid, affine, crs = read_rgb(Path(args.raster).read_bytes())
    started = time.perf_counter()
    model = load_model(str(manifest_path.parent / manifest["filename"]), manifest["sha256"])
    load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    probabilities = segment(rgb, model)
    buildings, coverage, binary = vectorize(probabilities, valid, affine)
    inference_seconds = time.perf_counter() - started
    features = [
        dict(
            type="Feature",
            properties={"source": "FLAIR real inference", "sha256": manifest["sha256"]},
            geometry=mapping(reproject(g, crs.to_epsg(), 4326)),
        )
        for g in buildings
    ]
    (destination / "buildings.geojson").write_text(
        json.dumps(dict(type="FeatureCollection", features=features)), encoding="utf-8"
    )
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=binary.shape[1],
            height=binary.shape[0],
            count=1,
            dtype="uint8",
            transform=affine,
            crs=crs,
            compress="deflate",
            nodata=255,
        ) as output:
            output.write(np.where(valid, binary, 255).astype("uint8"), 1)
        (destination / "mask.tif").write_bytes(memory.read())
    original = np.moveaxis(np.clip(rgb, 0, 255).astype("uint8"), 0, -1)
    overlay = original.copy()
    overlay[binary == 1] = (original[binary == 1] * 0.45 + np.array([30, 225, 165]) * 0.55).astype("uint8")
    Image.fromarray(original).save(destination / "ortho.png")
    Image.fromarray(overlay).save(destination / "overlay.png")
    report = dict(
        real_inference=True,
        model_revision=manifest["revision"],
        checkpoint_sha256=manifest["sha256"],
        output_channels=19,
        building_channel=0,
        raster=str(Path(args.raster)),
        crs=str(crs),
        pixels=list(binary.shape),
        resolution_m=abs(affine.a),
        model_load_seconds=load_seconds,
        inference_seconds=inference_seconds,
        detected_polygons=len(buildings),
        footprint_area_m2=sum(g.area for g in buildings),
        valid_image_area_m2=coverage.area,
        validated_local_accuracy=None,
    )
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
