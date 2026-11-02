import time
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _encode(sub: int, kind: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {"sub": str(sub), "typ": kind, "iat": now, "exp": now + ttl_seconds, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def create_access_token(user_id: int) -> str:
    return _encode(user_id, "access", get_settings().access_ttl_minutes * 60)


def create_refresh_token(user_id: int) -> str:
    return _encode(user_id, "refresh", get_settings().refresh_ttl_days * 86400)


def decode_token(token: str, expected: str) -> int:
    """Return the user id or raise jwt.PyJWTError. A refresh token is rejected as an access token and vice versa."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("typ") != expected:
        raise jwt.InvalidTokenError("wrong token type")
    return int(payload["sub"])
