import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, SecretStr, StringConstraints

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(value: str) -> str:
    if not _EMAIL_RE.fullmatch(value):
        raise ValueError("Invalid email address")
    return value


# Trimmed, lower-cased, then format-checked.
NormalizedEmail = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=254),
    AfterValidator(_check_email),
]

MIN_PASSWORD_LENGTH = 8  # characters (signup only)


def _password_check(min_chars: int):
    """Min length in characters; max length in UTF-8 bytes (bcrypt's 72-byte limit)."""

    def check(value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if len(password) < min_chars:
            raise ValueError(f"Password must be at least {min_chars} characters long")
        try:
            byte_length = len(password.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("Password contains invalid characters") from None
        if byte_length > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes "
                "(non-English characters and emoji use 2-4 bytes each)"
            )
        return value

    return check


SignupPassword = Annotated[SecretStr, AfterValidator(_password_check(MIN_PASSWORD_LENGTH))]
# No minimum on login (don't leak the password policy), but the same maximum byte limit.
LoginPassword = Annotated[SecretStr, AfterValidator(_password_check(1))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SignupRequest(BaseModel):
    name: Name
    email: NormalizedEmail
    password: SignupPassword


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: LoginPassword


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic