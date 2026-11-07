from fastapi import APIRouter, HTTPException, status

from app.core.database import ping_database

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/db")
async def db_health():
    if not await ping_database():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unreachable",
        )
    return {"status": "healthy", "database": "connected"}