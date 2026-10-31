import math
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user
from sqlalchemy import select, func, text
from ..extensions import db
from ..models import (
    User,
    AuditLog,
    Parcel,
    ParcelAnalysisResult,
    ImportBatch,
    ParcelComparisonResult,
    ReviewCase,
    Job,
    SystemSetting,
    AIModelVersion,
)
from ..schemas import UserSchema, load
from ..utils.security import require, audit

bp = Blueprint("admin", __name__)


@bp.get("/users")
@require("users")
def users():
    return jsonify(
        items=[
            u.public()
            for u in db.session.execute(select(User).order_by(User.created_at.desc()).limit(250)).scalars()
        ]
    )


@bp.post("/users")
@require("users")
def create_user():
    data = load(UserSchema(), request.get_json())
    if current_user.role != "superadmin" and data["role"] in {"superadmin", "admin"}:
        abort(403, "Solo el superadministrador puede otorgar permisos administrativos.")
    user = User(
        email=data["email"].strip().lower(), name=data["name"], role=data["role"], is_active=data["is_active"]
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()
    audit("USER_CREATE", user.id, {"role": user.role})
    db.session.commit()
    return jsonify(user=user.public()), 201


@bp.patch("/users/<identifier>")
@require("users")
def edit_user(identifier):
    data = load(UserSchema(partial=True), request.get_json())
    # Serialize role changes so the last active superadmin cannot be removed concurrently.
    db.session.execute(text("SELECT pg_advisory_xact_lock(805383)"))
    user = db.session.execute(
        select(User).where(User.id == identifier).with_for_update()
    ).scalar_one_or_none()
    if not user:
        abort(404)
    if current_user.role != "superadmin" and (
        user.role in {"superadmin", "admin"} or data.get("role") in {"superadmin", "admin"}
    ):
        abort(403)
    if user.role == "superadmin" and (
        data.get("role", user.role) != "superadmin" or data.get("is_active") is False
    ):
        count = db.session.execute(
            select(func.count()).select_from(User).where(User.role == "superadmin", User.is_active.is_(True))
        ).scalar()
        if count <= 1:
            abort(409, "Debe existir al menos un superadministrador activo.")
    if "password" in data:
        user.set_password(data.pop("password"))
    for key, value in data.items():
        setattr(user, key, value.lower().strip() if key == "email" else value)
    user.session_version += 1
    audit("USER_UPDATE", user.id, {"fields": list(data)})
    db.session.commit()
    return jsonify(user=user.public())


@bp.post("/users/<identifier>/reset-access")
@require("users")
def reset_access(identifier):
    from .auth import issue_challenge

    user = db.get_or_404(User, identifier)
    if current_user.role != "superadmin" and user.role in {"superadmin", "admin"}:
        abort(403)
    if not user.is_active:
        abort(409, "Active la cuenta antes de restablecer su acceso.")
    issue_challenge(user, "reset")
    user.session_version += 1
    audit("ADMIN_RESET_ACCESS", user.id)
    db.session.commit()
    return jsonify(message="Se envió un código de recuperación y se revocaron sesiones anteriores.")


@bp.get("/admin/audit")
@require("users")
def audit_logs():
    limit = min(max(request.args.get("limit", 100, type=int), 1), 250)
    offset = max(request.args.get("offset", 0, type=int), 0)
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    return jsonify(
        items=[
            dict(
                id=a.id,
                action=a.action,
                entity_id=a.entity_id,
                user_id=a.user_id,
                details=a.details,
                created_at=a.created_at,
                request_id=a.request_id,
            )
            for a in db.session.execute(query).scalars()
        ]
    )


@bp.route("/admin/settings", methods=["GET", "PATCH"])
@require("settings")
def settings():
    if request.method == "PATCH":
        data = request.get_json() or {}
        # Only explicit UI settings; never mutate secrets, endpoint URLs, paths or SQL.
        if set(data) - {"theme_colors", "default_thresholds"}:
            abort(422, "Configuración no admitida.")
        for key, value in data.items():
            if not isinstance(value, dict) or len(str(value)) > 4000:
                abort(422)
            if key == "theme_colors":
                import re

                if any(
                    not isinstance(v, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", v) for v in value.values()
                ):
                    abort(422, "Use colores hexadecimales de seis dígitos.")
            if key == "default_thresholds":
                for name, number in value.items():
                    if (
                        name not in {"probability", "min_area", "min_coverage", "min_occupancy"}
                        or not isinstance(number, (int, float))
                        or not math.isfinite(number)
                        or number < 0
                    ):
                        abort(422)
                    if name != "min_area" and number > 1:
                        abort(422)
            db.session.merge(SystemSetting(key=key, value=value))
        audit("SETTINGS_UPDATE", details={"keys": list(data)})
        db.session.commit()
    return jsonify(settings={s.key: s.value for s in db.session.execute(select(SystemSetting)).scalars()})


@bp.patch("/models/<identifier>")
@require("settings")
def update_model(identifier):
    data = request.get_json() or {}
    if set(data) != {"enabled"} or not isinstance(data["enabled"], bool):
        abort(422)
    model = db.get_or_404(AIModelVersion, identifier)
    model.enabled = data["enabled"]
    audit("MODEL_UPDATE", model.id, data)
    db.session.commit()
    return jsonify(id=model.id, enabled=model.enabled)


@bp.get("/dashboard")
@require("read")
def dashboard():
    locality = request.args.get("locality")
    query = (
        select(
            func.count(Parcel.id),
            func.count(ParcelAnalysisResult.id),
            func.coalesce(func.sum(ParcelAnalysisResult.m2_huella_detectada), 0),
        )
        .outerjoin(ParcelAnalysisResult, Parcel.current_result_id == ParcelAnalysisResult.id)
        .where(Parcel.active.is_(True))
    )
    by_state = (
        select(ParcelAnalysisResult.state, func.count())
        .join(Parcel, Parcel.current_result_id == ParcelAnalysisResult.id)
        .where(Parcel.active.is_(True))
    )
    if locality:
        query = query.where(Parcel.codloccat == locality)
        by_state = by_state.where(Parcel.codloccat == locality)
    total, analyzed, area = db.session.execute(query).one()
    states = dict(db.session.execute(by_state.group_by(ParcelAnalysisResult.state)).all())

    def state_count(state):
        return states.get(state, 0)

    def scalar_count(model):
        return db.session.execute(select(func.count()).select_from(model)).scalar()

    from ..models import CadastralLocality

    localities = db.session.execute(
        select(CadastralLocality.name, func.count(Parcel.id), func.count(ParcelAnalysisResult.id))
        .join(Parcel, Parcel.locality_id == CadastralLocality.id)
        .outerjoin(ParcelAnalysisResult, Parcel.current_result_id == ParcelAnalysisResult.id)
        .where(Parcel.active.is_(True))
        .group_by(CadastralLocality.name)
        .order_by(func.count(Parcel.id).desc())
    ).all()
    return jsonify(
        total_parcels=total,
        analyzed=analyzed,
        with_buildings=state_count("CON_CONSTRUCCION_VISIBLE"),
        without_buildings=state_count("SIN_CONSTRUCCION_VISIBLE"),
        indeterminate=state_count("INDETERMINADO"),
        footprint_m2=area,
        analyzed_pct=analyzed / total * 100 if total else 0,
        imports=scalar_count(ImportBatch),
        discrepancies=db.session.execute(
            select(func.count())
            .select_from(ParcelComparisonResult)
            .where(ParcelComparisonResult.state == "POSIBLE_CONSTRUCCION_NO_DECLARADA")
        ).scalar(),
        pending_reviews=db.session.execute(
            select(func.count()).select_from(ReviewCase).where(ReviewCase.status == "PENDIENTE_REVISION")
        ).scalar(),
        running_jobs=db.session.execute(
            select(func.count()).select_from(Job).where(Job.status.in_(["QUEUED", "RUNNING", "PENDING"]))
        ).scalar(),
        states=states,
        localities=[dict(name=name, total=count, analyzed=done) for name, count, done in localities],
        validation="PENDIENTE: se requiere muestra local etiquetada; no hay una precisión demostrada en Lavalleja.",
    )
