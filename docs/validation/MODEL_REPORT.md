# Informe del modelo y validación local

## Inferencia comprobada

Checkpoint oficial FLAIR RGB, revisión `533aa8f000dd36f2d07279ae73e0263d5f23a976`, SHA-256 `b7900cb1cf34f137c2f86a002dc99bca402d5a0139f8ad6253589ece416a511f`. Se verificaron 24.438.979 parámetros, 19 logits reales y clase edificio en canal 0; ver ADR-002. Los pesos se conservan fuera de Git en data/models y no se descargan al reiniciar.

Se descargó por WCS un recorte oficial Minas 2025 de aproximadamente 260 × 260 m en EPSG:5382. Resolución de trabajo 20 cm, 1300 × 1300 píxeles, 67.600 m² de imagen válida. El benchmark en esta máquina midió 7,02 s de carga y 8,99 s de inferencia CPU con dos hilos. Produjo 74 polígonos y 38.830,8 m² de huella segmentada antes de recortar por identidad catastral. Estos valores no son métricas de precisión y no deben extrapolarse a todo el departamento.

Artefactos reproducibles: artifacts/benchmark/report.json, ortho.png, overlay.png, mask.tif y buildings.geojson. Ejecutar scripts/benchmark_inference.py para obtener mediciones de su infraestructura. La máscara y el GeoJSON son resultados reales, no fixtures.

## Precisión local: PENDIENTE

No se dispone de una muestra independiente etiquetada de Lavalleja. Por tanto no se publican precisión, recall, F1, matriz de confusión ni error de área como si estuvieran demostrados. Las métricas francesas no se trasladan a Uruguay. Las confirmaciones QA prueban el flujo informático y **no** constituyen ground truth.

Propuesta inicial: al menos 200 identidades únicas, muestreo estratificado en ocho grupos de 25: terrenos vacíos, viviendas pequeñas, viviendas grandes, galpones, vegetación/oclusiones, patios/pavimentos, límites parcelarios y suelo suburbano con imagen apta. Equilibrar presencia/ausencia y registrar tamaño, antigüedad, cobertura, calidad de imagen y localidad. Un segundo revisor debe resolver desacuerdos sin mirar primero el resultado automático. No inferir ausencia en áreas sin datos.

Herramienta: scripts/evaluate_model.py recibe un CSV de etiquetas independientes con parcel_id, true_building (0/1), predicted_building (0/1), true_footprint_m2, predicted_footprint_m2 y stratum. Calcula métricas globales y por estrato, MAE y MAPE (excluye áreas reales cero del porcentaje). Registra denominadores y si se alcanzan 200 casos. Conservar identificador de imagen, modelo, revisor y fecha junto al conjunto original.

Umbrales iniciales provisionales: probabilidad 0,5, huella mínima 8 m², ocupación mínima 1 %, objetos de al menos 2 m² y cobertura 95 %. No son garantías. Construcciones pequeñas o probabilidades ambiguas se clasifican como indeterminadas, no como ausencia cierta. La imagen de diciembre 2025 no acredita por sí sola el estado posterior de una parcela.

## Muestra real preparada para etiquetado

`scripts/prepare_validation_sample.py` produjo `artifacts/validation/sample-200.csv` y un manifiesto con hash: 200 identidades oficiales, 50 por cuartil de superficie (20–10.000 m²), selección reproducible por hash catastral dentro del rectángulo de la escena de Minas. No usa el resultado del modelo para seleccionar clases. Las columnas de etiquetas y predicciones están vacías. La pertenencia al rectángulo no certifica cobertura válida de píxeles; verificarla manualmente junto con oclusiones, fecha y estrato semántico.

Primero completar true_building (0/1), true_footprint_m2, reviewer, reviewed_at, image_valid, semantic_stratum y observaciones mediante revisión independiente; resolver desacuerdos con un segundo revisor. Después incorporar las predicciones de la misma imagen/modelo y ejecutar evaluate_model.py. No convertir columnas vacías o imágenes sin cobertura en etiquetas negativas. Conservar el manifiesto y ambas revisiones. Esta muestra inicial no sustituye el balance semántico de ocho grupos propuesto arriba.
