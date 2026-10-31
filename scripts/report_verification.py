"""Publish small, non-secret local verification evidence; refuse failed suites."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
import _bootstrap
import requests

root = _bootstrap.ROOT
report = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Local software verification; no production deployment or local accuracy certification",
    "tests": {},
}
for name in ("backend", "frontend", "e2e"):
    tree = ElementTree.parse(root / f"artifacts/tests/{name}.xml")
    suites = list(tree.iter("testsuite"))
    stats = {
        key: sum(int(s.attrib.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    stats["seconds"] = round(sum(float(s.attrib.get("time", 0)) for s in suites), 3)
    if stats["failures"] or stats["errors"] or not stats["tests"]:
        raise SystemExit(f"No se publica verificación aprobada: suite {name} con fallos o vacía.")
    report["tests"][name] = stats
report["npm_audit"] = json.loads((root / "artifacts/tests/npm-audit.json").read_text(encoding="utf-8-sig"))[
    "metadata"
]["vulnerabilities"]
python_audit = json.loads((root / "artifacts/tests/python-audit.json").read_text(encoding="utf-8"))
report["python_known_vulnerabilities"] = sum(len(d.get("vulns", [])) for d in python_audit["dependencies"])
report["restore_and_production_role"] = json.loads((root / "artifacts/tests/operations.json").read_text())
report["http_load"] = json.loads((root / "artifacts/tests/http-load.json").read_text())
report["bulk_selection"] = json.loads((root / "artifacts/tests/bulk-real.json").read_text())
report["inference"] = json.loads((root / "artifacts/benchmark/report.json").read_text())
spatial = json.loads((root / "artifacts/spatial-benchmark.json").read_text())
report["spatial_benchmark"] = {key: value for key, value in spatial.items() if key != "plan"}
response = requests.get("http://127.0.0.1:8787/api/v1/health/ready", timeout=(3, 5))
response.raise_for_status()
report["local_readiness"] = response.json()
report["validation_sample"] = json.loads((root / "artifacts/validation/sample-200.manifest.json").read_text())
destination = root / "docs/screenshots"
destination.mkdir(exist_ok=True)
for source in (root / "artifacts/screenshots").glob("*.png"):
    shutil.copy2(source, destination / source.name)
target = root / "docs/validation/VERIFIED_RUN.json"
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "tests": report["tests"],
            "npm_known_vulnerabilities": report["npm_audit"]["total"],
            "python_known_vulnerabilities": report["python_known_vulnerabilities"],
            "readiness": report["local_readiness"]["status"],
            "report": str(target),
        },
        indent=2,
    )
)
