"""Toggle only local preview in the private root .env, preserving login/captcha/2FA."""

import argparse
import subprocess
from pathlib import Path
from dotenv import set_key, dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["on", "off"])
parser.add_argument("--restart", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
config = root / ".env"
if not config.is_file():
    raise SystemExit("Inicialice primero la configuración privada local con scripts/init_local.py.")
if dotenv_values(config).get("FLASK_CONFIG") != "development":
    raise SystemExit("Esta herramienta solo administra el entorno local con FLASK_CONFIG=development.")
set_key(str(config), "DEV_AUTH_BYPASS", "true" if args.mode == "on" else "false")
print("Entrada directa local ACTIVADA." if args.mode == "on" else "Login, captcha y doble factor ACTIVADOS.")
if args.restart:
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.dev.yml",
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "120",
        ],
        cwd=root,
        check=True,
    )
else:
    print("Reinicie los servicios para aplicar la configuración. Use --restart para hacerlo ahora.")
