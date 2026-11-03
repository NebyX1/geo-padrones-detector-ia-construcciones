"""Measure UNet++ on a real local ortho; reports speed, not accuracy."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import torch

from app import create_app
from app.services.imagery import read_rgb
from app.services.inference import load_model, segment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--raster", default="data/raw/minas-sector.tif")
    parser.add_argument("--manifest", default="data/models/unetpp.manifest.json")
    parser.add_argument("--output", default="artifacts/unet-benchmark")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("Se requiere al menos una repetición.")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA no está disponible en este entorno.")
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raster = Path(args.raster)
    with create_app().app_context():
        rgb, valid, affine, crs = read_rgb(raster.read_bytes())
        started = time.perf_counter()
        model = load_model(
            str(manifest_path.parent / manifest["filename"]),
            manifest["sha256"],
            args.device,
            "unetpp_efficientnet_b4",
        )
        if args.device == "cuda":
            torch.cuda.synchronize()
        load_seconds = time.perf_counter() - started
        segment(rgb[:, :512, :512], model, args.device, architecture="unetpp_efficientnet_b4")
        if args.device == "cuda":
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        times = []
        for _ in range(args.runs):
            started = time.perf_counter()
            probability = segment(rgb, model, args.device, architecture="unetpp_efficientnet_b4")
            if args.device == "cuda":
                torch.cuda.synchronize()
            times.append(time.perf_counter() - started)
        np.save(destination / f"{args.device}-probability.npy", probability)
        report = dict(
            device=args.device,
            hardware=torch.cuda.get_device_name() if args.device == "cuda" else "CPU, 2 hilos PyTorch",
            torch=torch.__version__,
            cuda_toolkit=torch.version.cuda,
            model_sha256=manifest["sha256"],
            image_sha256=hashlib.sha256(raster.read_bytes()).hexdigest(),
            sample=str(raster),
            image_pixels=list(valid.shape),
            image_crs=str(crs),
            resolution_m=[abs(affine.a), abs(affine.e)],
            valid_pixels=int(valid.sum()),
            window=512,
            overlap=128,
            load_seconds=load_seconds,
            inference_seconds=times,
            median_seconds=float(np.median(times)),
            building_pixels_threshold_0_5=int(((probability >= 0.5) & valid).sum()),
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated() if args.device == "cuda" else None,
            peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved() if args.device == "cuda" else None,
            accuracy="not measured; no local ground-truth labels",
        )
        (destination / f"{args.device}-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
