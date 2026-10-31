# ADR-002: inspeccionar el checkpoint, no inferir la salida por su nombre

La revisión oficial `533aa8f000dd36f2d07279ae73e0263d5f23a976` de IGNF/FLAIR-INC_rgb_12cl_resnet34-unet tiene SHA-256 `b7900cb1cf34f137c2f86a002dc99bca402d5a0139f8ad6253589ece416a511f`.

La inspección real con `torch.load(weights_only=True)` identificó un state_dict de Lightning con prefijo `model.seg_model.` y un tensor de salida `segmentation_head.0.weight` de forma **19 × 16 × 3 × 3**, aunque el nombre y la ficha dicen 12cl. Se descarta exclusivamente `criterion.weight` (estado del entrenamiento), se elimina el prefijo conocido y se exige carga estricta del resto. No se ejecuta pickle arbitrario.

La arquitectura operativa es SMP 0.3.4 Unet/ResNet34, RGB, **19 logits**, label building=1 en el esquema oficial y canal cero en el tensor. Softmax conserva los 19 canales; nunca se recorta a doce ni se transforma en una salida binaria. Se aplica argmax multiclase y umbral a la probabilidad de building, normalizando RGB 0–255 con medias [105.08,110.87,101.82] y desviaciones [52.17,45.38,44], sin dividir por 255.

El benchmark real prueba que los pesos cargan y generan resultados. Esto no demuestra precisión local: todavía requiere etiquetado independiente de al menos 200 padrones variados. Véase docs/validation/MODEL_REPORT.md.
