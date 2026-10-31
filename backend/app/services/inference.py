"""Imported only by worker/benchmark. API processes do not import torch."""

import hashlib
from functools import lru_cache
from pathlib import Path
import numpy as np
from rasterio.features import shapes
from shapely.geometry import shape
from shapely import union_all

MEAN = np.array([105.08, 110.87, 101.82], dtype=np.float32)[:, None, None]
STD = np.array([52.17, 45.38, 44.00], dtype=np.float32)[:, None, None]


def normalize(rgb):
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("Se requieren tres canales RGB en orden CHW.")
    return (rgb.astype(np.float32) - MEAN) / STD


@lru_cache(maxsize=2)
def load_model(filename, expected_sha256, device="cpu"):
    import torch
    import segmentation_models_pytorch as smp

    path = Path(filename)
    if not path.is_file():
        raise ValueError("Modelo no disponible. Ejecute scripts/download_models.py y registre el manifiesto.")
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_sha256:
            raise ValueError("Integridad del checkpoint incorrecta.")
    torch.set_num_threads(2)
    # weights_only forbids unpickling arbitrary Python objects from downloaded checkpoints.
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    state = checkpoint.get("state_dict", checkpoint)
    # Published checkpoint may include a Lightning wrapper prefix.
    if any(k.startswith("model.seg_model.") for k in state):
        unexpected = [k for k in state if not k.startswith("model.seg_model.") and k != "criterion.weight"]
        if unexpected:
            raise ValueError("El checkpoint contiene parámetros de entrenamiento no reconocidos.")
        state = {
            k[len("model.seg_model.") :]: v for k, v in state.items() if k.startswith("model.seg_model.")
        }
    elif all(k.startswith("model.") for k in state):
        state = {k[6:]: v for k, v in state.items()}
    # The official repository name says 12cl, but these exact published weights have 19 logits.
    # Keep every logit in softmax; selecting or renormalizing only 12 changes probabilities.
    if state["segmentation_head.0.weight"].shape[0] != 19:
        raise ValueError("Cambió la cantidad de canales del checkpoint revisado: se esperaban 19.")
    model = smp.Unet(
        encoder_name="resnet34", encoder_weights=None, in_channels=3, classes=19, activation=None
    )
    model.load_state_dict(state, strict=True)
    model.eval().to(device)
    return model


def segment(rgb, model, device="cpu", window=512, overlap=128, callback=None):
    import torch

    if not 0 <= overlap < window or window % 32:
        raise ValueError("Ventana/solapamiento inválidos.")
    _, height, width = rgb.shape
    padded_h, padded_w = max(window, height), max(window, width)
    data = np.pad(normalize(rgb), ((0, 0), (0, padded_h - height), (0, padded_w - width)), mode="edge")
    stride = window - overlap
    ys = list(range(0, padded_h - window + 1, stride))
    xs = list(range(0, padded_w - window + 1, stride))
    if ys[-1] != padded_h - window:
        ys.append(padded_h - window)
    if xs[-1] != padded_w - window:
        xs.append(padded_w - window)
    # Blend overlapping probabilities with raised-cosine weights, including safe nonzero borders.
    weight = np.maximum(np.outer(np.hanning(window), np.hanning(window)), 0.01).astype(np.float32)
    probability = np.zeros((padded_h, padded_w), dtype=np.float32)
    total_weight = np.zeros_like(probability)
    for y in ys:
        for x in xs:
            if callback:
                callback()
            with torch.inference_mode():
                output = model(torch.from_numpy(data[:, y : y + window, x : x + window][None]).to(device))
                if output.shape[1] != 19:
                    raise ValueError("El checkpoint no devuelve los diecinueve canales verificados.")
                probs = torch.softmax(output, dim=1)[0]
                # Building is training label 1, zero-based output channel 0.
                building = (probs[0] * (probs.argmax(dim=0) == 0)).cpu().numpy()
            probability[y : y + window, x : x + window] += building * weight
            total_weight[y : y + window, x : x + window] += weight
    return (probability / total_weight)[:height, :width]


def vectorize(probability, valid, affine, threshold=0.5, min_object_area=2):
    binary = ((probability >= threshold) & valid).astype(np.uint8)
    buildings = [
        shape(geo) for geo, value in shapes(binary, mask=binary.astype(bool), transform=affine) if value == 1
    ]
    buildings = [g for g in buildings if g.area >= min_object_area]
    valid_polygons = [
        shape(geo)
        for geo, value in shapes(valid.astype(np.uint8), mask=valid, transform=affine)
        if value == 1
    ]
    coverage = union_all(valid_polygons)
    return buildings, coverage, binary
