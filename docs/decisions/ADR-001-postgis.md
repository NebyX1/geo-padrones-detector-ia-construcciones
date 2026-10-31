# ADR-001: PostgreSQL y PostGIS

Estado: aceptado. Fecha: 2026-10-30.

MariaDB del boilerplate no es la base adecuada para intersecciones masivas, GiST y teselas MVT. Se conserva SQLAlchemy/Alembic y se usa PostgreSQL 16 con PostGIS 3.5 y GeoAlchemy2. Geometrías originales en EPSG:4326; áreas e intersecciones en EPSG:5382, CRS métrico de la ortofoto de Minas. Jamás se miden grados cuadrados como m².

La identidad funcional es coddepto + codloccat + padron; cada entidad WFS conserva su ID técnico y geometrías versionadas. Las partes de una identidad se unen antes de medir para evitar doble conteo. Las categorías de suelo intersectadas se conservan con proporción de área; no se fuerza una categoría única.

La API consulta bbox con índice espacial y límite explícito, ofrece MVT y paginación. Los resultados automáticos son inmutables; correcciones y declaraciones se guardan por separado. El esquema de producción usa PostGIS exclusivamente; tests matemáticos unitarios pueden usar Shapely, sin simular que sustituyen la integración con PostGIS.
