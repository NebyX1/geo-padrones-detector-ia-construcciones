from flask import Blueprint, jsonify, request
from sqlalchemy import select, func
from ..extensions import db
from ..models import CleanupEntry
from ..services.analysis_cleanup import plan, public_plan, erase
from ..utils.security import require

bp = Blueprint("analysis_cleanup", __name__)


@bp.post("/analysis/cleanup/preview")
@require("purge")
def preview():
    return jsonify(public_plan(plan(request.get_json())))


@bp.post("/analysis/cleanup")
@require("purge")
def remove():
    counts = erase(request.get_json())
    return jsonify(
        deleted=counts, pending_cleanup=db.session.scalar(select(func.count()).select_from(CleanupEntry))
    )


@bp.get("/analysis/cleanup/status")
@require("purge")
def status():
    return jsonify(pending_cleanup=db.session.scalar(select(func.count()).select_from(CleanupEntry)))
