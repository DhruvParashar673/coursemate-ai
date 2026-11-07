import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncMongoClient | None = None
_db: AsyncDatabase | None = None


async def connect_to_mongo() -> None:
    """Create the MongoDB client. Called once on application startup."""
    global _client, _db
    settings = get_settings()
    _client = AsyncMongoClient(
        settings.MONGODB_URL.get_secret_value(),
        serverSelectionTimeoutMS=5000,
        appname="coursemate-ai",
    )
    _db = _client[settings.DATABASE_NAME]

    # Don't crash the API if Atlas is unreachable; /health/db will report it.
    if await ping_database():
        logger.info("Connected to MongoDB database '%s'", settings.DATABASE_NAME)
    else:
        logger.warning("MongoDB is not reachable; check MONGODB_URL and Atlas network access")


async def close_mongo_connection() -> None:
    """Close the MongoDB client. Called once on application shutdown."""
    global _client, _db
    if _client is not None:
        await _client.close()
        logger.info("MongoDB connection closed")
    _client = None
    _db = None


def get_database() -> AsyncDatabase:
    """Return the active database handle (for use by routes/services)."""
    if _db is None:
        raise RuntimeError("Database is not initialised")
    return _db


async def ping_database() -> bool:
    """Return True if MongoDB answers a ping. Never logs or returns credentials."""
    if _db is None:
        return False
    try:
        await _db.command("ping")
        return True
    except PyMongoError as exc:
        # Log only the error type; messages can contain connection details.
        logger.error("MongoDB ping failed: %s", type(exc).__name__)
        return False