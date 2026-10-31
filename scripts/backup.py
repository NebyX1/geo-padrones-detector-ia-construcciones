"""Binary-safe local Postgres backup without exposing passwords to process arguments."""

import argparse
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--directory", default="artifacts/backups")
args = parser.parse_args()
target = Path(args.directory).resolve()
target.mkdir(parents=True, exist_ok=True)
name = "geopadrones-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".dump"
remote = "/tmp/geopadrones-" + uuid.uuid4().hex + ".dump"
subprocess.run(
    [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres-postgis",
        "sh",
        "-c",
        'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$1"',
        "sh",
        remote,
    ],
    check=True,
)
subprocess.run(["docker", "compose", "cp", f"postgres-postgis:{remote}", str(target / name)], check=True)
subprocess.run(["docker", "compose", "exec", "-T", "postgres-postgis", "rm", "--", remote], check=True)
print(f"Backup creado: {target / name}")
