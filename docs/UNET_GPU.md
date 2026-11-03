# UNet++ y procesador de análisis

GeoPadrones admite el modelo de construcciones [UNet++ / EfficientNet-B4](https://huggingface.co/giswqs/whu-building-unetplusplus-efficientnet-b4/tree/09df9efd323bbd3d56b98b4857129eb9b5baa2d3) junto al modelo FLAIR existente. La revisión de UNet++ está fijada y su SHA-256 se verifica antes de cargar los pesos. El modelo recibe RGB normalizado entre 0 y 1 y produce probabilidades de edificio; el recorte por parcela y el cálculo de m² siguen a cargo de GeoPadrones. Sus resultados todavía no tienen precisión local validada.

Para descargar los pesos sin sobrescribir FLAIR, construir la versión de la aplicación con el worker GPU y registrar el modelo cuando Docker vuelva a estar operativo:

```powershell
.\.venv\Scripts\python.exe scripts/install_unet_model.py
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml exec backend flask register-model /data/models/unetpp.manifest.json
```

El directorio `data/models` se monta en los contenedores en `/data/models`. El selector de modelo en los formularios de análisis individual y múltiple permite elegir FLAIR o UNet++ registrado y habilitado. La selección no reemplaza resultados históricos.

Cada análisis permite elegir **CPU** o **GPU NVIDIA**; se recuerda la preferencia por usuario en ese navegador. La GPU es la del servidor que ejecuta el worker, no necesariamente la de la computadora que abre la web. CPU es la opción inicial. Elegir GPU sin que esté disponible hace fallar el trabajo con un mensaje: no se simula la GPU ni se cambia a CPU silenciosamente. Para habilitar el worker opcional con CUDA, ver [Docker](deployment/DOCKER.md).

La medición de velocidad puede repetirse con `scripts/benchmark_unetpp.py --device cpu` y, en un entorno Python con PyTorch CUDA y controlador NVIDIA, `--device cuda`. Se requieren la ortofoto local `data/raw/minas-sector.tif` y el manifiesto `data/models/unetpp.manifest.json`. Las pruebas guardan tiempos, huella del archivo de imagen y modelo, máscaras de probabilidad y memoria GPU en `artifacts/unet-benchmark`. La velocidad medida no demuestra precisión: la evaluación local con referencias independientes sigue pendiente.

## Medición local del 2 de noviembre de 2026

En Windows, con PyTorch 2.6.0+cu124, se analizó el mismo recorte real de Minas de 1.300 × 1.300 píxeles, a 20 cm por píxel. Se usaron 16 ventanas de 512 × 512 píxeles, dos hilos de CPU, una ejecución de calentamiento y tres pasadas cronometradas. La mediana fue **13,323 segundos en CPU** y **0,972 segundos en una NVIDIA GeForce RTX 3050 de 8 GB**: la GPU fue unas 13,7 veces más rápida para esta inferencia. La memoria máxima reservada por PyTorch en la GPU fue aproximadamente 558 MiB. La carga inicial del modelo en GPU demoró 3,61 segundos.

Los tiempos miden únicamente la inferencia sobre la imagen ya cargada; no incluyen descarga de imagen, cola, almacenamiento ni conversión de la máscara a polígonos. Las máscaras de CPU y GPU coincidieron en el 99,9919 % de los píxeles (137 diferencias de 1.690.000). Esta coincidencia compara ambos procesadores, no mide aciertos frente a la realidad. Los resultados y configuraciones están en `artifacts/unet-benchmark-actual/`. La comparación se hizo con Python nativo en Windows. Posteriormente, un contenedor temporal sin red también ejecutó UNet++ con CUDA sobre ese recorte; la primera pasada tardó 1,957 segundos. Se verificó además el procesamiento completo por la cola en una base y un bucket de pruebas aislados.
