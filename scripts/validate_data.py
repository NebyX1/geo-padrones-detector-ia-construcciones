import argparse
import json
from collections import Counter
from pathlib import Path
import _bootstrap
from shapely.geometry import shape
from app.services.geospatial import validate_wgs84

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--output", default="artifacts/data-validation.json")
args = parser.parse_args()
counts = Counter()
identities = Counter()
localities = Counter()
issues = []
for index, line in enumerate(Path(args.file).open(encoding="utf-8"), start=1):
    feature = json.loads(line)
    props = feature["properties"]
    counts["features"] += 1
    try:
        original = shape(feature["geometry"])
        geom = validate_wgs84(feature["geometry"])
        if not original.is_valid:
            counts["repaired"] += 1
        key = tuple(str(props.get(k, "")) for k in ["coddepto", "codloccat", "padron"])
        if any(not v or v == "None" for v in key):
            raise ValueError("Identidad nula")
        identities[key] += 1
        localities[props.get("nomloccat")] += 1
    except (ValueError, KeyError) as exc:
        issues.append({"line": index, "feature": feature.get("id"), "error": str(exc)})
report = {
    "counts": dict(counts),
    "identities": len(identities),
    "extra_parts": sum(n - 1 for n in identities.values()),
    "localities": dict(localities),
    "issues": issues,
}
target = Path(args.output)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
