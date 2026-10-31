from sqlalchemy import update
from ..extensions import db
from ..models import Parcel


def promote_result(result):
    """Publish only if the analyzed cadastral version is still the active version.

    The conditional UPDATE also handles an import committed while inference was running.
    Older results remain immutable history and never regain the current-result pointer.
    """
    return (
        db.session.execute(
            update(Parcel)
            .where(
                Parcel.id == result.parcel_id,
                Parcel.source_version_id == result.parcel_version_id,
                Parcel.active.is_(True),
            )
            .values(current_result_id=result.id)
        ).rowcount
        == 1
    )
