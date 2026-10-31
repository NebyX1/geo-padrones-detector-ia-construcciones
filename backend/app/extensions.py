from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from .services.mail import BoundedMail

db = SQLAlchemy()
migrate = Migrate(
    compare_type=True,
    include_object=lambda obj, name, kind, reflected, compare_to: not (
        kind == "table" and reflected and compare_to is None
    ),
)
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per minute"])
talisman = Talisman()
mail = BoundedMail()
