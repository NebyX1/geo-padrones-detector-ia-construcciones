# Evaluación preliminar de alternativas

Se mantiene FLAIR como detector principal obligatorio. No se añade otra dependencia pesada sin medir una ventaja sobre imágenes y etiquetas independientes de Lavalleja.

| Recurso | Categoría | Decisión y comprobación necesaria |
| --- | --- | --- |
| [GeoAI](https://github.com/opengeos/geoai) | Biblioteca de herramientas geoespaciales/IA, MIT según repositorio | No es un checkpoint único. Elegir un detector concreto exigiría fijar pesos, licencia de esos pesos, dependencias y benchmark local; no se incorpora sin ventaja medida |
| [SAM2](https://github.com/facebookresearch/sam2) | Segmentación asistida por prompts | Candidato para edición guiada futura. No se considera detector automático de edificios. El repositorio declara Apache/BSD para componentes; revisar licencia de cada checkpoint, tamaños y GPU al seleccionar variante |
| Modelos HOTOSM | Checkpoints específicos por evaluar | No se selecciona un artefacto arbitrario bajo una etiqueta general. Falta determinar modelo, revisión, licencia, resolución y calidad local antes de descargar |
| [Google Open Buildings](https://sites.research.google/gr/open-buildings/) | Dataset vectorial de huellas ya inferidas | Fuente complementaria, no motor de inferencia. Ofrece elección CC BY-4.0 / ODbL 1.0. Verificar cobertura, antigüedad y procedencia para Lavalleja antes de comparar |
| [Microsoft Global Building Footprints](https://github.com/microsoft/GlobalMLBuildingFootprints) | Dataset vectorial de huellas existentes | No se confunde con pesos descargables. Requiere comprobar versión, licencia y fechas de las imágenes por región; no sustituye evidencia Minas 2025 |
| [Overture Buildings](https://docs.overturemaps.org/guides/buildings/) | Dataset integrado de edificios y partes | Reúne fuentes con atribuciones/licencias y fechas diversas. Conservar source/provenance, GERS ID y geometría original si se integra; no asumir que representa construcción actual |

No se atribuye a estas alternativas una precisión en Uruguay no medida. Pesos, tamaños y costes de GPU no se inventan: varían por variante y no se seleccionó una versión adicional. La validación local documentada en MODEL_REPORT.md es la condición para una comparación técnica útil.
