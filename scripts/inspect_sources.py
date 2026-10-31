"""Read-only inspection; never accesses reference environment files."""

import json
import requests

endpoints = [
    (
        "cadastre",
        "https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs",
        dict(
            service="WFS",
            version="2.0.0",
            request="GetFeature",
            typeNames="ideuy:parcelariourbano",
            outputFormat="application/json",
            srsName="EPSG:4326",
            CQL_FILTER="nomdepto='LAVALLEJA'",
            count=1,
        ),
    ),
    (
        "land_use",
        "https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs",
        dict(
            service="WFS",
            version="2.0.0",
            request="GetFeature",
            typeNames="ideuy:uyla_dir_categsuelo",
            outputFormat="application/json",
            srsName="EPSG:4326",
            count=1,
        ),
    ),
    ("model", "https://huggingface.co/api/models/IGNF/FLAIR-INC_rgb_12cl_resnet34-unet", {}),
    (
        "imagery",
        "https://mapas.ide.uy/geoserver-raster/ortofotos/wcs",
        dict(
            service="WCS",
            version="2.0.1",
            request="DescribeCoverage",
            coverageId="ortofotos__minas_lavalleja_mosaico_2025_geotiff",
        ),
    ),
]
for name, url, params in endpoints:
    try:
        response = requests.get(url, params=params, timeout=(10, 90))
        print(name, response.status_code)
        if name == "model":
            data = response.json()
            print(json.dumps({k: data.get(k) for k in ["sha", "siblings", "cardData"]}, ensure_ascii=False))
        elif name == "imagery":
            print(response.text[:12000])
        else:
            data = response.json()
            print(
                json.dumps(
                    {"total": data.get("totalFeatures"), "features": data.get("features", [])[:1]},
                    ensure_ascii=False,
                )[:6000]
            )
    except requests.RequestException as exc:
        print(name, type(exc).__name__)
