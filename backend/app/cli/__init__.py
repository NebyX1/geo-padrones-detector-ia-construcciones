import json
from pathlib import Path
import click
from sqlalchemy import select
from ..extensions import db
from ..models import User, AIModelVersion, Job
from ..utils.security import audit


def register_commands(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Nombre")
    def create_admin(email, name):
        """Primer administrador. La contraseña se solicita oculta, nunca como argumento."""
        from email_validator import validate_email, EmailNotValidError

        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError as exc:
            raise click.ClickException(str(exc))
        password = click.prompt("Contraseña", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Use al menos 12 caracteres.")
        if db.session.execute(select(User).where(User.email == email)).scalar_one_or_none():
            raise click.ClickException("La cuenta ya existe.")
        user = User(email=email, name=name, role="superadmin")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        audit("BOOTSTRAP_ADMIN", user.id, user_id=user.id)
        db.session.commit()
        click.echo("Administrador creado.")

    @app.cli.command("init-bucket")
    def init_bucket():
        from ..services.storage import storage

        storage().init()
        click.echo("Almacenamiento privado listo.")

    @app.cli.command("register-imagery")
    def register_imagery():
        from ..services.imagery import register_minas

        click.echo(register_minas().id)

    @app.cli.command("register-model")
    @click.argument("manifest", type=click.Path(exists=True))
    def register_model(manifest):
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        import hashlib

        filename = app.config["MODEL_DIR"] / data["filename"]
        if filename.parent.resolve() != app.config["MODEL_DIR"] or not filename.is_file():
            raise click.ClickException("Modelo fuera del directorio autorizado o inexistente.")
        if hashlib.sha256(filename.read_bytes()).hexdigest() != data["sha256"]:
            raise click.ClickException("Hash del modelo incorrecto.")
        row = db.session.execute(
            select(AIModelVersion).where(
                AIModelVersion.model_id == data["model_id"], AIModelVersion.revision == data["revision"]
            )
        ).scalar_one_or_none()
        if row is None:
            row = AIModelVersion(
                model_id=data["model_id"],
                revision=data["revision"],
                sha256=data["sha256"],
                filename=data["filename"],
                license=data["license"],
                metadata_json=data,
            )
            db.session.add(row)
            db.session.commit()
        click.echo(row.id)

    @app.cli.command("dispatch-pending")
    def dispatch_pending():
        from ..services.queue import dispatch

        for job in db.session.execute(
            select(Job).where(Job.status == "PENDING").order_by(Job.created_at).limit(100)
        ).scalars():
            dispatch(job)
        click.echo("Despacho reintentado.")

    @app.cli.command("recover-job")
    @click.argument("identifier")
    def recover_job(identifier):
        """Requeue a failed RQ job after correcting its cause; never duplicate a running task."""
        from ..services.queue import redis_connection
        from rq.job import Job as RQJob

        job = db.session.get(Job, identifier)
        if not job or job.status not in {"FAILED", "RUNNING"}:
            raise click.ClickException("Trabajo no recuperable.")
        rq_job = RQJob.fetch(identifier, connection=redis_connection())
        if rq_job.get_status(refresh=True) not in {"failed", "stopped"}:
            raise click.ClickException("RQ todavía no considera terminado el trabajo; espere su timeout.")
        rq_job.requeue()
        job.status, job.error = "QUEUED", None
        db.session.commit()
        click.echo("Trabajo encolado nuevamente.")
