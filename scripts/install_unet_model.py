"""Install the pinned WHU checkpoint without replacing the FLAIR model or its manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import requests

MODEL = "giswqs/whu-building-unetplusplus-efficientnet-b4"
REVISION = "09df9efd323bbd3d56b98b4857129eb9b5baa2d3"
SHA256 = "922af7c96c0dc44256ab8b4d1a071f2151e0a921c997af80b55bb766bcc30dc6"
FILENAME = f"{REVISION}-whu-unetplusplus-efficientnet-b4.pth"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def install(directory, source=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    temporary = directory / (FILENAME + ".part")
    if not target.is_file() or digest(target) != SHA256:
        try:
            if source:
                shutil.copyfile(source, temporary)
            else:
                with requests.get(
                    f"https://huggingface.co/{MODEL}/resolve/{REVISION}/model.pth",
                    stream=True,
                    timeout=(15, 150),
                ) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                            if output.tell() > 100_000_000:
                                raise ValueError("El checkpoint supera el tamaño permitido.")
            if digest(temporary) != SHA256:
                raise ValueError("El hash del modelo no coincide con la versión verificada.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    manifest = dict(
        model_id=MODEL,
        revision=REVISION,
        filename=FILENAME,
        sha256=SHA256,
        license="apache-2.0",
        source=f"https://huggingface.co/{MODEL}/tree/{REVISION}",
        architecture="unetpp_efficientnet_b4",
        input_channels=3,
        output_channels=2,
        building_channel=1,
        input_normalization="RGB / 255",
        training_resolution_m=0.3,
        local_validation="PENDING",
    )
    path = directory / "unetpp.manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Modelo verificado: {target}; manifiesto: {path}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="data/models")
    parser.add_argument("--source", help="Copia local ya descargada del checkpoint fijado")
    args = parser.parse_args()
    install(args.directory, args.source)
