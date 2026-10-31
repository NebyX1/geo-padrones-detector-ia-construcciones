from flask import Blueprint, jsonify
from sqlalchemy import select
from ..extensions import db
from ..models import SystemSetting
from ..utils.security import require

bp = Blueprint("preferences", __name__)


@bp.get("/preferences")
@require("read")
def preferences():
    return jsonify(
        settings={
            s.key: s.value
            for s in db.session.execute(
                select(SystemSetting).where(SystemSetting.key.in_(["theme_colors", "default_thresholds"]))
            ).scalars()
        }
    )
