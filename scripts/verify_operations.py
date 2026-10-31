"""Restore a backup and verify least-privilege bootstrap in disposable databases only."""

import argparse
import json
import os
import secrets
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
import _bootstrap
import psycopg
from psycopg import sql
from flask_migrate import upgrade
from sqlalchemy.engine import make_url
from app import create_app
from app.extensions import db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    backup = args.backup.resolve(strict=True)
    app = create_app()
    if app.config["PRODUCTION"]:
        raise SystemExit("Ejecute esta comprobación únicamente sobre el entorno local de desarrollo.")
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    suffix = uuid.uuid4().hex[:12]
    restore_name, app_name, role = (
        f"geopadrones_restore_{suffix}",
        f"geopadrones_ops_{suffix}",
        f"geopadrones_ops_{suffix}",
    )
    remote = f"/tmp/geopadrones-restore-{suffix}.dump"
    connection_args = dict(
        host=url.host, port=url.port or 5432, user=url.username, password=url.password, connect_timeout=5
    )
    admin = psycopg.connect(**connection_args, dbname="postgres", autocommit=True)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "backup": backup.name}
    operations_app = None
    try:
        for name in (restore_name, app_name):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        subprocess.run(
            ["docker", "compose", "cp", str(backup), f"postgres-postgis:{remote}"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres-postgis",
                "sh",
                "-c",
                'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$1" "$2"',
                "sh",
                restore_name,
                remote,
            ],
            check=True,
            capture_output=True,
        )
        with psycopg.connect(**connection_args, dbname=restore_name) as restored:
            report["restore"] = dict(
                zip(
                    ("parcels", "localities", "land_use_categories", "invalid_geometries"),
                    restored.execute(
                        "SELECT (SELECT count(*) FROM parcels), (SELECT count(*) FROM localities), "
                        "(SELECT count(*) FROM land_use_categories), (SELECT count(*) FROM parcels WHERE NOT ST_IsValid(geom))"
                    ).fetchone(),
                )
            )
            report["restore"]["migration"] = restored.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        # Reuse the actual entrypoint script against a fresh DB with PostGIS preinstalled by the owner.
        with psycopg.connect(**connection_args, dbname=app_name, autocommit=True) as connection:
            connection.execute("CREATE EXTENSION postgis")
        password = secrets.token_urlsafe(36)
        child_env = {
            **os.environ,
            "DATABASE_APP_USER": role,
            "DATABASE_APP_PASSWORD": password,
            "POSTGRES_DB": app_name,
        }
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "-e",
                "DATABASE_APP_USER",
                "-e",
                "DATABASE_APP_PASSWORD",
                "-e",
                "POSTGRES_DB",
                "postgres-postgis",
                "sh",
            ],
            input=(_bootstrap.ROOT / "infra/postgres/90-app-role.sh").read_bytes(),
            env=child_env,
            check=True,
            capture_output=True,
        )
        operations_app = create_app(
            "testing",
            {
                "PRODUCTION": True,
                "SQLALCHEMY_DATABASE_URI": url.set(
                    database=app_name, username=role, password=password
                ).render_as_string(hide_password=False),
            },
        )
        with operations_app.app_context():
            upgrade(directory=str(_bootstrap.ROOT / "backend/migrations"))
            flags = db.session.execute(
                db.text("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user")
            ).one()
            assert not any(flags)
            report["application_role"] = dict(
                superuser=flags[0], createdb=flags[1], createrole=flags[2], migrations="passed"
            )
        client = operations_app.test_client()
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 200
        assert client.get("/api/v1/auth/csrf").status_code in (301, 302, 307, 308)
        report["production_http"] = {"health": 200, "readiness": 200, "application_https_redirect": True}
        try:
            create_app(
                "testing",
                {
                    "PRODUCTION": True,
                    "SQLALCHEMY_DATABASE_URI": url.set(database=app_name).render_as_string(
                        hide_password=False
                    ),
                },
            )
        except RuntimeError as error:
            assert "sin SUPERUSER" in str(error)
            report["privileged_role_rejected"] = True
        else:
            raise AssertionError("Production accepted a privileged database role")
    finally:
        if operations_app:
            with operations_app.app_context():
                db.session.remove()
                db.engine.dispose()
        for name in (restore_name, app_name):
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        admin.close()
        subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres-postgis", "rm", "-f", "--", remote],
            check=True,
            capture_output=True,
        )
    report["temporary_resources_removed"] = True
    destination = _bootstrap.ROOT / "artifacts/tests/operations.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
