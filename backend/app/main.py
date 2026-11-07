import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.database import close_mongo_connection, connect_to_mongo
from app.services.auth import ensure_user_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await ensure_user_indexes()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="CourseMate AI",
    description="AI-powered personalized learning assistant",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Default 422 bodies echo the submitted value (including passwords); drop it.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: PyMongoError):
    logger.error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"})


app.include_router(health_router)
app.include_router(auth_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to CourseMate AI!",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}