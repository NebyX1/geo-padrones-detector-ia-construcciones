"""Bounded metadata checks for official imagery and cadastral alternatives."""

import json
from pathlib import Path
from datetime import datetime, timezone
import requests
from defusedxml import ElementTree

sources = {
    "minas_flight": (
        "https://catalogodatos.gub.uy/api/3/action/package_show",
        {"id": "ide-vuelo-fotogrametrico-minas-diciembre-2025"},
    ),
    "national_orthophotos": (
        "https://mapas.ide.uy/geoservicios/WMS/WMS_Uruguay_IDEuy_Ortofotos",
        {"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
    ),
    "snig": (
        "https://web.snig.gub.uy/arcgisserver/rest/services/Uruguay/SNIG_Catastro/MapServer/1",
        {"f": "pjson"},
    ),
    "mgap": (
        "https://mapas.mgap.gub.uy/arcgis/rest/services/SNIA_Temas/ParcelasCatastrales/MapServer/1",
        {"f": "pjson"},
    ),
    "mvot": ("https://sit.mvot.gub.uy/arcgis/rest/services/07_EXTERNO/CATASTRO/MapServer/3", {"f": "pjson"}),
    "dnc_shapes": (
        "https://catalogodatos.gub.uy/api/3/action/package_show",
        {"id": "direccion-nacional-de-catastro-shapes-del-parcelario-rural-y-urbano"},
    ),
    "dnc_attributes": (
        "https://catalogodatos.gub.uy/api/3/action/package_show",
        {"id": "direccion-nacional-de-catastro-padrones-urbanos-y-rurales"},
    ),
}
report = {"checked_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
for name, (url, params) in sources.items():
    result = {"url": url}
    try:
        response = requests.get(url, params=params, timeout=(8, 20), allow_redirects=False)
        result["status"] = response.status_code
        if response.status_code == 200:
            if name == "national_orthophotos":
                root = ElementTree.fromstring(response.content)
                layers = []
                for item in root.iter():
                    if item.tag.rsplit("}", 1)[-1] == "Layer":
                        row = {}
                        for child in item:
                            tag = child.tag.rsplit("}", 1)[-1]
                            if tag in {"Name", "Title", "Abstract"}:
                                row[tag] = child.text
                        if row.get("Name"):
                            layers.append(row)
                result["layers"] = layers
            else:
                data = response.json()
                if name.startswith("dnc") or name == "minas_flight":
                    package = data.get("result", {})
                    result.update(
                        success=data.get("success"),
                        license_id=package.get("license_id"),
                        license_title=package.get("license_title"),
                        modified=package.get("metadata_modified"),
                        resources=[
                            {"name": r.get("name"), "format": r.get("format"), "url": r.get("url")}
                            for r in package.get("resources", [])
                        ][:100],
                    )
                else:
                    result.update(
                        {
                            k: data.get(k)
                            for k in [
                                "name",
                                "type",
                                "geometryType",
                                "copyrightText",
                                "capabilities",
                                "maxRecordCount",
                                "extent",
                            ]
                        }
                    )
                    result["fields"] = [f["name"] for f in data.get("fields", [])]
    except (requests.RequestException, ValueError, ElementTree.ParseError) as exc:
        result["error"] = type(exc).__name__
    report["sources"][name] = result
    print(name, json.dumps(result, ensure_ascii=False)[:2200], flush=True)
target = Path("artifacts/official-source-checks.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
