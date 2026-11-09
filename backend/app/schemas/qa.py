from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
ObjectIdStr = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{24}$")]


class AskRequest(BaseModel):
    # extra="forbid": a client-supplied user_id / course_id is rejected, never trusted.
    model_config = ConfigDict(extra="forbid")

    question: Question
    document_id: ObjectIdStr | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    document_id: str
    filename: str  # the document's original filename
    page_number: int


class AskResponse(BaseModel):
    answer: str
    provider: str | None  # "groq" | "gemini"; null when no LLM call was needed
    grounded: bool  # False when the course documents did not contain enough information
    citations: list[Citation]
