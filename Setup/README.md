# Reconstrucción de GeoPadrones desde el repositorio

**Para agentes de código y personas administradoras.** Esta guía reconstruye una instalación local funcional desde el código, sin incluir pesos de IA ni datos en Git. Lea también [Fuentes, versiones y límites](FUENTES_Y_LIMITES.md) antes de empezar. Las instrucciones están basadas en el árbol de trabajo del 3 de noviembre de 2026, no en una versión posterior no inspeccionada.

Para una explicación del sistema dirigida a lectores sin conocimientos técnicos, consulte [Project_Info.pdf](Project_Info.pdf). Su fuente editable es `generar_project_info.py`; volver a generarlo es opcional para instalar el sistema y requiere ReportLab y fuentes Segoe UI (Windows) o DejaVu Sans (Linux).

## Punto de partida y límites de reproducibilidad

El commit histórico `110b4d0c17f2379cc28cd8d2f1734e5518ff673a` es anterior a parte de las funciones documentadas y **no basta por sí solo** para reconstruir esta versión. Compruebe que el commit recibido incluye `frontend/src/features/cadastre-compare/`, `backend/app/routes/cadastre_compare.py`, los servicios e importadores relacionados, los scripts `scripts/catastro_*.py`, `scripts/generar_catastro_lavalleja.py`, la migración de limpieza y `docker-compose.gpu.yml`. Para reproducir una versión concreta, use el commit o etiqueta que le indique el responsable; no declare una reconstrucción completa si faltan archivos o hay errores.

No se guardan en el repositorio `.env`, `data/models/`, `data/raw/`, `data/catastro/`, cachés ni volúmenes de PostgreSQL, Redis o MinIO. Un clon no recupera usuarios, contraseñas, trabajos, revisiones, imágenes descargadas, modelos registrados o resultados previos. Para restaurar *ese estado privado exacto* hace falta una copia íntegra y consistente, autorizada y compatible de base de datos, MinIO, configuración privada, modelo y referencias; consulte `docs/deployment/BACKUP_RESTORE.md`. No hay contraseñas predeterminadas recuperables por esta guía.

Los servicios WFS/WCS y los ZIP oficiales pueden cambiar o dejar de estar disponibles. Solo los archivos con los hashes de [Fuentes, versiones y límites](FUENTES_Y_LIMITES.md) son iguales a las entradas usadas entonces. Incluso con entradas idénticas el GeoJSON generado incorpora fecha y ruta de generación y no será necesariamente idéntico byte a byte. Para recuperar también el hash del GeoJSON original y abrir comparaciones históricas es necesario conservar **el archivo original**, no solo regenerarlo. Si no se cuenta con una copia coincidente, obtenga una nueva referencia y comunique la diferencia; no afirme reproducción exacta.

## Requisitos y seguridad

- Windows con Docker Desktop/WSL 2, o Linux con Docker Engine y Compose v2; Python 3.11 de 64 bits, Git y conexión HTTPS a las fuentes. Para ejecutar localmente las pruebas y el build del frontend, instale también Node.js 22 con npm; el build de Docker trae su propio Node. Referencia inicial: 4 CPU, 8 GB de RAM libres y 15 GB de disco; los modelos CUDA y los datos requieren espacio adicional. Docker Desktop debe estar iniciado.
- Para GPU: NVIDIA compatible, controlador del anfitrión, runtime NVIDIA/WSL 2 y soporte de GPU en Docker. La GPU está en el **servidor worker**, no necesariamente en el navegador. Sin GPU, el sistema y ambos modelos pueden ejecutarse en CPU.
- Las órdenes usan la raíz del repositorio como directorio actual. `docker compose` es v2; en caso de conflictos, resuelva los puertos de esta aplicación sin apagar servicios ajenos.
- En un servidor nuevo, genere claves y cuenta propias. Nunca incluya `.env`, datos operativos, captchas, OTP ni contraseñas en Git, logs ni documentación. El modo sin login es exclusivamente una prueba local; no lo exponga a Internet ni lo use en producción.
- No borre volúmenes, ni ejecute `docker compose down -v`, `git clean` o reemplazos destructivos para «arreglar» la instalación. Si hay datos previos, compruebe primero su procedencia y respaldo.

