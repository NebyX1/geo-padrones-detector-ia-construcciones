"""Only fixed official endpoints; callers cannot supply URLs or CQL expressions."""

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from defusedxml import ElementTree
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WFS_URL = "https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs"
WCS_URL = "https://mapas.ide.uy/geoserver-raster/ortofotos/wcs"
WMS_URL = "https://mapas.ide.uy/geoserver-raster/ortofotos/wms"
HISTORICAL_WMS_URL = "https://mapas.ide.uy/geoservicios/WMS/WMS_Uruguay_IDEuy_Ortofotos"
PARCEL_LAYER = "ideuy:parcelariourbano"
LAND_USE_LAYER = "ideuy:uyla_dir_categsuelo"
MINAS_COVERAGE = "ortofotos__minas_lavalleja_mosaico_2025_geotiff"


def http_session(retries=4):
    session = requests.Session()
    retry = Retry(
        total=retries, backoff_factor=1, status_forcelist=[429, 502, 503, 504], allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "GeoPadrones-Lavalleja/0.1 (official geospatial data ingestion)"
    return session


def get_bytes(url, params=None, max_bytes=50000000, timeout=(15, 150), retries=4):
    # Requests used for WFS/WCS only; redirects cannot move downloads to another host.
    if url not in {WFS_URL, WCS_URL, WMS_URL, HISTORICAL_WMS_URL}:
        raise ValueError("Fuente geográfica no autorizada.")
    with http_session(retries).get(
        url, params=params, timeout=timeout, stream=True, allow_redirects=False
    ) as response:
        response.raise_for_status()
        if response.is_redirect or 300 <= response.status_code < 400:
            raise ValueError("Redirección de fuente oficial no permitida.")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("La respuesta supera el límite de descarga.")
            chunks.append(chunk)
        content = b"".join(chunks)
    if b"ExceptionReport" in content[:2000] or b"ServiceException" in content[:2000]:
        raise ValueError("El servicio geográfico devolvió una excepción OGC.")
    return content


def wfs_metadata(layer):
    if layer not in {PARCEL_LAYER, LAND_USE_LAYER}:
        raise ValueError("Capa no autorizada.")
    capabilities = get_bytes(WFS_URL, dict(service="WFS", version="2.0.0", request="GetCapabilities"))
    ElementTree.fromstring(capabilities)
    schema = get_bytes(
        WFS_URL, dict(service="WFS", version="2.0.0", request="DescribeFeatureType", typeNames=layer)
    )
    root = ElementTree.fromstring(schema)
    fields = [
        {"name": el.attrib.get("name"), "type": el.attrib.get("type")}
        for el in root.iter()
        if el.tag.endswith("element")
    ]
    return dict(
        fields=fields, capabilities_sha256=hashlib.sha256(capabilities).hexdigest(), schema=schema.decode()
    )


def download_wfs(destination, layer=PARCEL_LAYER, bbox=None, page_size=1000, max_features=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = wfs_metadata(layer)
    params = dict(
        service="WFS",
        version="2.0.0",
        request="GetFeature",
        typeNames=layer,
        outputFormat="application/json",
        srsName="EPSG:4326",
    )
    if layer == PARCEL_LAYER:
        params["CQL_FILTER"] = "nomdepto='LAVALLEJA'"
    if bbox:
        from .geospatial import validate_wgs84
        from shapely.geometry import box, mapping

        validate_wgs84(mapping(box(*bbox)))
        # Use actual schema geometry name. BBOX cannot be combined with CQL_FILTER as separate OGC filter.
        geometry_field = next(f["name"] for f in metadata["fields"] if "gml:" in (f["type"] or ""))
        spatial = f"BBOX({geometry_field},{','.join(str(float(v)) for v in bbox)},'EPSG:4326')"
        params["CQL_FILTER"] = (
            f"({params['CQL_FILTER']}) AND {spatial}" if params.get("CQL_FILTER") else spatial
        )
    seen, offset, total = set(), 0, None
    temp = destination.with_suffix(destination.suffix + ".part")
    with temp.open("w", encoding="utf-8", newline="\n") as output:
        while True:
            count = min(page_size, max_features - offset) if max_features else page_size
            if count <= 0:
                break
            raw = get_bytes(WFS_URL, {**params, "count": count, "startIndex": offset})
            data = json.loads(raw)
            if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                raise ValueError("Respuesta WFS inválida.")
            if total is None:
                raw_total = data.get("numberMatched", data.get("totalFeatures"))
                total = int(raw_total) if str(raw_total).isdigit() else None
            features = data["features"]
            if not features:
                break
            for feature in features:
                fid = str(feature.get("id", ""))
                if not fid or fid in seen:
                    raise ValueError("Paginación WFS inconsistente: ID vacío o repetido.")
                seen.add(fid)
                output.write(json.dumps(feature, ensure_ascii=False, separators=(",", ":")) + "\n")
            offset += len(features)
            print(f"WFS {layer}: {offset}/{total if total is not None else '?'}", flush=True)
            if (total is not None and offset >= total) or len(features) < count:
                break
    if total is not None and offset != min(total, max_features or total):
        raise ValueError(f"Descarga incompleta: {offset} de {total}. Se conserva .part para diagnóstico.")
    temp.replace(destination)
    digest = hashlib.file_digest(destination.open("rb"), "sha256").hexdigest()
    manifest = dict(
        source=WFS_URL,
        layer=layer,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        sha256=digest,
        count=offset,
        matched=total,
        bbox=bbox,
        complete=max_features is None,
        capture_date=None,
        **metadata,
    )
    destination.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
