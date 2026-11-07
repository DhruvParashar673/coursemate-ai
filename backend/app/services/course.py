import logging
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.database import get_database
from app.schemas.course import CourseCreate, CoursePublic, CourseUpdate

logger = logging.getLogger(__name__)

COURSES_COLLECTION = "courses"
USER_COURSES_INDEX_NAME = "idx_course_user_created"


def _collection():
    return get_database()[COURSES_COLLECTION]


def _now() -> datetime:
    # MongoDB stores milliseconds; truncate so responses match later reads.
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _require_user_id(user_id: str) -> str:
    # Guard against None/empty: a filter like {"user_id": None} would match documents
    # that lack the field, silently widening access.
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id is required")
    return user_id


def _owned(user_id: str, course_id: ObjectId) -> dict:
    """The ONLY filter used to address a single course: id AND owner."""
    return {"_id": course_id, "user_id": _require_user_id(user_id)}


def course_to_public(doc: dict) -> CoursePublic:
    """Explicit field list: user_id and raw Mongo fields are never exposed."""

    def utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    return CoursePublic(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc.get("description"),
        subject=doc.get("subject"),
        created_at=utc(doc["created_at"]),
        updated_at=utc(doc["updated_at"]),
    )


async def ensure_course_indexes() -> bool:
    """Create indexes (idempotent). Serves 'my courses, newest first' without a sort in memory."""
    try:
        await _collection().create_index(
            [("user_id", 1), ("created_at", -1), ("_id", -1)],
            name=USER_COURSES_INDEX_NAME,
        )
        return True
    except PyMongoError as exc:
        logger.error("Could not create courses index: %s", type(exc).__name__)
        return False


async def create_course(user_id: str, data: CourseCreate) -> CoursePublic:
    now = _now()
    doc = {
        "user_id": _require_user_id(user_id),  # from the authenticated user, never from the payload
        "title": data.title,
        "description": data.description,
        "subject": data.subject,
        "created_at": now,
        "updated_at": now,
    }
    result = await _collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return course_to_public(doc)


async def list_courses(user_id: str, skip: int = 0, limit: int = 100) -> list[CoursePublic]:
    cursor = (
        _collection()
        .find({"user_id": _require_user_id(user_id)})
        .sort([("created_at", -1), ("_id", -1)])  # newest first, stable tie-break
        .skip(skip)
        .limit(limit)
    )
    return [course_to_public(doc) for doc in await cursor.to_list(length=limit)]


async def get_course(user_id: str, course_id: ObjectId) -> CoursePublic | None:
    doc = await _collection().find_one(_owned(user_id, course_id))
    return course_to_public(doc) if doc else None


async def update_course(user_id: str, course_id: ObjectId, data: CourseUpdate) -> CoursePublic | None:
    # Single atomic operation: the ownership check and the write are the same query.
    doc = await _collection().find_one_and_update(
        _owned(user_id, course_id),
        {
            "$set": {
                "title": data.title,
                "description": data.description,
                "subject": data.subject,
                "updated_at": _now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return course_to_public(doc) if doc else None


async def delete_course(user_id: str, course_id: ObjectId) -> bool:
    result = await _collection().delete_one(_owned(user_id, course_id))
    return result.deleted_count == 1