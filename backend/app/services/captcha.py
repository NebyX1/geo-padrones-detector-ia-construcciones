"""Numeric verification matching sample/admin: two numbers from 1 through 10.

Answers stay hashed server-side. Browser-bound challenges expire after ten minutes
and are consumed even on a wrong answer or a later invalid password.
"""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from flask import abort, current_app, session
from sqlalchemy import select, delete, or_
from ..extensions import db
from ..models import LoginCaptcha, uid, utcnow


def digest(identifier, answer):
    return hmac.new(
        current_app.secret_key.encode(), f"login-captcha:{identifier}:{answer}".encode(), hashlib.sha256
    ).hexdigest()


def create_captcha():
    nonce = session.setdefault("captcha_nonce", secrets.token_urlsafe(32))
    browser_digest = hashlib.sha256(nonce.encode()).hexdigest()
    db.session.execute(
        delete(LoginCaptcha).where(
            or_(LoginCaptcha.expires_at <= utcnow(), LoginCaptcha.browser_digest == browser_digest)
        )
    )
    left, right = secrets.randbelow(10) + 1, secrets.randbelow(10) + 1
    identifier = uid()
    db.session.add(
        LoginCaptcha(
            id=identifier,
            browser_digest=browser_digest,
            answer_digest=digest(identifier, str(left + right)),
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    db.session.commit()
    return {"id": identifier, "question": f"{left} + {right}", "expires_in": 600}


def consume_captcha(identifier, answer):
    challenge = db.session.execute(
        select(LoginCaptcha).where(LoginCaptcha.id == identifier).with_for_update()
    ).scalar_one_or_none()
    nonce = session.get("captcha_nonce", "")
    if (
        not challenge
        or not nonce
        or not hmac.compare_digest(challenge.browser_digest, hashlib.sha256(nonce.encode()).hexdigest())
    ):
        abort(422, "Captcha incorrecto o vencido. Resolvé una nueva suma.")
    usable = challenge.consumed_at is None and challenge.expires_at > utcnow()
    normalized = (
        str(int(answer)) if isinstance(answer, str) and re.fullmatch(r"[0-9]{1,2}", answer) else "invalid"
    )
    valid = usable and hmac.compare_digest(challenge.answer_digest, digest(challenge.id, normalized))
    challenge.consumed_at = utcnow()
    db.session.commit()
    if not valid:
        abort(422, "Captcha incorrecto o vencido. Resolvé una nueva suma.")
