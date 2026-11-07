import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.database import get_database
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.schemas.auth import UserPublic

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"
EMAIL_INDEX_NAME = "uniq_user_email"

_indexes_ready = False


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


async def ensure_user_indexes() -> bool:
    """Create the unique email index (idempotent). Returns True on success."""
    global _indexes_ready
    try:
        await get_database()[USERS_COLLECTION].create_index(
            "email", unique=True, name=EMAIL_INDEX_NAME
        )
        _indexes_ready = True
    except PyMongoError as exc:
        logger.error("Could not create users index: %s", type(exc).__name__)
        _indexes_ready = False
    return _indexes_ready


def user_to_public(doc: dict) -> UserPublic:
    """Build the safe user view from an explicit field list (never includes password_hash)."""
    created_at = doc["created_at"]
    if created_at.tzinfo is None:  # PyMongo returns naive UTC datetimes by default
        created_at = created_at.replace(tzinfo=timezone.utc)
    return UserPublic(
        id=str(doc["_id"]),
        name=doc["name"],
        email=doc["email"],
        created_at=created_at,
    )


async def create_user(name: str, email: str, password: str) -> UserPublic:
    # If the startup attempt failed (e.g. Atlas was down), retry before inserting,
    # so duplicate emails are always blocked by the unique index.
    if not _indexes_ready and not await ensure_user_indexes():
        raise PyMongoError("users index unavailable")

    now = datetime.now(timezone.utc)
    doc = {
        "name": name,
        "email": email,
        "password_hash": await asyncio.to_thread(hash_password, password),
        # MongoDB stores milliseconds; truncate so the signup response matches later reads.
        "created_at": now.replace(microsecond=now.microsecond // 1000 * 1000),
    }
    try:
        result = await get_database()[USERS_COLLECTION].insert_one(doc)
    except DuplicateKeyError:
        raise EmailAlreadyRegisteredError from None
    doc["_id"] = result.inserted_id
    return user_to_public(doc)


async def authenticate_user(email: str, password: str) -> UserPublic:
    user = await get_database()[USERS_COLLECTION].find_one({"email": email})

    # Always run one bcrypt check so response time doesn't reveal whether the email exists.
    stored_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    password_ok = await asyncio.to_thread(verify_password, password, stored_hash)

    if user is None or not password_ok:
        raise InvalidCredentialsError
    return user_to_public(user)


async def get_user_by_id(user_id: str) -> UserPublic | None:
    if not ObjectId.is_valid(user_id):
        return None
    user = await get_database()[USERS_COLLECTION].find_one(
        {"_id": ObjectId(user_id)}, projection={"password_hash": 0}
    )
    return user_to_public(user) if user else None