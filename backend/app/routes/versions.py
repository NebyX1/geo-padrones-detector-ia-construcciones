from flask import Blueprint, jsonify, request
from sqlalchemy import select, text
from ..extensions import db
from ..models import CadastralDatasetVersion
from ..utils.security import require

bp = Blueprint("versions", __name__)


@bp.get("/cadastral/versions")
@require("read")
def versions():
    rows = db.session.execute(
        select(CadastralDatasetVersion).order_by(CadastralDatasetVersion.created_at.desc()).limit(100)
    ).scalars()
    return jsonify(
        items=[
            dict(
                id=v.id,
                source=v.source,
                sha256=v.sha256,
                count=v.count,
                created_at=v.created_at,
                metadata=v.metadata_json,
            )
            for v in rows
        ]
    )


@bp.get("/cadastral/versions/<old_id>/differences/<new_id>")
@require("read")
def differences(old_id, new_id):
    db.get_or_404(CadastralDatasetVersion, old_id)
    db.get_or_404(CadastralDatasetVersion, new_id)
    offset = max(request.args.get("offset", 0, type=int), 0)
    rows = (
        db.session.execute(
            text("""WITH old AS (
        SELECT parcel_id,ST_UnaryUnion(ST_Collect(geom)) geom FROM parcel_geometries WHERE dataset_version_id=:old GROUP BY parcel_id),
        new AS (SELECT parcel_id,ST_UnaryUnion(ST_Collect(geom)) geom FROM parcel_geometries WHERE dataset_version_id=:new GROUP BY parcel_id)
        SELECT COALESCE(old.parcel_id,new.parcel_id) parcel_id,
          CASE WHEN old.parcel_id IS NULL THEN 'AGREGADO' WHEN new.parcel_id IS NULL THEN 'AUSENTE_EN_VERSION' ELSE 'GEOMETRIA_MODIFICADA' END change
        FROM old FULL OUTER JOIN new ON old.parcel_id=new.parcel_id
        WHERE old.parcel_id IS NULL OR new.parcel_id IS NULL OR NOT ST_Equals(old.geom,new.geom)
        ORDER BY parcel_id LIMIT 251 OFFSET :offset"""),
            {"old": old_id, "new": new_id, "offset": offset},
        )
        .mappings()
        .all()
    )
    return jsonify(items=[dict(r) for r in rows[:250]], next_offset=offset + 250 if len(rows) > 250 else None)
