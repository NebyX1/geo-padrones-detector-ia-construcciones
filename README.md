# GeoPadrones Lavalleja

Plataforma municipal de exploración catastral, segmentación de construcciones visibles, cálculo de huellas en m², comparación de declaraciones y revisión humana. Implementación real con React/Vite y Flask, PostgreSQL/PostGIS, RQ/Redis y MinIO. **El flujo principal fue probado de extremo a extremo con ortofoto, parcelas e inferencia reales. No se certifica todavía precisión local ni habilitación para producción institucional.**

La pestaña **Comparar** permite filtrar la referencia de Catastro por categoría territorial, localidad y construcción declarada, ejecutar un lote de análisis y destacar posibles discrepancias en el mapa. La cobertura de imagen habilitada para inferencia corresponde al vuelo de Minas de diciembre de 2025; los casos sin referencia o sin imagen suficiente no se consideran discrepancias automáticamente. Véase [Comparar Catastro](docs/COMPARAR_CATASTRO.md).

## Acceso temporal para pruebas locales

La instancia local puede habilitar entrada directa sin autenticación. El login, captcha numérico y doble factor se conservan; el login está disponible en `/login`. `scripts/set_local_preview.py on|off` cambia la opción para development; después recree los servicios con los mismos archivos Compose usados al iniciar. El modo directo está bloqueado en producción. Si usa GPU, no utilice el atajo `--restart`, pues no incluye el override GPU. Ver [modos de acceso](docs/AUTH_MODES.md) y [Setup](Setup/README.md).

## Ejecutar

Para reconstruir la instalación desde un clon sin los pesos ni los datos, siga **[Setup: instalación paso a paso](Setup/README.md)**. La guía incluye Windows y Linux, descarga y verificación de FLAIR y UNet++, configuración CPU o GPU NVIDIA, carga de imágenes y catastro, y la preparación de la pestaña Comparar. Las fuentes, revisiones y hashes figuran en [Fuentes y límites](Setup/FUENTES_Y_LIMITES.md). El documento [Project_Info.pdf](Setup/Project_Info.pdf) explica el proyecto en lenguaje claro.

Se requiere Docker/Compose v2, Python 3.11 y conexión a las fuentes; para probar y compilar el frontend localmente, Node.js 22. La orientación inicial es 4 CPU, 8 GB RAM y 15 GB de disco, con espacio adicional para GPU y datos. La aplicación se abre en **http://localhost:8787** y Mailpit de desarrollo en http://localhost:8125. El administrador inicial se crea con prompts y contraseña oculta; no existe una cuenta persistente por defecto.

Las fuentes públicas y sus fechas pueden cambiar. El código y las instrucciones no restauran por sí solos usuarios, resultados, revisiones ni las copias exactas originales de los datos: para recuperar ese estado se necesitan los archivos originales y un respaldo consistente y autorizado de la instalación.

## Arquitectura y referencias

```mermaid
flowchart LR
  UI[React 19 / Leaflet] --> Nginx
  Nginx --> API[Flask /api/v1]
  API --> PG[(PostgreSQL / PostGIS)]
  API --> RQ[(Redis / RQ)]
  RQ --> W[Worker CPU o GPU / FLAIR o UNet++]
  W --> PG
  W --> S3[(MinIO privado)]
  W --> IDE[IDE WFS / WCS]
  API --> S3
  API --> SMTP[SMTP / 2FA]
```

Las referencias usadas durante el desarrollo se documentan en [ARQUITECTURA_SAMPLE](docs/ARQUITECTURA_SAMPLE.md); `sample/` está excluido de Git y no es necesario para ejecutar la aplicación. Se conservan factory Flask, extensiones, SQLAlchemy/Alembic, sesiones Flask-Login, Argon2, CSRF, Marshmallow, Blueprints y separación por servicios; frontend por features, Axios central, React Query, Zustand, RHF/Zod, Tailwind/DaisyUI, Framer Motion y diseño institucional.

PostGIS sustituye MariaDB para GiST, consultas por bbox, MVT e intersecciones métricas. Las geometrías originales y reparaciones se versionan. Cuando cambia la geometría de una parcela se invalida su resultado actual, conservando la inferencia histórica. Las correcciones humanas no sobrescriben resultados automáticos.

## Evidencia real

El código incorpora la selección del modelo FLAIR o UNet++ registrado y de CPU o GPU NVIDIA en el worker. La prueba local de velocidad y los pasos de instalación figuran en [UNet++ y procesador de análisis](docs/UNET_GPU.md). La opción GPU necesita el worker CUDA optativo y una GPU accesible desde Docker.

El benchmark sobre 260 × 260 m de Minas utiliza GeoTIFF oficial en EPSG:5382, remuestreado de 5 a 20 cm. Procesó 1300 × 1300 píxeles en aproximadamente 9 s de inferencia CPU y generó 74 polígonos antes de intersecar con parcelas. Estos números son resultados de ejecución, **no una evaluación de precisión**.

