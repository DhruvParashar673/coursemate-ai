import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.qa import router as qa_router
from app.api.health import router as health_router
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.upload_limit import UploadGuardMiddleware
from app.rag.errors import EmbeddingError, StorageError, VectorStoreError
from app.services.auth import ensure_user_indexes
from app.services.course import ensure_course_indexes
from app.services.document import DocumentError, initialize_documents
from app.services.llm import LLMUnavailableError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await ensure_user_indexes()
    await ensure_course_indexes()
    await initialize_documents()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="CourseMate AI",
    description="AI-powered personalized learning assistant",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(UploadGuardMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Default 422 bodies echo the submitted value (including passwords); drop it.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: PyMongoError):
    logger.error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"})


@app.exception_handler(DocumentError)
async def document_error_handler(request: Request, exc: DocumentError):
    # Fixed, client-safe messages only (no paths, no internals).
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(VectorStoreError)
@app.exception_handler(EmbeddingError)
@app.exception_handler(StorageError)
async def backend_unavailable_handler(request: Request, exc: Exception):
    logger.error("Backend component error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"})


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError):
    # Provider details (names, errors, keys) are logged by the LLM layer by type only; never returned.
    logger.error("No LLM answer available for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "The answer service is temporarily unavailable. Please try again shortly."},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(documents_router)
app.include_router(qa_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to CourseMate AI!",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}