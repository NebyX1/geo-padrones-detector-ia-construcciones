import json
from importlib.metadata import metadata, version, PackageNotFoundError
from pathlib import Path

root = Path(__file__).resolve().parents[1]
frontend = json.loads((root / "frontend/package.json").read_text())
lines = [
    "# Inventario de dependencias directas",
    "",
    "Generado desde los paquetes realmente instalados. No sustituye revisión de todas las dependencias transitivas ni asesoramiento jurídico. Mantener avisos de licencia al redistribuir.",
    "",
    "## Frontend",
    "",
    "| Paquete | Versión efectiva | Licencia declarada |",
    "| --- | --- | --- |",
]
for name in sorted(frontend["dependencies"]):
    info = json.loads((root / "frontend/node_modules" / name / "package.json").read_text(encoding="utf-8"))
    license_ = info.get("license", "NO DECLARADA")
    if isinstance(license_, dict):
        license_ = license_.get("type", "NO DECLARADA")
    lines.append(f"| {name} | {info['version']} | {license_} |")
lines += ["", "## Python", "", "| Paquete | Versión efectiva | Licencia declarada |", "| --- | --- | --- |"]
for line in (root / "backend/requirements.txt").read_text().splitlines():
    name = line.split("==")[0].split("[")[0]
    if not name:
        continue
    try:
        info = metadata(name)
        license_ = (
            info.get("License-Expression")
            or info.get("License")
            or " / ".join(v for v in info.get_all("Classifier", []) if v.startswith("License"))
            or "REVISAR PAQUETE"
        )
        license_ = license_.splitlines()[0][:160].replace("|", "/")
        lines.append(f"| {name} | {version(name)} | {license_} |")
    except PackageNotFoundError:
        lines.append(f"| {name} | NO INSTALADO | PENDIENTE |")
lines += [
    "",
    "## Otros componentes",
    "",
    "FLAIR: Etalab 2.0 en pesos oficiales; implementación de referencia FLAIR-1 Apache-2.0. MinIO servidor: AGPL-3.0, compilado desde fuente oficial fijada. PostgreSQL/PostGIS, Redis, Nginx, GDAL y componentes embebidos en wheels conservan sus propias licencias y requieren inventario operativo de imagen. Los repositorios Buzón no incluyen licencia de proyecto explícita; publicación externa pendiente de aclaración con sus titulares. Ver data-sources/PROVENANCE.md.",
    "",
]
(root / "docs/THIRD_PARTY.md").write_text("\n".join(lines), encoding="utf-8")
print("Inventario de licencias generado en docs/THIRD_PARTY.md")