El checkpoint oficial llamado `FLAIR-INC_rgb_12cl_resnet34-unet` contiene realmente **19 canales de salida** en la revisión verificada. Se carga estrictamente, con weights_only, normalización RGB 0–255 y building en canal 0. La correspondencia y hashes se documentan en [ADR-002](docs/decisions/ADR-002-flair-checkpoint.md).

Las capturas de `docs/screenshots/` se obtienen del test real de navegador sobre una muestra temporal de parcelas oficiales. Su CSV es una declaración **sintética identificada exclusivamente para QA**. Ninguna cuenta ni declaración QA se incorpora a la instancia principal.

![Explorador con ortofoto y evidencia real](docs/screenshots/explorer.png)

![Comparación real con declaración de QA sintética](docs/screenshots/comparisons.png)

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests --junitxml=artifacts/tests/backend.xml
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Los tests backend crean y eliminan una base PostGIS aleatoria aislada. Incluyen CSRF, 2FA, bloqueo, replay, roles, revocación, importación, duplicados, intersecciones exactas, CRS, cobertura, filtros, revisión concurrente, exportación segura, cuotas y versionado.

End-to-end: `scripts/qa_server.py` crea una base, bucket, cola y cuenta de fixture temporales, carga una muestra oficial y levanta un worker Docker. Iniciar Vite en frontend (`$env:VITE_PROXY_TARGET="http://127.0.0.1:5051"; npm run dev`, proxy exclusivo de QA) y ejecutar `npm run test:e2e` con Microsoft Edge; para usar Chromium hay que ajustar el canal en la configuración de Playwright. Detener el servidor al finalizar; si una interrupción del sistema impide su finally, `scripts/qa_cleanup.py NOMBRE_EXACTO_BASE_QA` limpia únicamente recursos con formato y manifiesto de propiedad verificados. No usar fixtures como evidencia administrativa.

La suite cubre selección múltiple, comparación catastral y gestión de análisis, revisiones y resultados. La comprobación de dependencias documentada no sustituye el mantenimiento continuo.

Reportes, máscaras, GeoJSON, benchmark y capturas se guardan en artifacts/, excluido de Git. [Verificación ejecutada](docs/validation/VERIFIED_RUN.json), [informe del modelo](docs/validation/MODEL_REPORT.md), [estado por misión](docs/missions/STATUS.md), [plan](docs/missions/PLAN.md), [OpenAPI](docs/api/openapi.json).

## Operación y límites

- Imagen y modelo están versionados con fuente, fecha y hash. La captura se muestra como diciembre 2025, conservando precisión de mes.
- Huella visible no equivale a superficie total edificada ni a una determinación jurídica. Ausencia de datos se clasifica como indeterminada.
- Descargas e inferencias por sectores: límite de 100 padrones / 100.000 m² por trabajo, 16 millones de píxeles, CSV 10 MB y cuota de objetos configurable. [Selección múltiple](docs/BULK_SELECTION.md) admite 5.000 padrones por lote y lo divide en subtareas de hasta 50, con analítica, orden y CSV de todos los casos filtrados. No se infiere automáticamente todo el departamento.
- PostgreSQL, Redis y MinIO son privados en Compose principal. Producción exige cookies Secure, HTTPS y rol de base sin privilegios administrativos; [ADR-003](docs/decisions/ADR-003-production-roles.md).
- MinIO se compila desde fuente oficial archivada y commit fijado, porque las imágenes públicas probadas no están disponibles. Su mantenimiento y licencia AGPL deben revisarse antes de producción.
- Pendientes: etiquetado independiente de al menos 200 padrones; evaluación de otras ortofotos/localidades; completar vínculo normativo de categorías; ensayo de carga y validación de la infraestructura productiva. Ver el estado detallado, sin marcar esos puntos como terminados.

Guías: [usuario](docs/USER_GUIDE.md), [Docker](docs/deployment/DOCKER.md), [Coolify](docs/deployment/COOLIFY.md), [backup/restauración](docs/deployment/BACKUP_RESTORE.md), [procedencia y licencias](docs/data-sources/PROVENANCE.md).

## Problemas frecuentes

Si un servicio no está saludable, revisar `docker compose ps` y sus logs antes de reintentar; no borrar volúmenes. Los healthchecks internos usan IPv4 explícita donde el servicio no escucha IPv6. Si un puerto está ocupado, cambiar el puerto de este proyecto, sin detener otras aplicaciones.

Un análisis en PENDING espera al dispatcher/Redis; un FAILED expone una categoría de error y conserva el historial. Revisar el worker y la disponibilidad del modelo, fuente IDE, espacio y cobertura antes de recuperarlo. Una parcela sin cobertura no se clasifica como baldío.

Una recuperación que abre una URL equivocada indica FRONTEND_URL desactualizada: usar la dirección de la interfaz activa. Si falla el 2FA, comprobar SMTP o Mailpit y la hora del servidor; nunca desactivar CSRF ni registrar códigos en logs. Para desarrollo Python, pytest ya configura el import path del backend.
