"""Review evidence is private and always tied to the immutable analysis result."""

import hashlib
import io
import json
from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user
from geoalchemy2.shape import to_shape
from sqlalchemy import select, func
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models import (
    ReviewCase,
    ReviewAttachment,
    Parcel,
    ParcelAnalysisResult,
    BuildingFootprint,
    ImageryScene,
    AnalysisRun,
    AIModelVersion,
    ReviewAction,
)
from ..services.reviews import original_geometry
from ..services.geospatial import reproject
from ..services.storage import storage
from ..utils.security import require, audit

bp = Blueprint("review_evidence", __name__)


@bp.get("/reviews/<identifier>")
@require("read")
def detail(identifier):
    case = db.get_or_404(ReviewCase, identifier)
    result = db.session.get(ParcelAnalysisResult, case.result_id)
    parcel = db.session.get(Parcel, result.parcel_id)
    geometry = original_geometry(result)
    run = db.session.get(AnalysisRun, result.run_id)
    scene = db.session.get(ImageryScene, run.scene_id)
    model = db.session.get(AIModelVersion, run.model_version_id)
    return jsonify(
        parcel={
            "type": "Feature",
            "geometry": json.loads(db.session.scalar(select(func.ST_AsGeoJSON(geometry)))),
            "properties": {
                "id": parcel.id,
                "padron": parcel.padron,
                "state": result.state,
                "m2_parcela": reproject(to_shape(geometry)).area,
                "m2_huella_detectada": result.m2_huella_detectada,
            },
        },
        evidence={
            "captured_at": scene.captured_at,
            "scene_id": scene.id,
            "model_id": model.id,
            "revision": model.revision,
        },
        footprints=[
            json.loads(g)
            for g in db.session.scalars(
                select(func.ST_AsGeoJSON(BuildingFootprint.geom)).where(
                    BuildingFootprint.result_id == result.id
                )
            )
        ],
        actions=[
            {
                "status": a.status,
                "state": a.state,
                "observations": a.observations,
                "version": a.version,
                "created_at": a.created_at,
            }
            for a in db.session.scalars(
                select(ReviewAction)
                .where(ReviewAction.case_id == case.id)
                .order_by(ReviewAction.version.desc())
            )
        ],
        needs_reanalysis=case.needs_reanalysis,
    )


@bp.route("/reviews/<identifier>/attachments", methods=["GET", "POST"])
@require("read")
def attachments(identifier):
    db.get_or_404(ReviewCase, identifier)
    if request.method == "POST":
        return require("review")(lambda: upload_attachment(identifier))()
    return jsonify(
        items=[
            {
                "id": a.id,
                "filename": a.filename,
                "size": a.size,
                "sha256": a.sha256,
                "created_at": a.created_at,
                "user_id": a.user_id,
            }
            for a in db.session.scalars(
                select(ReviewAttachment)
                .where(ReviewAttachment.case_id == identifier)
                .order_by(ReviewAttachment.created_at.desc())
            )
        ]
    )


def upload_attachment(identifier):
    file = request.files.get("file")
    if not file or request.form.get("authorized") != "true":
        abort(422, "Seleccione un archivo y confirme que dispone de autorización para adjuntarlo.")
    raw = file.read(8 * 1024 * 1024 + 1)
    if not raw or len(raw) > 8 * 1024 * 1024:
        abort(422, "El adjunto debe ocupar entre 1 byte y 8 MB.")
    if raw.startswith(b"%PDF-"):
        mime, extension = "application/pdf", ".pdf"
    else:
        try:
            with Image.open(io.BytesIO(raw)) as picture:
                if picture.format not in {"PNG", "JPEG"} or picture.width * picture.height > 16000000:
                    raise ValueError()
                extension, mime = (".png", "image/png") if picture.format == "PNG" else (".jpg", "image/jpeg")
                picture.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            abort(422, "Solo se admiten PNG/JPEG válidos y PDF; no archivos ejecutables ni SVG.")
    name = secure_filename(file.filename or "evidencia")[:180] or "evidencia"
    if not name.lower().endswith(extension):
        name += extension
    attachment = ReviewAttachment(
        case_id=identifier,
        user_id=current_user.id,
        filename=name,
        sha256=hashlib.sha256(raw).hexdigest(),
        mime=mime,
        size=len(raw),
        object_key="",
    )
    db.session.add(attachment)
    db.session.flush()
    attachment.object_key = storage().put(
        f"review-evidence/{identifier}/{attachment.id}{extension}", raw, mime
    )
    audit("REVIEW_ATTACHMENT", identifier, {"attachment_id": attachment.id, "sha256": attachment.sha256})
    db.session.commit()
    return jsonify(id=attachment.id, filename=name), 201


@bp.get("/reviews/<identifier>/attachments/<attachment_id>")
@require("read")
def download(identifier, attachment_id):
    attachment = db.get_or_404(ReviewAttachment, attachment_id)
    if attachment.case_id != identifier:
        abort(404)
    audit("REVIEW_ATTACHMENT_DOWNLOAD", identifier, {"attachment_id": attachment.id})
    db.session.commit()
    # Always download untrusted evidence; do not render PDF or active content in the app origin.
    return send_file(
        io.BytesIO(storage().get(attachment.object_key)),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=attachment.filename,
    )


@bp.post("/reviews/<identifier>/request-analysis")
@require("review")
def request_analysis(identifier):
    case = db.session.execute(
        select(ReviewCase).where(ReviewCase.id == identifier).with_for_update()
    ).scalar_one_or_none()
    if not case:
        abort(404)
    reason = (request.get_json() or {}).get("observations")
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 4000:
        abort(422, "Indique el motivo de la nueva inferencia.")
    if not case.needs_reanalysis:
        case.needs_reanalysis = True
        audit("REANALYSIS_REQUESTED", case.id, {"observations": reason.strip(), "result_id": case.result_id})
    db.session.commit()
    return jsonify(message="Solicitud registrada para el analista; aún no se ejecutó una nueva inferencia.")
