import argparse
import hashlib
import json
from pathlib import Path
import rasterio
from rasterio.shutil import copy

parser = argparse.ArgumentParser(
    description="Valida un GeoTIFF y genera un COG sin perder georreferenciación."
)
parser.add_argument("input")
parser.add_argument("output")
args = parser.parse_args()
source, destination = Path(args.input), Path(args.output)
if destination.exists():
    raise SystemExit("La salida ya existe; use una ruta nueva para conservar versiones.")
with rasterio.open(source) as raster:
    if raster.crs is None or raster.count < 3:
        raise SystemExit("Se requiere una imagen georreferenciada con al menos tres canales.")
    metadata = dict(
        crs=raster.crs.to_string(),
        transform=list(raster.transform),
        resolution=list(raster.res),
        bounds=list(raster.bounds),
    )
destination.parent.mkdir(parents=True, exist_ok=True)
copy(source, destination, driver="COG", compress="DEFLATE", blocksize=512, overview_resampling="average")
metadata["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(json.dumps(metadata, indent=2))
