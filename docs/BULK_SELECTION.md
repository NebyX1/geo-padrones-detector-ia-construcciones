# Selección múltiple

La pestaña **Selección múltiple** permite dibujar un rectángulo arrastrando el mouse o marcando dos esquinas. Esc cancela el dibujo. Elegir localidad y buscar un padrón en la barra superior restringe la selección. Se incluyen los padrones activos que intersectan el rectángulo, contando una sola vez las identidades con varias piezas.

El conteo se realiza en PostGIS sobre la selección completa: el límite de 1.000 contornos visibles del mapa no recorta el lote. El máximo inicial es **5.000 padrones por selección** (`MAX_BULK_PARCELS`). Si se supera, se informa el total y se solicita reducir el rectángulo; no se analiza un subconjunto silenciosamente.

Antes de iniciar se muestra el número de padrones, superficie de parcelas, subtareas y píxeles estimados. Asignar un nombre y revisar los umbrales de probabilidad y huella mínima. Se utiliza la imagen registrada y el modelo habilitado. La imagen disponible actualmente corresponde a Minas, diciembre de 2025. Las parcelas sin cobertura o con recortes excesivos se conservan como **indeterminadas**, con motivo y sin inventar m².

El análisis se divide en subtareas de hasta 50 padrones (`BULK_CHUNK_SIZE`), respetando además el límite de área de cada trabajo. La cola persistente procesa el lote en segundo plano. Se puede cerrar la pestaña y regresar por el historial de selecciones. El progreso cuenta resultados efectivamente guardados. Cancelar conserva los resultados ya obtenidos y detiene las subtareas pendientes; una inferencia en curso termina cooperativamente en su siguiente punto de cancelación.

**Analítica del lote** presenta indicadores de construcción visible, sin construcción visible, indeterminados, pendientes y errores. Los indicadores superiores corresponden al lote entero. La tabla permite filtrar por estado, intervalo de m² y cobertura mínima, además de localidad y búsqueda de la barra superior. Se ordena por mayor o menor huella, ocupación o número de padrón. El total filtrado y su suma de m² incluyen todas las páginas. El botón de cada fila enfoca su geometría y evidencia en el mapa.

**Exportar casos filtrados a CSV** envía al worker los mismos filtros y orden de la tabla. Incluye todos los casos filtrados, no solo los 50 de la página visible. El archivo UTF-8 con BOM incluye identificadores, m², estado, cobertura, imagen, modelo, versiones catastrales, motivo de incidencias y lote de selección. Las posibles fórmulas se neutralizan. Cuando el lote aún está procesándose, los resultados y filtros pueden evolucionar hasta que termine.

Cada lote conserva membresía, área y versión catastral seleccionadas, parámetros y los resultados de sus propias subtareas. Un nuevo análisis o una actualización posterior del catastro no reemplaza estos resultados históricos. Si el catastro cambia antes de inferir una parcela, el caso queda indeterminado y exige una nueva selección. La geometría histórica se usa al enfocar y exportar el lote.

Los m² representan **huella visible en planta**, no la suma de superficies de todos los pisos. Los resultados requieren interpretación humana. Sin imagen o sin análisis no equivale a sin construcción.

La consulta requiere permiso de lectura; iniciar o cancelar requiere análisis, y exportar requiere exportación. Solo quien creó el lote o un administrador puede cancelarlo. Login, captcha, doble factor y el modo local de prueba se conservan.

API: `POST /api/v1/bulk-selections/preview`, `GET/POST /api/v1/bulk-selections`, `GET /api/v1/bulk-selections/{id}`, `GET /api/v1/bulk-selections/{id}/results` y `POST /api/v1/bulk-selections/{id}/cancel`. Exportación mediante `POST /api/v1/exports` con `filters.bulk_id` y los filtros/orden elegidos. Las mutaciones mantienen CSRF y el inicio admite `Idempotency-Key`.

Para grandes lotes, el almacenamiento comparte un contador de cuota protegido por el bloqueo de PostgreSQL. Evita enumerar todo el bucket por cada máscara; reconcilia en frío, después de interrupciones o reinicios de Redis. La caché vence a los cinco minutos. Las escrituras administrativas externas a la aplicación pueden requerir invalidar ese contador; no deben usarse para eludir la cuota.

La prueba backend usa una selección sintética identificada de 1.005 parcelas para comprobar el conteo completo, fraccionamiento, idempotencia y cancelación. Otra prueba comprueba filtros, orden, paginación y CSV histórico frente a cambios posteriores del catastro. La prueba de navegador usa geometrías oficiales e inferencia FLAIR reales en recursos QA desechables; no constituye una evaluación de precisión ni una certificación de rendimiento de 5.000 inferencias.
