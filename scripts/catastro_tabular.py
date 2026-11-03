"""Lectura de datos alfanuméricos DNC de Lavalleja, sin suposiciones sobre PH.

Las claves urbanas son (código de localidad catastral DNC, número de padrón);
las rurales son números de padrón. Un padrón urbano puede tener muchas unidades.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


DEPARTAMENTO = "P"


@dataclass
class DatosCatastro:
    localidades: dict[str, str]
    urbanos: dict[tuple[str, int], dict]
    rurales: dict[int, dict]
    lineas_sin_padron_urbano: dict[tuple[str, int], dict]


def _entero(valor: str) -> int | None:
    valor = valor.strip()
    if not valor:
        return None
    return int(valor)


def _archivo(zip_file: ZipFile, nombre: str):
    matches = [n for n in zip_file.namelist() if n.rsplit("/", 1)[-1].casefold() == nombre.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Se esperaba un archivo {nombre}, encontrados: {len(matches)}")
    return io.TextIOWrapper(zip_file.open(matches[0]), encoding="latin-1", newline="")


def cargar_datos(ruta_zip: str | Path) -> DatosCatastro:
    """Carga el ZIP oficial, manteniendo el cero separado del dato ausente.

    El estado del padrón urbano es positivo si alguna unidad tiene área positiva;
    negativo solo si todas tienen área cero y no hay líneas con área positiva,
    y desconocido cuando faltan datos o el resumen contradice las líneas. Los
    rurales no publican área edificada en esta tabla; su estado es desconocido.
    Los valores PH/UH se conservan tal como vienen: su escala no está confirmada.
    """
    localidades: dict[str, str] = {}
    registros: dict[tuple[str, int], list[dict]] = defaultdict(list)
    lineas: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"cantidad_lineas": 0, "cantidad_lineas_area_positiva": 0,
                 "area_lineas_suma_m2": 0}
    )
    rurales: dict[int, dict] = {}
    with ZipFile(ruta_zip) as z:
        with _archivo(z, "Localidades.csv") as f:
            for row in csv.reader(f):
                if row[0] == DEPARTAMENTO:
                    localidades[row[1]] = row[2]

        with _archivo(z, "Padrones Urbanos.csv") as f:
            for row in csv.reader(f):
                if row[1] != DEPARTAMENTO:
                    continue
                if len(row) < 9:
                    raise ValueError(f"Fila urbana incompleta: {row!r}")
                regimen, _, localidad, numero, block, epss, unidad = row[:7]
                area = _entero(row[8])
                registros[(localidad, int(numero))].append({
                    "regimen": regimen,
                    "block_manzana": block or None,
                    "entrepisos_subsuelo": epss or None,
                    "unidad": _entero(unidad),
                    "area_predio_m2": _entero(row[7]),
                    "area_edificada_valor_original": area,
                    # La escala de PH/UH en la entrega no se pudo verificar.
                    "area_edificada_m2": area if regimen == "CO" else None,
                    "tiene_construccion": None if area is None else area > 0,
                })

        # El archivo usa una codificación defectuosa en el nombre del miembro;
        # el final ASCII identifica de forma inequívoca la tabla.
        nombres_lineas = [n for n in z.namelist() if n.endswith("neas de Construccion.csv")]
        if len(nombres_lineas) != 1:
            raise ValueError("No se encontró una única tabla de líneas de construcción")
        with io.TextIOWrapper(z.open(nombres_lineas[0]), encoding="latin-1", newline="") as f:
            for row in csv.reader(f):
                if row[1] != DEPARTAMENTO:
                    continue
                if len(row) < 15:
                    raise ValueError(f"Línea de construcción incompleta: {row!r}")
                datos_lineas = lineas[(row[2], int(row[3]))]
                datos_lineas["cantidad_lineas"] += 1
                area_linea = _entero(row[14])
                if area_linea is not None and area_linea > 0:
                    datos_lineas["cantidad_lineas_area_positiva"] += 1
                    datos_lineas["area_lineas_suma_m2"] += area_linea

        with _archivo(z, "Padrones Rurales.csv") as f:
            for row in csv.reader(f):
                if row[0] != DEPARTAMENTO:
                    continue
                if len(row) < 4:
                    raise ValueError(f"Fila rural incompleta: {row!r}")
                numero = int(row[1])
                if numero in rurales:
                    raise ValueError(f"Padrón rural repetido: {numero}")
                rurales[numero] = {
                    "padron": numero,
                    "seccion_catastral": _entero(row[2]),
                    "area_predio_m2": _entero(row[3]),
                    "tiene_construccion": None,
                    "area_edificada_m2": None,
                }

    urbanos: dict[tuple[str, int], dict] = {}
    for (localidad, numero), unidades in registros.items():
        estados = [u["tiene_construccion"] for u in unidades]
        estado_resumen = True if True in estados else False if all(s is False for s in estados) else None
        evidencia_lineas = lineas.get((localidad, numero), {
            "cantidad_lineas": 0, "cantidad_lineas_area_positiva": 0, "area_lineas_suma_m2": 0
        })
        conflicto = estado_resumen is False and evidencia_lineas["cantidad_lineas_area_positiva"] > 0
        estado = None if conflicto else estado_resumen
        # No sumar unidades ni combinar CO y PH: podrían representar derechos
        # coexistentes y la escala de PH/UH no está confirmada.
        area = unidades[0]["area_edificada_m2"] if len(unidades) == 1 else None
        urbanos[(localidad, numero)] = {
            "padron": numero,
            "codigo_localidad_dnc": localidad,
            "localidad_dnc": localidades.get(localidad),
            "tiene_construccion": estado,
            "tiene_construccion_segun_resumen": estado_resumen,
            "conflicto_con_lineas_construccion": conflicto,
            "evidencia_lineas_construccion": evidencia_lineas,
            "area_edificada_m2": area,
            "unidades": unidades,
        }
    lineas_sin_padron = {clave: valor for clave, valor in lineas.items() if clave not in urbanos}
    return DatosCatastro(localidades, urbanos, rurales, lineas_sin_padron)
