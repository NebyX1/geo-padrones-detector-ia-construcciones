# Procedencia y condiciones de reutilización

Fecha de comprobación: 2026-10-30 (UTC de adquisición conservado en manifiestos).

| Recurso | Fuente primaria / revisión | Comprobación |
| --- | --- | --- |
| Parcelario urbano Lavalleja | https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs · ideuy:parcelariourbano | GetCapabilities, DescribeFeatureType, 26 páginas: 25.994 geometrías, 25.953 identidades, 18 localidades; 41 piezas con claves repetidas y 2 reparaciones |
| Categorías de suelo | Mismo WFS · ideuy:uyla_dir_categsuelo | 117 entidades descargadas; 5 geometrías reparadas; originales preservados en fuente local versionada por hash |
| Ortofoto Minas 2025 | https://mapas.ide.uy/geoserver-raster/ortofotos/wcs · ortofotos__minas_lavalleja_mosaico_2025_geotiff | DescribeCoverage verificó EPSG:5382, píxel 0,05 m y bounds; recorte GeoTIFF real a 0,20 m |
| Vuelo / fecha | https://catalogodatos.gub.uy/dataset/ide-vuelo-fotogrametrico-minas-diciembre-2025 | Se conserva precisión de mes (2025-12); no se inventa día de captura. Ficha y API CKAN comprobadas: licencia odc-uy, Licencia de DAG de Uruguay; atribución IDE y fecha preservadas |
| Modelo FLAIR | https://huggingface.co/IGNF/FLAIR-INC_rgb_12cl_resnet34-unet/tree/533aa8f000dd36f2d07279ae73e0263d5f23a976 | Etalab 2.0 en metadata oficial; atribuir IGN/FLAIR, origen, versión, cambios y fecha; no sugiere aval del IGN |
| Código FLAIR | https://github.com/IGNF/FLAIR-1 | Apache-2.0; implementación propia del adaptador con SMP, basada en arquitectura y documentación oficial |
| Mapa de calles | https://www.openstreetmap.org/copyright | Atribución visible OSM; para despliegue de alto tráfico contratar/proveer teselas adecuadas, sin descarga masiva de teselas públicas |
| MinIO | https://github.com/minio/minio/tree/7aac2a2c5b7c882e68c1ce017d8256be2feea27f | AGPL-3.0, fuente oficial archivada; imagen propia fijada a commit, licencia incluida en /licenses. No hay imagen pública oficial descargable en los registros probados |

Hashes catastrales: parcelario `5e39557b6da671a957bfd8c0beb61a5cb48ca2a7728b72711172c9243f694765`; suelo `af172e82bb8c8ad1d9bf1e354e565f11dce3123eaa7d73b57f2f02f6cb1234ac`. Cada nueva adquisición genera su propio manifiesto: no se fijan totales en el código.

Los timestamps feat_date_gvol, adquisición y publicación no se presentan como fecha legal de actualización catastral. Se conservan las propiedades originales. El WFS de categorías consultado no incluye el texto de la norma en su esquema: **no se inventa origen normativo**. Se muestra categoria y fuente; vinculación con instrumentos normativos oficiales requiere investigación adicional. Una categoría rural potencialmente transformable no se convierte en suburbana.

## Fuentes complementarias comprobadas y limitaciones

Comprobaciones reproducibles: scripts/inspect_historical.py e informe artifacts/official-source-checks.json. Todas las fichas consultadas respondieron 200 el 2026-10-31 UTC:

- [DNC shapes](https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-shapes-del-parcelario-rural-y-urbano): recursos SHP de urbano/rural/localidades, licencia DAG de Uruguay (odc-uy). Fecha de metadata no se interpreta como fecha legal de actualización del contenido.
- [DNC alfanumérico](https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-padrones-urbanos-y-rurales): odc-uy, recursos fechados individualmente; no asumir actualidad por metadata_modified.
- [SNIG](https://web.snig.gub.uy/arcgisserver/rest/services/Uruguay/SNIG_Catastro/MapServer/1): Catastro Rural y Urbano, EPSG:32721, máximo 1.000 registros; claves Codigo, codDepto, codLocCat, NroPadron. No se mezcló con IDE.
- [MGAP](https://mapas.mgap.gub.uy/arcgis/rest/services/SNIA_Temas/ParcelasCatastrales/MapServer/1): urbano, EPSG:32721, máximo 2.000 registros.
- [MVOT](https://sit.mvot.gub.uy/arcgis/rest/services/07_EXTERNO/CATASTRO/MapServer/3): urbano, EPSG:5382, máximo 2.000; atribuye a DNC. Los CRS distintos se conservan y no se presumen equivalentes.
- [WMS histórico IDE](https://mapas.ide.uy/geoservicios/WMS/WMS_Uruguay_IDEuy_Ortofotos): capas nacional/urbana/infrarrojas 2017–2018, 1966 y UTE 2003/IM 2007. El alias ORTOFOTOS_2019 tiene título 2017–2018: no se presenta 2019 como año de vuelo. La URL del catálogo devuelve capabilities aun ante GetMap; se utiliza su servicio anunciado, geoserver-raster/ortofotos/wms, capa ortofotos:ortofoto_urbana. Se comprobó una tesela PNG real de Minas. La capa histórica es visual; no se le asigna resolución o captura exacta por parcela ni se usa para inferencia.

La licencia del vuelo Minas 2025 está explícita en la ficha CKAN (odc-uy). La licencia DAG también está en los datasets originales DNC; debe conservarse atribución y comprobarse la correspondencia de cada redistribución IDE antes de publicar sus capas fuera de la plataforma. Disponibilidad pública de un servicio no demuestra derechos irrestrictos sobre todos los productos. Los boilerplates no publican licencia de proyecto explícita; no se copiaron logos. Ver ARQUITECTURA_SAMPLE.md y THIRD_PARTY.md. La incorporación de fuentes alternativas y cobertura de otras localidades requiere validación específica; no se combinan silenciosamente con la versión catastral ya importada.
