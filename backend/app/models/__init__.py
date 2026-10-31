"""Identidades, evidencia original y correcciones tienen persistencia separada."""

import uuid
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from flask_login import UserMixin
from geoalchemy2 import Geometry
from ..extensions import db

ph = PasswordHasher()


def utcnow():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.String(36), primary_key=True, default=uid)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class User(UserMixin, Base):
    __tablename__ = "users"
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), nullable=False, default="viewer")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    last_login_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.CheckConstraint("role IN ('superadmin','admin','analyst','reviewer','viewer')", name="valid_role"),
    )

    def set_password(self, password):
        self.password_hash = ph.hash(password)

    def check_password(self, password):
        try:
            return ph.verify(self.password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def public(self):
        return dict(
            id=self.id,
            email=self.email,
            name=self.name,
            role=self.role,
            is_active=self.is_active,
            last_login_at=self.last_login_at,
        )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    user_id = db.Column(db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.String(120))
    details = db.Column(db.JSON, nullable=False, default=dict)
    request_id = db.Column(db.String(36))


class CadastralDatasetVersion(Base):
    __tablename__ = "cadastral_versions"
    sha256 = db.Column(db.String(64), unique=True, nullable=False)
    source = db.Column(db.Text, nullable=False)
    count = db.Column(db.Integer, nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)


class CadastralLocality(Base):
    __tablename__ = "localities"
    coddepto = db.Column(db.String(8), nullable=False)
    codloccat = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    __table_args__ = (db.UniqueConstraint("coddepto", "codloccat"),)


class Parcel(Base):
    __tablename__ = "parcels"
    coddepto = db.Column(db.String(8), nullable=False, index=True)
    codloccat = db.Column(db.String(20), nullable=False, index=True)
    padron = db.Column(db.String(40), nullable=False, index=True)
    locality_id = db.Column(db.ForeignKey("localities.id"), nullable=False)
    geom = db.Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    m2_parcela = db.Column(db.Float, nullable=False)
    source_version_id = db.Column(db.ForeignKey("cadastral_versions.id"), nullable=False)
    current_result_id = db.Column(
        db.String(36), db.ForeignKey("parcel_results.id", use_alter=True, name="fk_parcels_current_result")
    )
    active = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (
        db.UniqueConstraint("coddepto", "codloccat", "padron"),
        db.CheckConstraint("m2_parcela > 0"),
    )


class ParcelGeometryVersion(Base):
    __tablename__ = "parcel_geometries"
    parcel_id = db.Column(db.ForeignKey("parcels.id"), nullable=False, index=True)
    dataset_version_id = db.Column(db.ForeignKey("cadastral_versions.id"), nullable=False)
    source_feature_id = db.Column(db.String(160), nullable=False)
    original = db.Column(db.JSON, nullable=False)
    geom = db.Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    repaired = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint("dataset_version_id", "source_feature_id"),)


class LandUseCategory(Base):
    __tablename__ = "land_use_categories"
    source_feature_id = db.Column(db.String(160), unique=True, nullable=False)
    properties = db.Column(db.JSON, nullable=False)
    source = db.Column(db.Text, nullable=False)
    geom = db.Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)


class ImageryScene(Base):
    __tablename__ = "imagery_scenes"
    name = db.Column(db.String(160), nullable=False)
    source = db.Column(db.Text, nullable=False)
    coverage_id = db.Column(db.String(180), unique=True, nullable=False)
    captured_at = db.Column(db.String(32), nullable=False)  # May be only YYYY-MM; preserve source precision.
    resolution_m = db.Column(db.Float, nullable=False)
    srid = db.Column(db.Integer, nullable=False, default=5382)
    license = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)


class ImageryAsset(Base):
    __tablename__ = "imagery_assets"
    scene_id = db.Column(db.ForeignKey("imagery_scenes.id"), nullable=False)
    cache_key = db.Column(db.String(64), unique=True, nullable=False)
    object_key = db.Column(db.Text, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False)


