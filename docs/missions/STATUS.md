# Estado de implementación

Actualizado: 2026-10-30, America/Montevideo (evidencias con timestamps UTC del 31).

Estado global: FUNCIONAL Y VERIFICADA EN LOCAL; aceptación del build de producción aprobada. La precisión local del modelo sigue pendiente. No hubo push ni despliegue externo.

| Misión | Estado | Implementado y evidencia |
| --- | --- | --- |
| 0 | VERIFICADA | Referencias clonadas y SHA fijados; arquitectura, dependencias, licencias, contratos y decisiones documentados en ARQUITECTURA_SAMPLE.md y decisions/. No se leyó sample/backend/.env. |
| 1 | VERIFICADA LOCAL | React, Flask, PostGIS, Redis, MinIO, SMTP de pruebas, migraciones, init, worker y dispatcher construidos; Compose con volúmenes y healthchecks. |
| 2 | VERIFICADA LOCAL | Sesión, Argon2, CSRF, captcha numérico, 2FA SMTP, recuperación, revocación, roles, usuarios, último superadmin y auditoría; pruebas de servidor y login de navegador. Administrador inicial por CLI interactiva. |
| 3 | VERIFICADA | WFS paginado real: 25.994 geometrías, 25.953 identidades, 18 localidades, 41 piezas adicionales y 2 reparaciones; 117 geometrías de categorías de suelo. GiST, bbox, MVT, versiones e importación idempotente. |
| 4 | VERIFICADA EN MINAS | WCS real EPSG:5382, captura 2025-12, 5 cm nativos y trabajo a 20 cm, caché privada, WMS alineado. WMS histórico urbano 2017–2018 comprobado, capa de comparación visual; inferencia histórica no habilitada. |
| 5 | VERIFICADA | Checkpoint oficial fijado por revisión/hash, carga estricta de 19 logits, normalización oficial, ventanas con solape, máscara, vectorización y RQ CPU. Benchmark verdadero de Minas. |
| 6 | VERIFICADA | Unión y recorte por identidad, m² en EPSG:5382, cobertura, ocupación, estados, persistencia de huellas y máscara. Casos matemáticos exactos y resultado real del worker. |
| 7 | VERIFICADA LOCAL | Consultas por extensión, selección clic/múltiple/polígono, tabla virtual, inspector, filtros, temas IA/superficie/ocupación/cobertura/comparación, capas, opacidad y múltiples vistas locales. Capas y selección por polígono verificadas en la aceptación final. |
| 8 | VERIFICADA LOCAL | CSV/TSV, BOM/Windows-1252, preview, mapping reutilizable, normalización, validación, conciliación, incidencias, confirmación asíncrona y detalle paginado. |
| 9 | VERIFICADA LOCAL | Comparaciones congelan result_id, tolerancias y equivalencia de superficies explícita, mapa temático, paginación y exportación por filtros/selección. Filas sin conciliar se conservan en exportaciones no espaciales. |
| 10 | SOFTWARE VERIFICADO; PRECISIÓN LOCAL PENDIENTE | Confirmar/corregir/rechazar, edición de huella recortada a geometría histórica, originales inmutables, adjuntos autorizados privados y solicitud de nueva inferencia. Muestra real de 200 identidades preparada sin etiquetas (50 por cuartil de superficie), propuesta de balance semántico y evaluador disponibles; no hay métricas de precisión publicadas. |
| 11 | VERIFICADA EN ALCANCE LOCAL | Permisos, CSRF, replay, cuotas, límites, dos revisores concurrentes y creación idempotente simultánea; outbox, cancelación, callback de fallos, timeouts, métricas y logs sin secretos. Benchmark espacial sobre catastro completo. No es certificación de carga productiva. |
| 12 | VERIFICADA LOCAL; COOLIFY PREPARADO | Dockerfiles y Compose, bootstrap, rol PostgreSQL sin privilegios, HTTPS de producción, backup y restauración aislada comprobados. Coolify documentado; no se desplegó por falta de autorización explícita. |

## Evidencias ejecutadas

