"""Inspect official WCS coverages without assuming dates or suitability for a locality."""

import json
from pathlib import Path
from datetime import datetime, timezone
import _bootstrap
from defusedxml import ElementTree
from app.services.official import get_bytes, WCS_URL

raw = get_bytes(WCS_URL, {"service": "WCS", "version": "2.0.1", "request": "GetCapabilities"})
root = ElementTree.fromstring(raw)
names = []
for item in root.iter():
    if item.tag.endswith("CoverageSummary"):
        info = {}
        for element in item.iter():
            if element.tag.endswith("CoverageId"):
                info["coverage_id"] = element.text
            elif element.tag.endswith("LowerCorner"):
                info["lower_corner"] = element.text
            elif element.tag.endswith("UpperCorner"):
                info["upper_corner"] = element.text
        names.append(info)
report = {
    "source": WCS_URL,
    "acquired_at": datetime.now(timezone.utc).isoformat(),
    "coverages": names,
    "notice": "Un nombre de cobertura no certifica fecha de captura, resolución o aptitud para IA. Se requiere DescribeCoverage y validación de cada sector.",
}
target = Path("artifacts/imagery-inventory.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