## 1. Clonar y preparar Python

Una vez publicado el código completo, clone este repositorio indicando explícitamente el nombre de la carpeta. Use el commit o etiqueta que indique el responsable cuando necesite una versión concreta. La rama predeterminada puede avanzar con el tiempo.

```text
git clone https://github.com/NebyX1/geo-padrones-detector-ia-construcciones.git Geo-Padron-Detector
cd Geo-Padron-Detector
git status --short
git rev-parse HEAD
docker version
docker compose version
python --version
```

Para fijar una versión concreta use `git checkout COMMIT_O_ETIQUETA_PUBLICADA` solo después de sustituir ese texto por el identificador real. Instale dependencias en un entorno virtual; Shapely, PyProj y Rasterio son necesarias para reconstruir el GeoJSON. Dependencias fijadas: `backend/requirements.txt`, `backend/requirements-dev.txt` y `frontend/package-lock.json`.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe scripts/init_local.py
```

**Linux, shell POSIX:**

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python scripts/init_local.py
```

`init_local.py` crea una configuración `.env` nueva con secretos aleatorios y no reemplaza un `.env` ya existente. En el resto de esta guía, `$PY` representa el ejecutable de la máquina: en PowerShell defina `$PY = '.\.venv\Scripts\python.exe'` y ejecútelo como `& $PY ...`; en Bash defina `PY=.venv/bin/python` y ejecútelo como `"$PY" ...`. En bloques marcados «común», `python` significa ese Python del entorno virtual, activado con `.\.venv\Scripts\Activate.ps1` en PowerShell o `source .venv/bin/activate` en Bash.

## 2. Modelos y directorios

Con el entorno virtual activado:

```text
python -c "from pathlib import Path; [Path(p).mkdir(parents=True, exist_ok=True) for p in ('data/models', 'data/raw', 'data/catastro', 'data/catastro/lavalleja_procesado')]"
python scripts/download_models.py
python scripts/install_unet_model.py
```

El primer script descarga FLAIR y escribe `data/models/manifest.json`; el segundo instala UNet++ y `unetpp.manifest.json`, sin reemplazar FLAIR. Ambos fijan la revisión y verifican SHA-256; no use `main`, enlaces no oficiales ni pesos de procedencia desconocida. En caso de descarga restringida, `scripts/install_unet_model.py --source RUTA` acepta una copia local **del mismo hash**. Los repositorios, SHA y licencias figuran en [Fuentes, versiones y límites](FUENTES_Y_LIMITES.md). La primera descarga y la construcción pueden demorar y requieren red.

## 3. Configurar acceso local e iniciar servicios

Por defecto, `.env.example` conserva acceso protegido. Para reproducir el **modo local temporal sin login que el usuario tiene en esta instalación**, antes de arrancar ejecute:

```text
python scripts/set_local_preview.py on
```

Esta acción conserva el login, captcha y segundo factor y no los elimina. Para exigirlos, use `off`. Este interruptor es solo para `FLASK_CONFIG=development` y hosts locales. **El script con `--restart` usa únicamente los archivos Compose base+dev y puede sustituir el worker GPU:** cuando use GPU, omita `--restart` y recree los servicios con los tres archivos indicados más abajo.

Para CPU, con el entorno virtual activado:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build --wait --wait-timeout 150
```

El servicio `init` ejecuta migraciones Alembic y crea el bucket antes de iniciar los servicios. El acceso local es http://127.0.0.1:8787 y Mailpit de desarrollo http://127.0.0.1:8125. Si usa login real, cree un superadministrador humano con contraseña solicitada de forma oculta:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend flask create-admin
```

Siga los prompts de correo, nombre y contraseña; 2FA llega a Mailpit en desarrollo. Para producción deben configurarse SMTP real, HTTPS, rol de base sin privilegios y secretos propios. Consulte `docs/AUTH_MODES.md` y `docs/deployment/DOCKER.md`.

