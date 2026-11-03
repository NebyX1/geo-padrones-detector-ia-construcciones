# Fuentes y control de reproducibilidad

Este inventario registra la configuración y los hashes observados en la instalación original. Cada nuevo agente debe verificar accesibilidad, licencia, hash y fecha; los recursos oficiales pueden cambiar. Esta hoja no contiene datos catastrales ni credenciales.

## Modelos

| Modelo | Revisión fijada | SHA-256 de pesos | Referencia y licencia |
| --- | --- | --- | --- |
| `IGNF/FLAIR-INC_rgb_12cl_resnet34-unet` | `533aa8f000dd36f2d07279ae73e0263d5f23a976` | `b7900cb1cf34f137c2f86a002dc99bca402d5a0139f8ad6253589ece416a511f` | [Repositorio y revisión](https://huggingface.co/IGNF/FLAIR-INC_rgb_12cl_resnet34-unet/tree/533aa8f000dd36f2d07279ae73e0263d5f23a976), Etalab 2.0 según metadatos del modelo. |
| `giswqs/whu-building-unetplusplus-efficientnet-b4` | `09df9efd323bbd3d56b98b4857129eb9b5baa2d3` | `922af7c96c0dc44256ab8b4d1a071f2151e0a921c997af80b55bb766bcc30dc6` | [Repositorio y revisión](https://huggingface.co/giswqs/whu-building-unetplusplus-efficientnet-b4/tree/09df9efd323bbd3d56b98b4857129eb9b5baa2d3), Apache 2.0 según el manifiesto instalado. |

FLAIR usa una U-Net/ResNet-34 con 19 canales reales de salida; el canal 0 corresponde a construcción. UNet++/EfficientNet-B4 usa dos clases, construcción en el canal 1 y RGB dividido por 255. Consultar `backend/app/services/inference.py`, `docs/decisions/ADR-002-flair-checkpoint.md` y `docs/UNET_GPU.md`. Los scripts verifican el hash antes de registrar o cargar los pesos. No existe todavía una medición de precisión local representativa en Lavalleja.

## ZIP de la Dirección Nacional de Catastro

El [catálogo oficial de padrones](https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-padrones-urbanos-y-rurales) y el [catálogo de parcelario SHP](https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-shapes-del-parcelario-rural-y-urbano) indican la Licencia de Datos Abiertos de Gobierno de Uruguay. Revise las condiciones vigentes antes de redistribuir; la disponibilidad no elimina las obligaciones de atribución.

| Nombre esperado en `data/catastro/` | Origen directo | SHA-256 original |
| --- | --- | --- |
| `datosabiertosdnc2026-10.zip` | [DNC: alfanumérico 10/2026](https://catalogodatos.gub.uy/dataset/a0ff3085-b886-454b-8e8b-88f59bd980cc/resource/0bbc79c5-3000-4ef3-9eb2-e7af7cdc74af/download/datosabiertosdnc2026-10.zip) | `2862a3dcbdb1ae94cec58c295cd9a7f0e4d1ca483ae58a28d3d5498e5a99c83c` |
| `paisurbano_shp.zip` | [DNC: total país urbano](https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/3d211675-14a6-4e69-bc0b-6cc549060633/download/paisurbano_shp.zip) | `7c0a7028f4aa9a41f9552043719c873d888e459cb0731a349b8ed1f914c04026` |
| `paisrural_shp.zip` | [DNC: total país rural](https://catalogodatos.gub.uy/dataset/9e0dc092-a669-4697-b3ba-88808165c902/resource/2073596d-f122-4030-9eb4-eaca1cdf1e9c/download/paisrural_shp.zip) | `36de017c4254d11c721d16ee5407bb9194e10d2370e2cf7a4a7d38abbe5ef574` |

Los enlaces SHP pueden entregar una versión más reciente bajo el mismo nombre; si el hash difiere, no la renombre ni describa como la instantánea original. Si se necesita reproducción histórica, obtenga una copia de esos bytes desde una fuente archivada o del responsable original, manteniendo la licencia. Los nombres no aseguran ni que la fecha del contenido sea exacta ni que se trate de una declaración jurídica vigente.

Para comprobar SHA-256, por ejemplo:

```powershell
Get-FileHash -Algorithm SHA256 data/catastro/datosabiertosdnc2026-10.zip
Get-FileHash -Algorithm SHA256 data/catastro/paisurbano_shp.zip
Get-FileHash -Algorithm SHA256 data/catastro/paisrural_shp.zip
```

```bash
sha256sum data/catastro/datosabiertosdnc2026-10.zip data/catastro/paisurbano_shp.zip data/catastro/paisrural_shp.zip
```

El diccionario de campos de DNC está disponible en los [metadatos publicados](https://catalogodatos.gub.uy/dataset/a0ff3085-b886-454b-8e8b-88f59bd980cc/resource/fa6614bb-1cf1-469f-b7f2-3d81b81bd5d5/download/metadatos-dnc-2020-12-.pdf). El CSV rural no informa construcción. El generador conserva valores originales en propiedad horizontal, evita inventar una escala y señala la contradicción hallada en el padrón Minas 9668.

## Capas e imágenes IDE

| Uso | Fuente | Huella de la captura anterior |
| --- | --- | --- |
| Parcelario urbano Lavalleja | [WFS IDE](https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs), `ideuy:parcelariourbano`, filtro `nomdepto='LAVALLEJA'` | `data/raw/lavalleja.ndjson`: `5e39557b6da671a957bfd8c0beb61a5cb48ca2a7728b72711172c9243f694765` |
| Categoría territorial | Mismo WFS, `ideuy:uyla_dir_categsuelo` | `data/raw/land-use.ndjson`: `af172e82bb8c8ad1d9bf1e354e565f11dce3123eaa7d73b57f2f02f6cb1234ac`; adquisición 31/10/2026 |
| Ortofoto análisis | [WCS IDE](https://mapas.ide.uy/geoserver-raster/ortofotos/wcs), `ortofotos__minas_lavalleja_mosaico_2025_geotiff` | [Ficha del vuelo Minas, diciembre 2025](https://catalogodatos.gub.uy/dataset/ide-vuelo-fotogrametrico-minas-diciembre-2025). IDE indica licencia DAG Uruguay; se consulta por recortes. |
| Mapa de calles | [OpenStreetMap](https://www.openstreetmap.org/copyright) | Mantener atribución visible y respetar condiciones del proveedor de teselas. |

La escena Minas tiene 5 cm de píxel nativo; la inferencia usa 20 cm. Su CRS métrico de trabajo es EPSG:5382; geometrías GeoJSON se entregan en WGS 84. La capa territorial no contiene necesariamente el instrumento jurídico que la respalda: su superposición es informativa. Una capa «potencialmente transformable a suburbano» no se convierte por ello en suburbana. El WFS y la escena pueden cambiar o dejar de responder; conserve sus manifiestos de captura cuando importe datos.

Los hashes anteriores se refieren a los **archivos NDJSON exactos**, no al WFS como servicio. La API o el orden de entidades pueden cambiar aunque la información aparente sea similar. Para coincidencia exacta conserve los NDJSON originales y sus manifiestos; no suplante el hash en un manifiesto. El GeoJSON preparado en la instalación original tenía SHA-256 `ed5998e96e95810a934a57b3b1d4a62efea1b1a5b2eccdedeb9ed527bb5d9e14`, pero el generador incluye `generado_utc` y la ruta de la capa, por lo que regenerarlo no conserva necesariamente ese hash. Una comparación previa queda vinculada al hash original de la referencia.

## Componentes operativos y licencias

Los archivos `docker-compose*.yml`, Dockerfiles y lockfiles identifican versiones y dependencias del software. Docker descarga imágenes base y dependencias durante el build; un tag o un registro no constituye una garantía de reconstrucción byte a byte. Para reproducción fuerte conserve también digests de imágenes, versiones de paquetes, la versión de Docker/host y artefactos permitidos. El contenedor MinIO se construye desde [fuente oficial fijada](https://github.com/minio/minio/tree/7aac2a2c5b7c882e68c1ce017d8256be2feea27f), AGPL-3.0; examine sus obligaciones. Consulte `docs/THIRD_PARTY.md` o `THIRD_PARTY.md` si están presentes y `docs/data-sources/PROVENANCE.md` para las licencias y atribuciones verificadas.

Estado y resultados de la instalación, fotografías servidas por terceros, firmas, usuarios, contraseñas y claves, datos de revisiones y contenidos de los volúmenes **no se reconstruyen** con el repositorio ni con estos enlaces. Solo una restauración autorizada y consistente de todos esos componentes podría reproducirlos. Revisar el vínculo normativo de categorías y la precisión local es una tarea pendiente, no un paso que pueda darse por cumplido mediante instalación.
