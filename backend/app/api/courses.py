import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError

from app.api.auth import get_current_user
from app.schemas.auth import UserPublic
from app.schemas.course import CourseCreate, CoursePublic, CourseUpdate
from app.services import course as course_service

router = APIRouter(prefix="/courses", tags=["Courses"])

_OBJECT_ID_RE = re.compile(r"[0-9a-fA-F]{24}")
_NOT_FOUND = "Course not found"  # identical for "doesn't exist" and "belongs to someone else"


def valid_course_id(course_id: str) -> ObjectId:
    """Path dependency: strict 24-hex ObjectId check, returned as a typed ObjectId."""
    if not _OBJECT_ID_RE.fullmatch(course_id):
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("path", "course_id"), "msg": "Invalid course ID"}]
        )
    return ObjectId(course_id)


# NOTE: `current_user` is declared first in every route so authentication is always
# checked before any other validation (unauthenticated callers get 401, never 422/404).


@router.post("", response_model=CoursePublic, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseCreate,
    current_user: UserPublic = Depends(get_current_user),
):
    return await course_service.create_course(current_user.id, payload)


@router.get("", response_model=list[CoursePublic])
async def list_courses(
    current_user: UserPublic = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    """The authenticated user's courses, newest first."""
    return await course_service.list_courses(current_user.id, skip=skip, limit=limit)


@router.get("/{course_id}", response_model=CoursePublic)
async def get_course(
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    course = await course_service.get_course(current_user.id, course_oid)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return course


@router.put("/{course_id}", response_model=CoursePublic)
async def update_course(
    payload: CourseUpdate,
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    course = await course_service.update_course(current_user.id, course_oid, payload)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    current_user: UserPublic = Depends(get_current_user),
    course_oid: ObjectId = Depends(valid_course_id),
):
    if not await course_service.delete_course(current_user.id, course_oid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)