- Backend: pytest/PostGIS en bases aleatorias, eliminadas al terminar; informe artifacts/tests/backend.xml. 71 casos aprobados; incluye protección contra promoción de resultados catastrales obsoletos y liberación de conexiones PostGIS durante esperas WMS.
- Frontend: 9 tests Vitest, ESLint y build TypeScript/Vite; informe artifacts/tests/frontend.xml.
- Navegador: Playwright con SMTP real, parcela oficial, worker Linux con FLAIR, CSV de QA explícitamente sintético, comparación, revisión y CSV descargado. Informe artifacts/tests/e2e.xml: aprobado en 41,533 s sobre build compilado; incluye selección por polígono y exportación de discrepancias seleccionadas desde la UI.
- Dependencias: npm audit y pip-audit sin vulnerabilidades conocidas en la comprobación ejecutada. Informes artifacts/tests/. Se documenta el override compatible de minimatch 11.0.1 para herramientas de lint.
- Restauración: 25.953 parcelas, 18 localidades y 117 categorías; cero geometrías inválidas. Bootstrap y migraciones con rol sin SUPERUSER/CREATEDB/CREATEROLE; producción rechaza el rol privilegiado. artifacts/tests/operations.json.
- HTTP: 40 consultas concurrentes, concurrencia 8, cero errores; percentiles reales en VERIFIED_RUN.json. Muestra QA de 201 geometrías y servidor Flask de desarrollo, sin certificación de capacidad productiva.
- Rendimiento: consulta espacial del catastro completo, mediana 2,127 ms / p95 3,214 ms en 20 consultas con caché caliente; no incluye red ni renderizado. FLAIR sobre 1300 × 1300 píxeles: carga 7,02 s e inferencia 8,99 s con dos hilos CPU. Medidas específicas de esta máquina.

## Límites pendientes y alcance

1. Etiquetar y revisar independientemente al menos 200 padrones; recién entonces informar precision/recall/F1 y error de superficie. No se trasladan métricas francesas a Uruguay.
2. Verificar cobertura, fecha y aptitud de imagen para otras localidades antes de habilitar inferencia. Las fotos históricas son una ayuda visual; su resolución y fecha exacta por parcela no se presumen.
3. Relacionar categorías de suelo con su instrumento normativo oficial: la capa consultada no entrega ese dato.
4. Habilitación institucional: SMTP real, dominio/HTTPS, responsables, retención, escaneo de malware de adjuntos, revisión de licencias (boilerplates sin licencia publicada, React-Leaflet Hippocratic-2.1, MinIO AGPL) y carga/recuperación bajo infraestructura objetivo. Ningún despliegue externo se considera probado.
5. No hay cuenta persistente por defecto. La revisión automática rechazó crear una cuenta privilegiada de QA con contraseña guardada en disco. Se descartó ese paso y las pruebas usan exclusivamente una cuenta fixture en base temporal; el administrador propio se crea con flask create-admin y contraseña oculta.
6. El backup PostgreSQL se restauró en aislamiento; la recuperación conjunta de MinIO/modelos/configuración debe ensayarse en el entorno de operación con su política RPO/RTO.

Fixtures sintéticos solo en tests y declaraciones de QA, identificados como tales. La adquisición, geometrías, ortofotos y segmentación del ensayo son reales. No hay inferencia masiva del departamento ni declaración jurídica automática.

## Entrega y cierre

Informe consolidado con cantidades, tiempos, auditorías, restauración y salud: [VERIFIED_RUN.json](../validation/VERIFIED_RUN.json). Aplicación principal activa en http://127.0.0.1:8787; el primer administrador se crea por CLI interactiva. Se eliminaron todas las cuentas/bases/buckets/colas/workers de QA y se cerraron los previews auxiliares. PostgreSQL/MinIO/Redis y la aplicación principal permanecen disponibles con sus datos oficiales. Capturas verificadas en ../screenshots/.

Se corrigió además la espera de WMS para no retener conexiones de base ni bloquear consultas de parcelas durante la carga de teselas; caché por cobertura oficial estable, timeouts acotados y validación de coordenadas. La probabilidad media se calcula exclusivamente sobre detecciones válidas dentro de la parcela. El backup PostgreSQL final restaurado contiene la revisión f2a08bc931d7. No se publicó código ni se cambió infraestructura externa.

## Cambio solicitado el 2026-10-31: captcha y entrada local temporal

Se agregó al login la suma numérica del ejemplo de sample, validación de servidor, expiración y consumo de un solo uso. El login y el doble factor quedan preservados en la etiqueta Git local `auth-captcha-2fa-preserved` (`22bfbd9`). Por pedido expreso del usuario se añadió `DEV_AUTH_BYPASS`, con entrada directa solo en development/localhost, aviso visible, auditoría de identidad técnica y rechazo en producción. Desactivar la opción restaura login/captcha/2FA sin quitar código. Instrucciones en ../AUTH_MODES.md. Los informes de verificación anteriores describen la entrega inicial; la nueva ejecución se registra por separado.

Verificación del cambio de acceso: 79 tests backend, 10 frontend y 2 pruebas Playwright aprobadas (flujo protegido completo más navegación de prueba sin credenciales). Antes de activar el modo local, /auth/me devolvió 401 y /auth/captcha 200; activado, /auth/me devuelve identidad técnica local. Se limpió la QA efímera. La instancia de pruebas solicitada permanece activa en 127.0.0.1:8787.
