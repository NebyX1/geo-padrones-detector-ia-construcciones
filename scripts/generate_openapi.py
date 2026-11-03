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
        "device": {
            "enum": ["cpu", "cuda"],
            "default": "cpu",
            "description": "Procesador del worker; cuda requiere GPU NVIDIA disponible en el servidor.",
        },
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
    "/bulk-selections/preview": {
        "bounds": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {"type": "number"},
            "description": "Oeste, sur, este y norte en WGS84; selección completa sin truncar por el mapa.",
        },
        "locality": {"type": "string"},
        "q": {"type": "string", "maxLength": 80},
        "scene_id": {"type": "string", "format": "uuid"},
    },
    "/bulk-selections": {
        "bounds": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number"}},
        "name": {"type": "string", "minLength": 1, "maxLength": 120},
        "locality": {"type": "string"},
        "q": {"type": "string", "maxLength": 80},
        "scene_id": {"type": "string", "format": "uuid"},
        "model_version_id": {"type": "string", "format": "uuid"},
        "device": {"enum": ["cpu", "cuda"], "default": "cpu"},
        "probability": {"type": "number", "minimum": 0.1, "maximum": 0.99},
        "min_area": {"type": "number", "minimum": 0},
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

# Cadastral comparisons use the generated local reference file, and launch a
# fresh bounded analysis batch; they never infer a contradiction from null or
# an inconclusive model result.
compare_filters = {
    "category": {"type": "string", "enum": ["todos", "urbano", "suburbano", "rural", "sin_clase"], "default": "todos"},
    "locality": {"type": "string", "maxLength": 40, "default": "todos", "description": "Código DNC, todos o sin_localidad."},
    "state": {"type": "string", "enum": ["todos", "si", "no", "desconocido"], "default": "todos", "description": "Construcción informada por Catastro; desconocido no equivale a no."},
    "padron_desde": {"oneOf": [{"type": "integer", "minimum": 0, "maximum": 999999999}, {"type": "string", "pattern": "^[0-9]{1,9}$"}], "description": "Límite inclusivo; permite subdividir selecciones amplias."},
    "padron_hasta": {"oneOf": [{"type": "integer", "minimum": 0, "maximum": 999999999}, {"type": "string", "pattern": "^[0-9]{1,9}$"}], "description": "Límite inclusivo; no puede ser menor que padron_desde."},
    "scene_id": {"type": "string", "format": "uuid"},
}
compare_analysis = {
    "model_version_id": {"type": "string", "format": "uuid"},
    "device": {"type": "string", "enum": ["cpu", "cuda"], "default": "cpu"},
    "probability": {"type": "number", "minimum": 0.1, "maximum": 0.99},
    "min_area": {"type": "number", "minimum": 0, "maximum": 1000},
    "min_object_area": {"type": "number", "minimum": 0, "maximum": 1000},
    "min_occupancy": {"type": "number", "minimum": 0, "maximum": 1},
    "min_coverage": {"type": "number", "minimum": 0.5, "maximum": 1},
    "max_image_age_days": {"type": "integer", "minimum": 1, "maximum": 36500},
}
payloads["/catastro-comparar/preview"] = compare_filters
payloads["/catastro-comparar/runs"] = {**compare_filters, **compare_analysis}

spec["components"]["schemas"] = {
    "CadastreComparePreview": {
        "type": "object",
        "description": "Solo available se procesa; el resto se contabiliza por motivo. Los registros con líneas sin resumen se identifican por separado.",
        "properties": {
            **{key: {"type": "integer", "minimum": 0} for key in ["total", "available", "unavailable", "sin_geometria", "no_conciliados", "fuera_cobertura", "supera_limites", "lineas_sin_resumen", "max_parcels", "mapped"]},
            "can_analyze": {"type": "boolean"},
            "dataset_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    },
    "CadastreCompareOption": {"type": "object", "properties": {"value": {"type": "string"}, "label": {"type": "string"}, "count": {"type": "integer", "minimum": 0}}},
    "CadastreCompareSummary": {"type": "object", "properties": {key: {"type": "integer", "minimum": 0} for key in ["discrepancia", "coincide", "sin_referencia", "indeterminado", "pendiente", "total"]}},
    "CadastreCompareBatch": {"type": "object", "description": "Lote persistido; selection_filters conserva los filtros y el resumen de excluidos.", "properties": {
        "id": {"type": "string", "format": "uuid"}, "status": {"type": "string"},
        "total": {"type": "integer"}, "processed": {"type": "integer"},
        "bounds": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number"}},
        "selection_filters": {"type": "object"}, "jobs": {"type": "array", "items": {"type": "object"}},
        "cancel_requested": {"type": "boolean"}, "scene_id": {"type": "string", "format": "uuid"},
        "model_version_id": {"type": "string", "format": "uuid"}, "parameters": {"type": "object"},
    }},
    "CadastreCompareFeatureCollection": {"type": "object", "properties": {
        "type": {"const": "FeatureCollection"}, "features": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"const": "Feature"}, "id": {"type": "string"}, "geometry": {"type": ["object", "null"]},
            "properties": {"type": "object", "properties": {
                "id": {"type": "string"}, "parcel_id": {"type": "string"}, "padron": {"type": "string"},
                "locality": {"type": ["string", "null"]}, "categoria_suelo": {"type": "string"},
                "codigo_localidad": {"type": ["string", "null"]}, "processing_status": {"type": "string"},
                "declared_building": {"type": ["boolean", "null"]}, "model_state": {"type": "string"},
                "outcome": {"enum": ["discrepancia", "coincide", "sin_referencia", "indeterminado", "pendiente"]},
                "m2_huella_detectada": {"type": ["number", "null"]}, "coverage": {"type": ["number", "null"]},
                "result_id": {"type": ["string", "null"]}, "error": {"type": ["string", "null"]},
                "tiene_registro_alfanumerico": {"type": "boolean"}, "lineas_sin_resumen": {"type": "boolean"},
            }},
        }}}}},
}


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


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
        if method == "GET" and not suffix.startswith(("/auth/", "/catastro-comparar/")):
            parameters += [
                {"name": name, "in": "query", "schema": {"type": "string"}} for name in ["limit", "offset"]
            ]
        if suffix in ["/parcels", "/parcels/search", "/dashboard", "/bulk-selections/{identifier}/results"]:
            parameters += [
                {"name": name, "in": "query", "schema": {"type": "string"}}
                for name in sorted(FILTER_KEYS | {"format"})
            ]
        if suffix == "/catastro-comparar/options" and method == "GET":
            parameters.append({"name": "category", "in": "query", "schema": compare_filters["category"]})
        if suffix == "/catastro-comparar/runs/{identifier}/features" and method == "GET":
            parameters.extend([
                {"name": "bbox", "in": "query", "schema": {"type": "string"}, "description": "Oeste,sur,este,norte en WGS84."},
                {"name": "outcome", "in": "query", "schema": {"type": "string", "enum": ["todos", "discrepancia", "coincide", "sin_referencia", "indeterminado", "pendiente"], "default": "todos"}},
            ])
        if parameters:
            operation["parameters"] = parameters
        if method in {"POST", "PATCH"}:
            operation["security"] = [{"session": [], "csrf": []}]
            properties = payloads.get(suffix, {})
            if properties:
                schema = {"type": "object", "properties": properties}
                if suffix == "/catastro-comparar/runs":
                    schema["required"] = ["scene_id", "model_version_id"]
                    schema["additionalProperties"] = False
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": schema}},
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
        if method == "POST" and suffix in ["/analysis/jobs", "/exports", "/comparisons", "/bulk-selections", "/catastro-comparar/runs"]:
            operation["responses"]["202"] = {
                "description": "Trabajo persistido para procesamiento asíncrono; consultar progreso y estado."
            }
            operation.setdefault("parameters", []).append(
                {"name": "Idempotency-Key", "in": "header", "schema": {"type": "string", "maxLength": 64}}
            )
        if suffix.startswith("/catastro-comparar/"):
            operation["responses"]["503"] = {"description": "Referencia catastral no disponible o inválida."}
            operation["description"] = (
                "La categoría proviene del cruce territorial. Los valores desconocidos o los resultados "
                "del modelo indeterminados no se clasifican como discrepancias. Cada comparación usa "
                "exclusivamente los resultados de su propio lote."
            )
            response_schema = None
            if suffix == "/catastro-comparar/options" and method == "GET":
                response_schema = {"type": "object", "properties": {key: {"type": "array", "items": ref("CadastreCompareOption")} for key in ["categories", "localities", "states"]}}
            elif suffix == "/catastro-comparar/preview" and method == "POST":
                response_schema = ref("CadastreComparePreview")
            elif suffix == "/catastro-comparar/runs" and method == "POST":
                response_schema = {"type": "object", "properties": {"batch": ref("CadastreCompareBatch"), "preview": ref("CadastreComparePreview")}}
            elif suffix == "/catastro-comparar/runs" and method == "GET":
                response_schema = {"type": "object", "properties": {"items": {"type": "array", "items": ref("CadastreCompareBatch")}}}
            elif suffix == "/catastro-comparar/runs/{identifier}" and method == "GET":
                response_schema = {"type": "object", "properties": {"batch": ref("CadastreCompareBatch"), "preview": ref("CadastreComparePreview"), "summary": ref("CadastreCompareSummary")}}
            elif suffix == "/catastro-comparar/runs/{identifier}/features" and method == "GET":
                response_schema = ref("CadastreCompareFeatureCollection")
            if response_schema:
                status = "202" if suffix == "/catastro-comparar/runs" and method == "POST" else "200"
                operation["responses"][status]["content"] = {"application/json": {"schema": response_schema}}
                if status == "202":
                    operation["responses"].pop("200", None)
        spec["paths"].setdefault(path, {})[method.lower()] = operation
text = json.dumps(spec, ensure_ascii=False, indent=2)
for target in [_bootstrap.ROOT / "docs/api/openapi.json", _bootstrap.ROOT / "backend/app/openapi.json"]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
print(f"OpenAPI generado: {len(spec['paths'])} rutas")