Registre ambos modelos descargados y la ortofoto de Minas:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend flask register-model /data/models/manifest.json
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend flask register-model /data/models/unetpp.manifest.json
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend flask register-imagery
```

`register-imagery` consulta la descripción real del WCS IDE; requiere red y conserva captura `2025-12`, resolución nativa y límites. La ortofoto se consulta por recortes al analizar, no se incluye completa en Git. Los modelos y la imagen no se habilitan solo con descargar sus archivos: deben registrarse. El worker debe poder leer `/data/models`.

### GPU NVIDIA opcional

Con Docker Desktop en WSL 2 o Linux con runtime NVIDIA y driver compatibles, compruebe primero que Docker detecta la GPU; después compile y cambie el worker del proyecto:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml build worker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d --no-deps worker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml exec worker python -c "import torch; print('CUDA disponible:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'GPU no disponible')"
```

El Dockerfile GPU instala PyTorch 2.6.0 y torchvision 0.21.0 con CUDA 12.4; el host no necesita un kit CUDA idéntico instalado, pero sí un driver compatible. Elegir `cuda` sin una GPU accesible falla explícitamente; no simule resultados ni cambie a CPU sin avisar. Espere que terminen los trabajos antes de recrear el worker. Para volver al worker CPU use `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-deps --build worker`. Si más adelante recrea toda la pila GPU, incluya siempre los tres archivos Compose.

## 4. Descargar e importar capas IDE

Con el entorno virtual activado, Docker/PostGIS iniciado y la configuración local vigente:

```text
python scripts/download_cadastre.py
python scripts/import_cadastre.py data/raw/lavalleja.ndjson
python scripts/download_cadastre.py --land-use --output data/raw/land-use.ndjson
python scripts/import_cadastre.py data/raw/land-use.ndjson --land-use
```

El primer WFS descarga el parcelario urbano de Lavalleja con manifiesto, hash y procedencia; el segundo obtiene categorías de suelo. Cada importación conserva geometrías históricas, agrupa piezas y valida el manifiesto. El resultado de una descarga actual puede diferir de la captura de 2026. El importador accede al PostgreSQL local publicado en el puerto 5432 por el override dev; si usa otro puerto, configure la URL apropiada en el `.env` local sin publicarla. El usuario de pruebas backend necesita crear una base temporal.

## 5. Reconstruir el archivo usado por «Comparar»

Coloque en `data/catastro/` los tres ZIP oficiales **sin descomprimir y con los siguientes nombres exactos**. En [Fuentes, versiones y límites](FUENTES_Y_LIMITES.md) están los enlaces directos y hashes de la instantánea original:

```text
data/catastro/datosabiertosdnc2026-10.zip
data/catastro/paisurbano_shp.zip
data/catastro/paisrural_shp.zip
```

Descargue el ZIP alfanumérico de octubre de 2026 y los ZIP urbano/rural del catálogo DNC; los SHP se actualizan y pueden no conservar la versión histórica. Compruebe las huellas antes de procesarlos. `data/raw/land-use.ndjson` debe existir desde el paso 4. Con el entorno virtual activado:

En Windows use `curl.exe` para evitar el alias de PowerShell; en Linux use `curl`:

```powershell
curl.exe -fL -o data/catastro/datosabiertosdnc2026-10.zip https://catalogodatos.gub.uy/dataset/a0ff3085-b886-454b-8e8b-88f59bd980cc/resource/0bbc79c5-3000-4ef3-9eb2-e7af7cdc74af/download/datosabiertosdnc2026-10.zip
curl.exe -fL -o data/catastro/paisurbano_shp.zip https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/3d211675-14a6-4e69-bc0b-6cc549060633/download/paisurbano_shp.zip
curl.exe -fL -o data/catastro/paisrural_shp.zip https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/2073596d-f122-4030-9eb4-eaca1cdf1e9c/download/paisrural_shp.zip
```

```bash
curl -fL -o data/catastro/datosabiertosdnc2026-10.zip https://catalogodatos.gub.uy/dataset/a0ff3085-b886-454b-8e8b-88f59bd980cc/resource/0bbc79c5-3000-4ef3-9eb2-e7af7cdc74af/download/datosabiertosdnc2026-10.zip
curl -fL -o data/catastro/paisurbano_shp.zip https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/3d211675-14a6-4e69-bc0b-6cc549060633/download/paisurbano_shp.zip
curl -fL -o data/catastro/paisrural_shp.zip https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/2073596d-f122-4030-9eb4-eaca1cdf1e9c/download/paisrural_shp.zip
```

