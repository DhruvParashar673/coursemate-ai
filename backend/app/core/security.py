from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


class InvalidTokenError(Exception):
    """Raised for any invalid, expired or malformed access token."""


# ---------- passwords ----------

# bcrypt only uses the first 72 bytes of a password. Instead of silently truncating
# (or pre-hashing), longer passwords are rejected; the limit is measured in UTF-8 bytes.
BCRYPT_MAX_PASSWORD_BYTES = 72


def _password_bytes(password: str) -> bytes:
    data = password.encode("utf-8")  # UnicodeEncodeError (a ValueError) for lone surrogates
    if len(data) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(f"Password exceeds {BCRYPT_MAX_PASSWORD_BYTES} bytes")
    return data


def hash_password(password: str) -> str:
    """Hash with bcrypt. Raises ValueError if the password is longer than 72 UTF-8 bytes."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a bcrypt hash. Over-long or malformed input returns False."""
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except ValueError:  # includes UnicodeEncodeError
        return False


# Used to spend the same time on unknown emails as on real ones (login timing).
DUMMY_PASSWORD_HASH = hash_password("timing-equalisation-dummy-password")


# ---------- JWT ----------

def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> str:
    """Validate signature and expiry; return the subject (user id) or raise InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],  # pinned: blocks "none"/alg-swap attacks
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Invalid token") from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("Invalid token subject")
    return subject