import argparse
import _bootstrap
from app import create_app
from app.services.imagery import register_minas, download_crop

parser = argparse.ArgumentParser(description="Recorte WCS en EPSG:5382, sin descargar el mosaico completo.")
parser.add_argument("--bounds", nargs=4, type=float, required=True)
parser.add_argument("--output", default="data/raw/minas-sector.tif")
args = parser.parse_args()
with create_app().app_context():
    raw, asset = download_crop(register_minas(), args.bounds)
    from pathlib import Path

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(asset.metadata_json)