class AIModelVersion(Base):
    __tablename__ = "model_versions"
    model_id = db.Column(db.String(200), nullable=False)
    revision = db.Column(db.String(64), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    license = db.Column(db.String(80), nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (db.UniqueConstraint("model_id", "revision"),)


class Job(Base):
    __tablename__ = "jobs"
    kind = db.Column(db.String(20), nullable=False, index=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="PENDING", index=True)
    idempotency_key = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    total = db.Column(db.Integer, nullable=False, default=0)
    processed = db.Column(db.Integer, nullable=False, default=0)
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
    error = db.Column(db.Text)
    output_key = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint("user_id", "kind", "idempotency_key"),)

    def public(self):
        return {
            k: getattr(self, k)
            for k in (
                "id",
                "kind",
                "status",
                "total",
                "processed",
                "created_at",
                "started_at",
                "finished_at",
                "error",
                "cancel_requested",
            )
        }


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    job_id = db.Column(db.ForeignKey("jobs.id"), unique=True, nullable=False)
    model_version_id = db.Column(db.ForeignKey("model_versions.id"), nullable=False)
    scene_id = db.Column(db.ForeignKey("imagery_scenes.id"), nullable=False)
    parameters = db.Column(db.JSON, nullable=False)


class ParcelAnalysisResult(Base):
    __tablename__ = "parcel_results"
    run_id = db.Column(db.ForeignKey("analysis_runs.id"), nullable=False, index=True)
    parcel_id = db.Column(db.ForeignKey("parcels.id"), nullable=False, index=True)
    parcel_version_id = db.Column(db.ForeignKey("cadastral_versions.id"), nullable=False)
    asset_id = db.Column(db.ForeignKey("imagery_assets.id"))
    state = db.Column(db.String(40), nullable=False)
    m2_huella_detectada = db.Column(db.Float)
    occupancy = db.Column(db.Float)
    building_count = db.Column(db.Integer)
    coverage = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Float)
    error = db.Column(db.Text)
    mask_key = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint("run_id", "parcel_id"),)


class BuildingFootprint(Base):
    __tablename__ = "building_footprints"
    result_id = db.Column(db.ForeignKey("parcel_results.id"), nullable=False, index=True)
    geom = db.Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    confidence = db.Column(db.Float)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    object_key = db.Column(db.Text, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="PREVIEW")
    mapping = db.Column(db.JSON, nullable=False, default=dict)
    options = db.Column(db.JSON, nullable=False, default=dict)
    summary = db.Column(db.JSON, nullable=False, default=dict)
    job_id = db.Column(db.ForeignKey("jobs.id"))


class ImportMapping(Base):
    __tablename__ = "import_mappings"
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    mapping = db.Column(db.JSON, nullable=False)
    options = db.Column(db.JSON, nullable=False)


class ImportedParcelDeclaration(Base):
    __tablename__ = "declarations"
    batch_id = db.Column(db.ForeignKey("import_batches.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    parcel_id = db.Column(db.ForeignKey("parcels.id"), index=True)
    key = db.Column(db.JSON, nullable=False)
    declared_building = db.Column(db.Boolean)
    declared_m2 = db.Column(db.Float)
    observations = db.Column(db.Text)
    issues = db.Column(db.JSON, nullable=False, default=list)
    original = db.Column(db.JSON, nullable=False)
    __table_args__ = (db.UniqueConstraint("batch_id", "row_number"),)


class ComparisonRun(Base):
    __tablename__ = "comparison_runs"
    batch_id = db.Column(db.ForeignKey("import_batches.id"), nullable=False)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    parameters = db.Column(db.JSON, nullable=False)
    job_id = db.Column(db.ForeignKey("jobs.id"), unique=True, nullable=False)


class ParcelComparisonResult(Base):
    __tablename__ = "comparison_results"
    run_id = db.Column(db.ForeignKey("comparison_runs.id"), nullable=False, index=True)
    declaration_id = db.Column(db.ForeignKey("declarations.id"), nullable=False)
    result_id = db.Column(db.ForeignKey("parcel_results.id"))
    state = db.Column(db.String(50), nullable=False, index=True)
    difference_m2 = db.Column(db.Float)
    difference_pct = db.Column(db.Float)
    warning = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint("run_id", "declaration_id"),)


class ReviewCase(Base):
    __tablename__ = "review_cases"
    result_id = db.Column(db.ForeignKey("parcel_results.id"), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="PENDIENTE_REVISION")
    version = db.Column(db.Integer, nullable=False, default=1)
    assigned_to = db.Column(db.ForeignKey("users.id"))
    needs_reanalysis = db.Column(db.Boolean, nullable=False, default=False)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    case_id = db.Column(db.ForeignKey("review_cases.id"), nullable=False, index=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    state = db.Column(db.String(40), nullable=False)
    observations = db.Column(db.Text, nullable=False)
    corrected_geom = db.Column(Geometry("MULTIPOLYGON", srid=4326))
    corrected_m2 = db.Column(db.Float)
    version = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint("case_id", "version"),)


class ReviewAttachment(Base):
    __tablename__ = "review_attachments"
    case_id = db.Column(db.ForeignKey("review_cases.id"), nullable=False, index=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    object_key = db.Column(db.Text, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    mime = db.Column(db.String(80), nullable=False)
    size = db.Column(db.Integer, nullable=False)


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.JSON, nullable=False)
