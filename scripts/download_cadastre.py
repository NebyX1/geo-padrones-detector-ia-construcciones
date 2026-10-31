import argparse
import _bootstrap
from app.services.official import download_wfs, PARCEL_LAYER, LAND_USE_LAYER

parser = argparse.ArgumentParser(description="Descarga WFS oficial paginada, con procedencia y hash.")
parser.add_argument("--output", default="data/raw/lavalleja.ndjson")
parser.add_argument("--land-use", action="store_true")
parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
parser.add_argument("--max-features", type=int)
args = parser.parse_args()
print(
    download_wfs(
        args.output,
        LAND_USE_LAYER if args.land_use else PARCEL_LAYER,
        args.bbox,
        max_features=args.max_features,
    )
)
