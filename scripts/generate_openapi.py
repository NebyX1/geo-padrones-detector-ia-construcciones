import json
import re
import _bootstrap
from pathlib import Path
from app import create_app
from app.repositories.parcels import FILTER_KEYS

app = create_app()
spec = {
    "openapi": "3.1.0",
    "info": {
        "title": "GeoPadrones Lavalleja",
        "version": "0.1.0",
        "description": "API de catastro, evidencia aérea, inferencia, declaraciones y revisión. Todas las mutaciones requieren X-CSRFToken, incluyendo login.",
    },
    "servers": [{"url": "/"}],
    "paths": {},
    "components": {
        "securitySchemes": {
            "session": {"type": "apiKey", "in": "cookie", "name": "geopadrones_session"},
            "csrf": {"type": "apiKey", "in": "header", "name": "X-CSRFToken"},
        }
    },
    "security": [{"session": []}],
}
payloads = {
    "/auth/login": {
        "email": {"type": "string", "format": "email"},
        "password": {"type": "string", "maxLength": 256},
        "captcha_id": {"type": "string", "format": "uuid"},
        "captcha_answer": {"type": "string", "pattern": "^[0-9]{1,2}$"},
    },
    "/auth/2fa/verify": {"code": {"type": "string", "pattern": "^[0-9]{6}$"}},
    "/auth/password/forgot": {"email": {"type": "string", "format": "email"}},
    "/auth/password/reset": {
        "challenge_id": {"type": "string", "format": "uuid"},
        "code": {"type": "string"},
        "password": {"type": "string", "minLength": 12, "maxLength": 256},
    },
    "/auth/password/change": {
        "current_password": {"type": "string"},
        "password": {"type": "string", "minLength": 12},
    },
    "/users": {
        "email": {"type": "string", "format": "email"},
        "name": {"type": "string"},
        "password": {"type": "string", "minLength": 12},
        "role": {"enum": ["superadmin", "admin", "analyst", "reviewer", "viewer"]},
    },
    "/analysis/jobs": {
        "parcel_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {"type": "string", "format": "uuid"},
        },
        "scene_id": {"type": "string", "format": "uuid"},
        "model_version_id": {"type": "string", "format": "uuid"},
        "probability": {"type": "number", "minimum": 0.1, "maximum": 0.99, "default": 0.5},
        "min_area": {"type": "number", "minimum": 0, "default": 8},
        "min_occupancy": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.01},
        "min_coverage": {"type": "number", "minimum": 0.5, "maximum": 1, "default": 0.95},
    },
    "/comparisons": {
        "batch_id": {"type": "string", "format": "uuid"},
        "absolute_tolerance": {"type": "number", "default": 20},
        "percent_tolerance": {"type": "number", "default": 20},
        "comparable_area": {"type": "boolean", "default": False},
    },
    "/exports": {
        "format": {"enum": ["csv", "geojson"]},
        "filters": {
            "type": "object",
            "description": "locality,q,state,min_area,max_area,bbox,ids,review_status,comparison_id,comparison_state; selección y filtros exactos.",
        },
    },
    "/reviews/{identifier}": {
        "version": {"type": "integer", "minimum": 1},
        "status": {"enum": ["CONFIRMADO", "CORREGIDO", "RECHAZADO"]},
        "state": {"enum": ["CON_CONSTRUCCION_VISIBLE", "SIN_CONSTRUCCION_VISIBLE", "INDETERMINADO"]},
        "observations": {"type": "string", "minLength": 3, "maxLength": 4000},
        "geometry": {
            "type": ["object", "null"],
            "description": "GeoJSON EPSG:4326; el servidor recorta y calcula área en EPSG:5382.",
        },
    },
}
for rule in app.url_map.iter_rules():
    if not rule.rule.startswith("/api/v1"):
        continue
    path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule.rule)
    suffix = path.removeprefix("/api/v1")
    for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
        operation = {
            "operationId": rule.endpoint.replace(".", "_") + "_" + method.lower(),
            "summary": rule.endpoint.replace(".", " · ").replace("_", " "),
            "tags": [suffix.strip("/").split("/")[0]],
            "responses": {
                str(code): {"description": desc}
                for code, desc in [
                    (200, "Resultado JSON, imagen o archivo según endpoint"),
                    (400, "CSRF ausente/vencido o petición inválida"),
                    (401, "Sesión requerida/revocada"),
                    (403, "Rol sin permiso"),
                    (404, "Registro no encontrado"),
                    (409, "Conflicto o versión concurrente"),
                    (422, "Validación de datos"),
                    (429, "Límite de solicitudes"),
                    (500, "Error interno sin detalles sensibles"),
                ]
            },
        }
        parameters = [
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
            for name in re.findall(r"{([^}]+)}", path)
        ]
        if method == "GET" and not suffix.startswith("/auth/"):
            parameters += [
                {"name": name, "in": "query", "schema": {"type": "string"}} for name in ["limit", "offset"]
            ]
        if suffix in ["/parcels", "/parcels/search", "/dashboard"]:
            parameters += [
                {"name": name, "in": "query", "schema": {"type": "string"}}
                for name in sorted(FILTER_KEYS | {"format"})
            ]
        if parameters:
            operation["parameters"] = parameters
        if method in {"POST", "PATCH"}:
            operation["security"] = [{"session": [], "csrf": []}]
            properties = payloads.get(suffix, {})
            if properties:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object", "properties": properties}}},
                }
        if suffix.startswith("/auth/") and suffix not in [
            "/auth/me",
            "/auth/logout",
            "/auth/password/change",
        ]:
            operation["security"] = [] if method == "GET" else [{"csrf": []}]
        if suffix.startswith("/health"):
            operation["security"] = []
        if (suffix == "/imports/csv" or suffix == "/reviews/{identifier}/attachments") and method == "POST":
            upload_schema = {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "encoding": {"enum": ["utf-8-sig", "utf-8", "cp1252"]},
                },
            }
            if suffix.endswith("/attachments"):
                upload_schema["properties"].pop("encoding")
                upload_schema["properties"]["authorized"] = {"type": "string", "const": "true"}
                upload_schema["required"].append("authorized")
            operation["requestBody"] = {
                "required": True,
                "content": {"multipart/form-data": {"schema": upload_schema}},
            }
        if method == "POST" and suffix in ["/analysis/jobs", "/exports", "/comparisons"]:
            operation["responses"]["202"] = {
                "description": "Trabajo persistido para procesamiento asíncrono; consultar progreso y estado."
            }
            operation.setdefault("parameters", []).append(
                {"name": "Idempotency-Key", "in": "header", "schema": {"type": "string", "maxLength": 64}}
            )
        spec["paths"].setdefault(path, {})[method.lower()] = operation
text = json.dumps(spec, ensure_ascii=False, indent=2)
for target in [_bootstrap.ROOT / "docs/api/openapi.json", _bootstrap.ROOT / "backend/app/openapi.json"]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
print(f"OpenAPI generado: {len(spec['paths'])} rutas")
