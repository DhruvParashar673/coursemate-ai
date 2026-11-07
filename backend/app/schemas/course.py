from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints


def _blank_to_none(value):
    """Trim optional text; treat empty/whitespace-only input as 'not provided'."""
    if isinstance(value, str):
        return value.strip() or None
    return value  # non-strings fall through to normal type validation


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Length limits are bound to the str branch only, so None (blank input) skips them.
Description = Annotated[Annotated[str, StringConstraints(max_length=2000)] | None, BeforeValidator(_blank_to_none)]
Subject = Annotated[Annotated[str, StringConstraints(max_length=100)] | None, BeforeValidator(_blank_to_none)]


class CourseCreate(BaseModel):
    # extra="forbid": a client-supplied user_id (or any unknown field) is rejected, never trusted.
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Description = None
    subject: Subject = None


class CourseUpdate(CourseCreate):
    """PUT replaces title/description/subject: omitted optional fields are cleared."""


class CoursePublic(BaseModel):
    id: str
    title: str
    description: str | None = None
    subject: str | None = None
    created_at: datetime
    updated_at: datetime