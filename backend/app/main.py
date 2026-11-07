import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.database import close_mongo_connection, connect_to_mongo

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="CourseMate AI",
    description="AI-powered personalized learning assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to CourseMate AI!",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}