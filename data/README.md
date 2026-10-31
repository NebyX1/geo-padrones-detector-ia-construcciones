# Datos locales

- raw/: adquisiciones oficiales NDJSON, manifiestos y recortes GeoTIFF; no se versionan en Git.
- models/: checkpoint oficial y manifest.json fijado a revisión y SHA-256; volumen persistente de solo lectura para workers.
- runtime/: caché, archivos operativos y muestras temporales QA; excluido de Git. Los objetos de la instalación se guardan en MinIO privado.
- fixtures/: solo ejemplos sintéticos identificados para probar importaciones, nunca detecciones ficticias en la aplicación.

El catastro se importa a PostGIS con originales y versiones. Los resultados de IA son inmutables y las revisiones se conservan aparte. La descarga completa del mosaico de máxima resolución no forma parte del bootstrap: se trabaja por recortes.
