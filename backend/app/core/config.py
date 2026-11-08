from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / backend/.env."""

    MONGODB_URL: SecretStr
    DATABASE_NAME: str

    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0, le=1440)

    # --- Documents / RAG (all optional: defaults need no .env changes) ---
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-small"
    EMBEDDING_QUERY_PREFIX: str | None = None  # None -> derived from the model family
    EMBEDDING_PASSAGE_PREFIX: str | None = None
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=256)
    CHUNK_SIZE_CHARS: int = Field(default=1000, ge=200, le=4000)
    CHUNK_OVERLAP_CHARS: int = Field(default=150, ge=0)
    MAX_UPLOAD_SIZE_MB: int = Field(default=25, ge=1, le=200)
    MAX_PDF_PAGES: int = Field(default=500, ge=1, le=5000)
    MIN_TEXT_PAGE_RATIO: float = Field(default=0.1, ge=0.0, le=1.0)
    INGESTION_TIMEOUT_SECONDS: int = Field(default=900, ge=1)
    UPLOAD_DIR: Path = BACKEND_DIR / "uploads"
    CHROMA_PERSIST_DIR: Path = BACKEND_DIR / "chroma_db"
    CHROMA_COLLECTION_NAME: str = Field(default="course_chunks", min_length=3)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # later modules can add keys to .env without breaking this
        hide_input_in_errors=True,  # never echo secret values in validation errors
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return value

    @field_validator("UPLOAD_DIR", "CHROMA_PERSIST_DIR")
    @classmethod
    def _resolve_relative_to_backend(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_DIR / value

    @model_validator(mode="after")
    def _overlap_fits_chunk(self):
        if self.CHUNK_OVERLAP_CHARS > self.CHUNK_SIZE_CHARS // 2:
            raise ValueError("CHUNK_OVERLAP_CHARS must be at most half of CHUNK_SIZE_CHARS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()