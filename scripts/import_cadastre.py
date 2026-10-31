import argparse
import json
import _bootstrap
from app import create_app
from app.services.cadastre import import_file

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--land-use", action="store_true")
args = parser.parse_args()
with create_app().app_context():
    print(json.dumps(import_file(args.file, args.land_use), ensure_ascii=False, indent=2))