Después de verificar los hashes de [Fuentes, versiones y límites](FUENTES_Y_LIMITES.md):

```text
python scripts/generar_catastro_lavalleja.py
python scripts/verificar_catastro_lavalleja.py
```

La salida principal es `data/catastro/lavalleja_procesado/padrones_lavalleja.geojson`; se genera también `.geojson.gz` y `resumen_y_fuentes.json`. Docker monta el directorio procesado como `/data/catastro:ro` y la API usa `CATASTRE_GEOJSON=/data/catastro/padrones_lavalleja.geojson`. Si la carpeta se creó *después* de iniciar Docker, recree el backend con el mismo conjunto de Compose; no cambie permisos ni vuelva a generar los datos silenciosamente durante una comparación en curso.

Importe a PostGIS **solo** las identidades y geometrías faltantes; el importador es transaccional e idempotente y no sustituye parcelas ya existentes:

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T backend python -c "from app import create_app; from app.services.comparison_cadastre_import import import_geojson_parcels; app=create_app(); ctx=app.app_context(); ctx.push(); print(import_geojson_parcels('/data/catastro/padrones_lavalleja.geojson')); ctx.pop()"
```

Para GPU pueden añadirse `-f docker-compose.gpu.yml` a la misma orden. No importe las 167 identidades sin geometría como parcelas inventadas. La clasificación de suelo es una intersección informativa con la capa IDE; el archivo rural no declara superficie edificada. Las comparaciones almacenan el hash de su referencia y devolverán 409 si se sustituye por otro archivo; restaurar el archivo original es necesario para reabrir esos lotes.

## 6. Verificar el resultado

```text
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail 100 backend worker dispatcher
```

Abra http://127.0.0.1:8787/api/v1/health/ready: debe informar salud de PostGIS, Redis y bucket. En la interfaz compruebe el aviso de prueba local si está activado, los dos modelos, la imagen Minas y la pestaña **Comparar**; filtre categoría, localidad y construcción, observe la vista previa y que los no analizables se explican. Los datos de la instantánea original totalizaban 42.280 identidades, 42.113 con geometría; son referencia para un cotejo del snapshot, **no constantes universales**. Los cambios oficiales o los cruces con una base previa producen números diferentes. Para verificar inferencia de verdad, use una muestra apropiada y una base/cola/bucket de pruebas aislados; no falsifique una respuesta del modelo ni destruya análisis del usuario.

Con PostGIS de desarrollo disponible y entorno virtual activado:

```text
python -m pytest backend/tests -q
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Para navegador, la configuración actual de Playwright requiere Microsoft Edge instalado (`channel: 'msedge'`); para usar Chromium hay que adaptar el canal e instalar ese navegador. La prueba sintética `frontend/e2e/cadastre-compare.spec.ts` intercepta la API; no mide precisión ni realiza inferencia. Las pruebas backend crean y eliminan una base aleatoria de QA; no apuntarlas a un servidor en el que el usuario no autorice bases temporales. Antes de operar una instalación institucional lea también `docs/COMPARAR_CATASTRO.md`, `docs/ANALYSIS_MANAGEMENT.md`, `docs/UNET_GPU.md` y `docs/data-sources/PROVENANCE.md`.

Para ejecutar esa prueba sintética contra el frontend local en ejecución, desde la raíz:

```powershell
Push-Location frontend
$env:E2E_BASE_URL = 'http://127.0.0.1:8787'
npx playwright test e2e/cadastre-compare.spec.ts
Pop-Location
```

```bash
(cd frontend && E2E_BASE_URL=http://127.0.0.1:8787 npx playwright test e2e/cadastre-compare.spec.ts)
```

La inferencia solo está habilitada para la ortofoto de Minas y su cobertura. El valor de antigüedad predeterminado es 730 días; una imagen más antigua puede producir estado indeterminado. Nada de esto certifica precisión del modelo en Lavalleja: esa evaluación independiente sigue pendiente.
