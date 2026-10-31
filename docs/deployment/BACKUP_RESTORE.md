# Respaldo y restauración

Respaldar conjuntamente base, objetos, manifiestos/pesos, configuración privada y revisión de código. Los secretos se almacenan cifrados fuera del repositorio, con acceso restringido. Establecer responsables, retención y objetivos RPO/RTO; una copia no comprobada no constituye restauración verificada.

## Backup PostgreSQL

Preferir `scripts/backup.py` (pg_dump dentro del contenedor y docker compose cp) para evitar corrupción binaria por redirección PowerShell. El script no imprime credenciales. Ejecutarlo desde la raíz con servicios activos; produce un archivo .dump de formato custom en artifacts/backups, excluido de Git. Los privilegios del rol de backup pueden separarse del rol de aplicación en producción.

Para backups coherentes, pausar la creación de nuevos trabajos, dejar terminar operaciones en curso y detener worker/dispatcher durante la ventana. Un snapshot consistente del volumen de MinIO debe tomarse con el servicio detenido o mediante una herramienta S3 autorizada que conserve todos los objetos y versiones. No copiar a ciegas archivos internos de MinIO mientras escribe. Respaldar data/models/manifest.json y su checkpoint con SHA-256; los modelos oficiales también pueden redescargarse de su revisión fijada.

## Restauración aislada

1. Crear un entorno y volúmenes nuevos; no apuntar a producción. Instalar exactamente la revisión del código respaldado.
2. Crear una base PostgreSQL vacía con PostGIS. Copiar el dump dentro del contenedor y restaurar con `pg_restore --no-owner --no-acl --exit-on-error -d BASE_NUEVA archivo.dump`, con credenciales tomadas del entorno interno del contenedor, sin argumentos de contraseña. No usar --clean contra una base existente sin aprobación explícita y backup.
3. Restaurar objetos en un MinIO vacío conservando claves; restaurar pesos y verificar sus hashes. Reponer secretos desde su sistema privado. No mezclar cookies/sesiones antiguas: generar una SECRET_KEY nueva para revocarlas.
4. Ejecutar migraciones pendientes una sola vez, verificar health/ready, recuentos de parcelas, versiones, resultados, acciones de revisión y accesibilidad de objetos. Ejecutar análisis y exportación de un sector acotado y confirmar trazabilidad.
5. Registrar duración real, hashes, responsable, errores y resultado. Solo después promover mediante el procedimiento autorizado de la institución.

Se verificó una restauración aislada mediante `python scripts/verify_operations.py RUTA_AL_DUMP`: recuperó 25.953 parcelas, 18 localidades y 117 categorías, con cero geometrías inválidas. El script crea bases y un rol aleatorios, aplica las migraciones con privilegios restringidos, comprueba HTTPS/health y elimina sus recursos temporales. Informe en artifacts/tests/operations.json. No sustituye un ensayo conjunto de recuperación de objetos, modelos y configuración, ni se efectuó sustitución de una base de producción.
