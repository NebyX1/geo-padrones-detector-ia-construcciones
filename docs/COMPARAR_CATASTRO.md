# Comparar Catastro con el modelo

La pestaña **Comparar** selecciona registros de `data/catastro/lavalleja_procesado/padrones_lavalleja.geojson` por categoría de suelo, localidad y construcción informada. Los filtros opcionales por número permiten dividir selecciones grandes. Antes de iniciar se muestra el total y se separan las parcelas sin geometría, sin correspondencia, fuera de la imagen o con recortes superiores al límite.

La selección apta se procesa en segundo plano con el modelo y CPU o GPU elegidos. La comparación usa exclusivamente los resultados del lote nuevo: un análisis anterior del mismo padrón no determina el color. El mapa muestra en rojo las posibles discrepancias; también distingue coincidencias, referencias no definidas, resultados indeterminados y pendientes. Los lotes quedan disponibles en el historial de esta vista.

Solo se considera discrepancia una diferencia entre un valor catastral conocido y un resultado concluyente del modelo. Un dato catastral desconocido, imagen insuficiente o error de análisis no significa ausencia de construcción. Los resultados son indicios para revisión humana; el área edificada declarada y la huella observada no son necesariamente equivalentes.

El GeoJSON añade una categoría territorial calculada con la capa IDE y puede marcar categorías mixtas o cobertura parcial; no acredita situación jurídica. El archivo rural no informa construcción, de modo que su valor es desconocido. La ortofoto habilitada para inferencia es la de Minas, diciembre de 2025: no se pueden analizar automáticamente parcelas fuera de su cobertura. El máximo por comparación es el valor configurado en `MAX_BULK_PARCELS`; si se supera, acotá el rango de padrones y procesá las partes por separado.

## Fuentes y puesta en marcha

Compose monta el directorio del GeoJSON en `/data/catastro` en modo de solo lectura y establece `CATASTRE_GEOJSON`. Si el archivo falta o está dañado, la vista informa que la referencia no está disponible. Cada comparación guarda el SHA-256 de su referencia; si esta cambia, el lote no se compara silenciosamente contra datos distintos.

Las parcelas que faltaban en la base se agregan con `app.services.comparison_cadastre_import.import_geojson_parcels`. La importación es transaccional e idempotente: no sustituye geometrías, versiones ni resultados existentes; los registros sin geometría no se inventan. Los rurales se identifican internamente con el código de localidad técnica `R`, que no significa que Catastro les haya asignado una localidad. El importador urbano no debe retirar esos registros rurales durante una actualización del WFS.

Consulte [la guía del GeoJSON](CATASTRO_PREPARADO.md) para detalles de origen y del significado de sus valores.
