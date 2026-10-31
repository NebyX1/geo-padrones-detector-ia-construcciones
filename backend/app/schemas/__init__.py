from marshmallow import Schema, fields, validate, RAISE, ValidationError

ROLES = ["superadmin", "admin", "analyst", "reviewer", "viewer"]
STATES = [
    "CON_CONSTRUCCION_VISIBLE",
    "SIN_CONSTRUCCION_VISIBLE",
    "INDETERMINADO",
    "NO_ANALIZADO",
    "ERROR_ANALISIS",
]


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE


class LoginSchema(StrictSchema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=1, max=256))


class UserSchema(StrictSchema):
    email = fields.Email(required=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    password = fields.String(required=True, validate=validate.Length(min=12, max=256))
    role = fields.String(required=True, validate=validate.OneOf(ROLES))
    is_active = fields.Boolean(load_default=True)


class AnalysisSchema(StrictSchema):
    parcel_ids = fields.List(fields.UUID(), required=True, validate=validate.Length(min=1, max=100))
    scene_id = fields.UUID(required=True)
    model_version_id = fields.UUID(required=True)
    probability = fields.Float(load_default=0.5, validate=validate.Range(min=0.1, max=0.99))
    min_area = fields.Float(load_default=8, validate=validate.Range(min=0, max=1000))
    min_object_area = fields.Float(load_default=2, validate=validate.Range(min=0, max=1000))
    min_occupancy = fields.Float(load_default=0.01, validate=validate.Range(min=0, max=1))
    min_coverage = fields.Float(load_default=0.95, validate=validate.Range(min=0.5, max=1))
    max_image_age_days = fields.Integer(load_default=730, validate=validate.Range(min=1, max=36500))


class ReviewSchema(StrictSchema):
    version = fields.Integer(required=True, validate=validate.Range(min=1))
    status = fields.String(required=True, validate=validate.OneOf(["CONFIRMADO", "CORREGIDO", "RECHAZADO"]))
    state = fields.String(required=True, validate=validate.OneOf(STATES[:3]))
    observations = fields.String(required=True, validate=validate.Length(min=3, max=4000))
    geometry = fields.Dict(load_default=None, allow_none=True)


def load(schema, value):
    if not isinstance(value, dict):
        raise ValidationError({"body": ["Se esperaba un objeto JSON."]})
    return schema.load(value)
