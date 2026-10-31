# Misiones y aceptación

Cada misión requiere código, evidencia y pruebas antes de pasar a VERIFICADA. STATUS.md contiene los resultados ejecutados y bloqueos reales. Se continúa con trabajo independiente cuando un servicio o fuente externa bloquea una comprobación.

| Misión | Objetivo y alcance | Dependencias | Aceptación / pruebas |
| --- | --- | --- | --- |
| 0 | Auditar referencias, versiones, seguridad, licencias, contratos y roadmap | GitHub | Clones y arquitectura documentados |
| 1 | React, Flask, PostGIS, Redis, MinIO, migración, Compose | 0, Docker | Stack saludable y consultas UI → API → DB |
| 2 | Sesión, 2FA, recuperación, RBAC, usuarios, auditoría | 1, SMTP | Pruebas de permisos, CSRF, revocación y login E2E |
| 3 | WFS paginado, importación idempotente, versiones, suelo, búsqueda y MVT | 1, IDE | Parcela real importada y visualizada |
| 4 | WCS por recortes, CRS, validez, caché y teselas | 3, IDE | Ortofoto real alineada con parcela |
| 5 | Checkpoint FLAIR fijado, normalización, ventanas y worker CPU | 4, pesos | Inferencia verdadera y benchmark |
| 6 | Unión, intersección, m², cobertura, estados y persistencia | 5 | Geometrías sintéticas exactas y resultado real |
| 7 | Mapa por bbox, selección, capas, filtros, detalle y tabla | 3–6 | Navegación sin descargar el departamento completo |
| 8 | CSV/TSV, preview, mapping, validación y conciliación | 2–3 | Casos válidos, ambiguos, contradictorios, duplicados |
| 9 | Comparación versionada, tolerancias, filtros y exportaciones | 6, 8 | Discrepancias trazables y CSV seguro |
| 10 | Revisión, corrección geométrica, muestra y métricas | 6, 9 | Original preservado y evaluación local documentada |
| 11 | Seguridad, concurrencia, fallos, límites y rendimiento | anteriores | Tests, mediciones y limitaciones explícitas |
| 12 | Docker, Coolify, backup/restore, bootstrap y entrega | anteriores | Instalación limpia y aceptación global |

Todas las tareas se registran contra los criterios del pedido original. No se generan detecciones ni métricas ficticias. Fixtures sintéticos se limitan a tests, identificados como tales. No se hará push ni despliegue externo sin autorización explícita.
