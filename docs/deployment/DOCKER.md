# Instalación y operación con Docker

Requisitos: Docker Engine/Compose v2, al menos 4 CPU, 8 GB de RAM libres y 15 GB de disco para imágenes, pesos y sectores iniciales. Las primeras compilaciones descargan PyTorch y construyen MinIO desde fuente oficial. Los datos, objetos y modelos no están incluidos en las imágenes.

Desde la raíz:

```powershell
python scripts/init_local.py
python scripts/download_models.py
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec backend flask create-admin
```

El bootstrap genera secretos nuevos solo si no existe .env. No imprime valores ni copia configuraciones de sample. La contraseña del administrador se solicita oculta y no se admite como argumento CLI. No existe registro público ni cuenta de producción por defecto.

Abrir http://localhost:8787. Mailpit local de pruebas: http://localhost:8125; SMTP host 1125. PostgreSQL 5432, Redis 6379 y MinIO 9000/9001 se publican **solo en 127.0.0.1** al usar el override dev. Si hay conflictos, cambiar únicamente puertos de host en ese override y la configuración local correspondiente; no detener servicios de otros proyectos.

Compose principal mantiene bases, Redis y MinIO sin puertos publicados. Nginx es el único ingreso. Los servicios necesitan red de salida para IDE, correo y S3. En dev, una segunda red permite los bindings loopback; en producción se mantiene la red interna para servicios de datos.

## Inicialización de datos

Con Python local y dependencias backend instaladas:

```powershell
python scripts/download_cadastre.py
python scripts/import_cadastre.py data/raw/lavalleja.ndjson
python scripts/download_cadastre.py --land-use --output data/raw/land-use.ndjson
python scripts/import_cadastre.py data/raw/land-use.ndjson --land-use
```

La descarga es paginada y valida IDs, esquema, cantidad y hash. La importación conserva originales, registra reparaciones y unifica piezas con la misma identidad. Repetir el mismo archivo es idempotente. Una instantánea nueva se versiona; las parcelas ausentes en una instantánea completa se inactivan sin borrar su historial. Una descarga parcial no retira identidades; se rechazan versiones vacías o reducciones masivas para exigir revisión operativa. El origen normativo no se inventa si el servicio no lo ofrece.

Para ejecutar importaciones desde el contenedor, copiar el archivo y su manifiesto a `/data/runtime/import/` con `docker compose cp`, y ejecutar `docker compose exec backend python /app/scripts/import_cadastre.py /data/runtime/import/lavalleja.ndjson`. La importación CLI es una tarea operativa; el procesamiento CSV de usuarios sí corre por RQ.

```powershell
docker compose exec backend flask register-model /data/models/manifest.json
docker compose exec backend flask register-imagery
docker compose exec backend flask init-bucket
```

El directorio `data/models` se monta de solo lectura. Para descargar en el servidor, ejecutar el script una sola vez sobre ese directorio persistente antes de iniciar nuevos workers. Nunca se descarga en cada arranque. La imagen estándar suministrada y validada usa CPU.

## Worker opcional con GPU NVIDIA

Existe una imagen opcional separada con PyTorch CUDA 12.4 en `worker/Dockerfile.gpu` y una configuración en `docker-compose.gpu.yml`. El 2 de noviembre de 2026 se comprobó en esta máquina que un contenedor temporal sin red, con usuario sin privilegios, accede a la RTX 3050 y ejecuta UNet++ sobre una ortofoto real. Tras recuperar Redis, también se verificó el análisis completo mediante una cola y una base de pruebas aisladas.

Con Docker Desktop usando WSL 2, un controlador NVIDIA compatible y el acceso a GPU confirmado, construir e iniciar únicamente el worker de este proyecto:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml build worker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d --no-deps worker
```

El archivo opcional reserva una GPU NVIDIA y una réplica de worker. La imagen incluye CUDA y también puede ejecutar trabajo en CPU; elegir GPU requiere que la aplicación y el dispositivo estén configurados para ello. Los archivos de pesos ocupan disco, mientras que la memoria de GPU utilizada durante la inferencia debe medirse: no son cantidades equivalentes.

Para volver al worker estándar de CPU, cuando no haya trabajos en curso:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-deps --build worker
```

Cambiar de imagen recrea el worker. Espere a que termine cualquier trabajo en curso para evitar interrumpirlo. No se deben eliminar los volúmenes para cambiar de dispositivo.

## Migraciones y salud

`init` ejecuta una sola vez `flask db upgrade && flask init-bucket`; backend y worker dependen de su éxito. No hay migraciones en el entrypoint de cada réplica. Despliegues simultáneos desde herramientas externas deben serializar esa tarea.

`/api/v1/health` verifica proceso; `/api/v1/health/ready` comprueba PostGIS, Redis y bucket. Los resultados degradados devuelven 503. Métricas Prometheus requieren rol superadministrador en `/api/v1/metrics`; no publicar ese endpoint sin control de acceso.

```powershell
docker compose ps
docker compose logs --tail 100 backend worker dispatcher
docker compose exec backend flask dispatch-pending
docker compose exec backend flask recover-job ID_DEL_TRABAJO
```

El dispatcher reintenta el outbox PENDING cuando Redis vuelve. Cancelación es cooperativa entre ventanas/parcelas; los resultados ya confirmados permanecen. Recuperar trabajos solo tras corregir la causa y verificar que RQ los considera fallidos/detenidos. El callback registra fallos incluso si no puede importar el módulo de inferencia.

## Desarrollo sin contenedores para API/UI

Levantar solo postgres-postgis, redis, minio y mailpit con el override dev. Crear `.venv`, instalar backend/requirements-dev.txt y worker/requirements.txt (PyTorch CPU desde su índice oficial). Desde la raíz con PYTHONPATH=backend: `python -m flask --app wsgi:app run --host 127.0.0.1 --port 5051`. En frontend: `npm ci` y `npm run dev`. Vite usa por defecto la API del stack en 127.0.0.1:8787. Para una API Python local o QA, configurar `$env:VITE_PROXY_TARGET="http://127.0.0.1:5051"` antes de `npm run dev`. Ajustar FRONTEND_URL a la URL real de la interfaz para los enlaces de recuperación. Las variables VITE_* se incorporan al build y nunca deben contener secretos.

No ejecutar `docker compose down -v` en instalaciones con datos que se quieran conservar. El cierre normal `docker compose down` conserva volúmenes.
