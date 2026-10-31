from flask import abort
from sqlalchemy import select, func
from ..extensions import db
from ..models import ParcelGeometryVersion


def original_geometry(result):
    geometry = db.session.execute(
        select(func.ST_Multi(func.ST_UnaryUnion(func.ST_Collect(ParcelGeometryVersion.geom)))).where(
            ParcelGeometryVersion.parcel_id == result.parcel_id,
            ParcelGeometryVersion.dataset_version_id == result.parcel_version_id,
        )
    ).scalar()
    if geometry is None:
        abort(409, "No hay una geometría histórica verificable para este análisis.")
    return geometry
