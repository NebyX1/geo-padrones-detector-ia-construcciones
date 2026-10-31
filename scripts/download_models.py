"""Download only the reviewed official checkpoint, fixed to an immutable revision."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

MODEL = "IGNF/FLAIR-INC_rgb_12cl_resnet34-unet"
REVISION = "533aa8f000dd36f2d07279ae73e0263d5f23a976"
FILENAME = "FLAIR-INC_rgb_12cl_resnet34-unet_weights.pth"


def download(directory, revision=REVISION):
    if len(revision) != 40 or not all(c in "0123456789abcdef" for c in revision):
        raise ValueError("Use una revisión Git completa, nunca main o latest.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    metadata = requests.get(
        f"https://huggingface.co/api/models/{MODEL}/revision/{revision}", params={"blobs": "true"}, timeout=60
    )
    metadata.raise_for_status()
    repo = metadata.json()
    if repo["sha"] != revision or repo.get("cardData", {}).get("license") != "etalab-2.0":
        raise ValueError("Revisión o licencia del modelo cambiaron; requiere revisión técnica.")
    file = next(f for f in repo["siblings"] if f["rfilename"] == FILENAME)
    expected = file.get("lfs", {}).get("sha256")
    if not expected:
        raise ValueError("No se obtuvo el SHA-256 LFS oficial del checkpoint.")
    target = directory / f"{revision}-{FILENAME}"
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        temp = target.with_suffix(".part")
        with requests.get(
            f"https://huggingface.co/{MODEL}/resolve/{revision}/{FILENAME}", stream=True, timeout=(15, 150)
        ) as response:
            response.raise_for_status()
            digest, total = hashlib.sha256(), 0
            with temp.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total > 150000000:
                        raise ValueError("Checkpoint supera el tamaño esperado.")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("SHA-256 del checkpoint incorrecto; no se habilitará.")
        temp.replace(target)
    manifest = dict(
        model_id=MODEL,
        revision=revision,
        filename=target.name,
        sha256=expected,
        license="etalab-2.0",
        source=f"https://huggingface.co/{MODEL}/tree/{revision}",
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        architecture="Unet/resnet34",
        model_card_classes=12,
        checkpoint_output_channels=19,
        building_channel=0,
        input_channels=3,
        training_resolution_m=0.2,
        mean=[105.08, 110.87, 101.82],
        std=[52.17, 45.38, 44.00],
        local_validation="PENDING",
    )
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="data/models")
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args()
    download(args.directory, args.revision)
