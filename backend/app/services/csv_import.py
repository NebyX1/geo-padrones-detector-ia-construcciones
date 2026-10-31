import csv
import io
import math
import unicodedata
from collections import Counter
from sqlalchemy import select
from ..extensions import db
from ..models import Parcel, CadastralLocality, ImportedParcelDeclaration
from .cadastre import normalize_id

TRUE_VALUES = {"si", "true", "1", "con construccion", "construido", "edificado"}
FALSE_VALUES = {"no", "false", "0", "sin construccion", "baldio"}
FIELDS = {
    "department",
    "locality",
    "padron",
    "declared_building",
    "declared_empty",
    "declared_m2",
    "observations",
}


def folded(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(value).strip().lower()) if unicodedata.category(c) != "Mn"
    )


def boolean(value):
    text = folded(value)
    if not text:
        return None
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError("VALOR_BOOLEANO_INVALIDO")


def number(value, decimal=","):
    value = str(value).strip()
    if not value:
        return None
    if decimal == ",":
        value = value.replace(".", "").replace(",", ".")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("SUPERFICIE_INVALIDA")
    return result


def csv_reader(raw, options=None):
    options = options or {}
    encoding = options.get("encoding", "utf-8-sig")
    if encoding not in {"utf-8-sig", "utf-8", "cp1252"}:
        raise ValueError("Codificación no admitida.")
    text = raw.decode(encoding, errors="strict")
    if "\x00" in text:
        raise ValueError("El archivo contiene bytes nulos y no es CSV válido.")
    delimiter = options.get("delimiter")
    if delimiter not in {None, ",", ";", "\t"}:
        raise ValueError("Separador no admitido.")
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:16384], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    columns = reader.fieldnames
    if not columns or len(columns) > 100 or len(set(columns)) != len(columns) or any(not c for c in columns):
        raise ValueError("Columnas vacías, duplicadas o demasiadas columnas.")
    return reader, columns, delimiter


def preview(raw, options=None):
    reader, columns, delimiter = csv_reader(raw, options)
    rows = []
    for index, row in enumerate(reader):
        if index >= 20:
            break
        if None in row:
            raise ValueError("Una fila tiene más campos que columnas.")
        rows.append(row)
    return dict(columns=columns, rows=rows, delimiter=delimiter)


def validate_mapping(mapping, columns):
    if not isinstance(mapping, dict) or set(mapping) - FIELDS:
        raise ValueError("Mapeo de columnas inválido.")
    if not mapping.get("padron") or not mapping.get("locality") or not mapping.get("department"):
        raise ValueError("Mapee departamento, localidad y padrón para evitar conciliación ambigua.")
    if any(v not in columns for v in mapping.values() if v):
        raise ValueError("Una columna mapeada no existe en el archivo.")
    if not (mapping.get("declared_building") or mapping.get("declared_empty") or mapping.get("declared_m2")):
        raise ValueError("Mapee al menos un dato declarado de construcción o superficie.")


def reconcile(raw, mapping, options=None):
    options = options or {}
    reader, columns, _ = csv_reader(raw, options)
    validate_mapping(mapping, columns)
    lookup = {}
    for identifier, department, locality_code, padron, name in db.session.execute(
        select(Parcel.id, Parcel.coddepto, Parcel.codloccat, Parcel.padron, CadastralLocality.name)
        .join(CadastralLocality, Parcel.locality_id == CadastralLocality.id)
        .where(Parcel.active.is_(True))
    ):
        lookup[(department, locality_code, padron)] = identifier
        lookup[(department, folded(name), padron)] = identifier
    seen = {}
    for line, original in enumerate(reader, start=2):
        if line > 100002:
            raise ValueError("El archivo supera 100000 registros; divídalo en lotes.")
        issues = []
        row = {field: original.get(column, "") or "" for field, column in mapping.items() if column}
        key, parcel_id, building, area = {}, None, None, None
        if None in original or any(v is None for v in original.values()):
            issues.append("NUMERO_DE_CAMPOS_INVALIDO")
            original = {str(k): v for k, v in original.items()}
        try:
            department = normalize_id(row.get("department"))
            if department == "LAVALLEJA":
                department = "P"
            locality = str(row.get("locality", "")).strip()
            padron = normalize_id(row.get("padron"))
            key = dict(coddepto=department, codloccat=locality, padron=padron)
            parcel_id = lookup.get((department, locality.upper(), padron)) or lookup.get(
                (department, folded(locality), padron)
            )
            if not parcel_id:
                issues.append("NO_CONCILIADO")
            if not locality:
                issues.append("LOCALIDAD_FALTANTE")
        except ValueError:
            issues.append("IDENTIFICADOR_INVALIDO")
        try:
            building = boolean(row.get("declared_building", ""))
            empty = boolean(row.get("declared_empty", ""))
            if empty is not None:
                if building is not None and building == empty:
                    issues.append("DECLARACION_CONTRADICTORIA")
                else:
                    building = not empty
            area = number(row.get("declared_m2", ""), options.get("decimal", ","))
            if building is False and area is not None and area > 0:
                issues.append("DECLARACION_CONTRADICTORIA")
        except (ValueError, TypeError) as exc:
            issues.append(
                str(exc)
                if str(exc) in {"VALOR_BOOLEANO_INVALIDO", "SUPERFICIE_INVALIDA"}
                else "VALOR_INVALIDO"
            )
        signature = tuple(key.values())
        if signature and signature in seen:
            issues.append("DUPLICADO")
            if seen[signature] != (building, area):
                issues.append("DECLARACION_CONTRADICTORIA")
        elif signature:
            seen[signature] = (building, area)
        yield dict(
            row_number=line,
            parcel_id=parcel_id,
            key=key,
            declared_building=building,
            declared_m2=area,
            observations=str(row.get("observations", ""))[:4000],
            issues=issues,
            original=original,
        )


def process_batch(batch, raw, callback=None):
    counts = Counter()
    for index, record in enumerate(reconcile(raw, batch.mapping, batch.options), start=1):
        db.session.add(ImportedParcelDeclaration(batch_id=batch.id, **record))
        counts["rows"] += 1
        counts["matched" if record["parcel_id"] and not record["issues"] else "issues"] += 1
        for issue in record["issues"]:
            counts[issue] += 1
        if index % 500 == 0:
            db.session.flush()
            if callback:
                callback(index)
    batch.summary = dict(counts)
    batch.status = "CONFIRMED"
    return dict(counts)
