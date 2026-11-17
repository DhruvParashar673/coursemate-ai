from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

from app.schemas.qa import Citation, ObjectIdStr

Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Level = Literal["simple", "detailed"]

MAX_KEY_POINTS = 6


class ExplainRequest(BaseModel):
    # extra="forbid": a client-supplied user_id / course_id is rejected, never trusted.
    model_config = ConfigDict(extra="forbid")

    topic: Topic
    level: Level = "simple"
    document_id: ObjectIdStr | None = None  # optional: restrict to one document


class ExplanationResponse(BaseModel):
    explanation: str
    key_points: list[str]
    example: str | None
    provider: str | None  # "groq" | "gemini"; null when no LLM call was needed
    grounded: bool  # False when the course documents did not contain enough information
    citations: list[Citation]


class ExplanationOutput(BaseModel):
    """What the LLM must return (internal). Strict about the core text, lenient about junk list items,
    so a structurally wrong answer is rejected and the next provider is tried."""

    model_config = ConfigDict(extra="ignore")

    insufficient: bool = False
    explanation: str = ""
    key_points: list[str] = Field(default_factory=list)
    example: str | None = None
    sources: list[int] = Field(default_factory=list)

    @field_validator("explanation", mode="before")
    @classmethod
    def _explanation_is_text(cls, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("explanation must be a string")
        return value.strip()

    @field_validator("key_points", mode="before")
    @classmethod
    def _clean_key_points(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("key_points must be a list")
        return [v.strip() for v in value if isinstance(v, str) and v.strip()][:MAX_KEY_POINTS]

    @field_validator("example", mode="before")
    @classmethod
    def _clean_example(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("example must be a string or null")
        return value.strip() or None

    @field_validator("sources", mode="before")
    @classmethod
    def _clean_sources(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("sources must be a list")
        numbers: list[int] = []
        for item in value:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                numbers.append(item)
            elif isinstance(item, str) and item.strip().isdigit():
                numbers.append(int(item.strip()))
        return numbers

    @model_validator(mode="after")
    def _answer_present_unless_insufficient(self):
        if not self.insufficient and len(self.explanation) < 20:
            raise ValueError("explanation is missing or too short")
        return self


# ----------------------------------------------------------------------------- chapter summaries

SummaryLength = Literal["short", "medium", "detailed"]
PageNumber = Annotated[int, Field(strict=True, ge=1, le=100000)]  # JSON integers only (no "3", 3.5 or true)
MAX_SUMMARY_POINTS = 12


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: ObjectIdStr  # required: a chapter is a page range of ONE document
    start_page: PageNumber | None = None  # defaults to the first page
    end_page: PageNumber | None = None  # defaults to the last page
    length: SummaryLength = "medium"

    @model_validator(mode="after")
    def _range_is_ordered(self):
        if self.start_page is not None and self.end_page is not None and self.start_page > self.end_page:
            raise ValueError("start_page must not exceed end_page")
        return self


class PageRange(BaseModel):
    start_page: int
    end_page: int


class SummaryResponse(BaseModel):
    summary: str
    key_points: list[str]
    page_range: PageRange  # the pages actually summarised (defaults applied)
    partial: bool  # True if a very dense range had to be thinned to respect the LLM call/size limits
    llm_calls: int  # how many LLM calls this request used (1 = direct, N+1 = map-reduce)
    provider: str | None  # provider of the final call
    grounded: bool  # False when the pages did not contain enough information to summarise
    citations: list[Citation]  # document + page citations, validated against the chunks that were read


def _clean_str_list(value, cap: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [v.strip() for v in value if isinstance(v, str) and v.strip()][:cap]


def _clean_source_numbers(value) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    numbers: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            numbers.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            numbers.append(int(item.strip()))
    return numbers


class SummaryOutput(BaseModel):
    """What the LLM must return for a summary / a section summary / the final merge (internal)."""

    model_config = ConfigDict(extra="ignore")

    insufficient: bool = False
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    sources: list[int] = Field(default_factory=list)  # chunk numbers (direct/map) or part numbers (reduce)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary_is_text(cls, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("summary must be a string")
        return value.strip()

    @field_validator("key_points", mode="before")
    @classmethod
    def _points(cls, value):
        return _clean_str_list(value, MAX_SUMMARY_POINTS)

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, value):
        return _clean_source_numbers(value)

    @model_validator(mode="after")
    def _summary_present_unless_insufficient(self):
        if not self.insufficient and len(self.summary) < 20:
            raise ValueError("summary is missing or too short")
        return self


# ----------------------------------------------------------------------------- important questions

QuestionType = Literal["short", "long", "conceptual"]
MAX_QUESTION_COUNT = 15
_TYPE_SYNONYMS = {"short answer": "short", "long answer": "long", "essay": "long", "concept": "conceptual"}


class ImportantQuestionsRequest(BaseModel):
    """Document mode: document_id (+ optional page range). Topic mode: topic (+ optional document_id filter)."""

    model_config = ConfigDict(extra="forbid")

    topic: Topic | None = None
    document_id: ObjectIdStr | None = None
    start_page: PageNumber | None = None
    end_page: PageNumber | None = None
    count: Annotated[int, Field(strict=True, ge=1, le=MAX_QUESTION_COUNT)] = 10

    @model_validator(mode="after")
    def _valid_scope(self):
        if self.topic is not None:
            if self.start_page is not None or self.end_page is not None:
                raise ValueError("start_page / end_page can only be combined with document_id, not with topic")
        elif self.document_id is None:
            raise ValueError("Provide either a topic or a document_id")
        if self.start_page is not None and self.end_page is not None and self.start_page > self.end_page:
            raise ValueError("start_page must not exceed end_page")
        return self


class ImportantQuestion(BaseModel):
    question: str
    type: QuestionType
    why_important: str
    citation: Citation  # the document + page the question is based on (validated against what was read)


class ImportantQuestionsResponse(BaseModel):
    questions: list[ImportantQuestion]
    page_range: PageRange | None  # document mode: the pages read (defaults applied); null in topic mode
    partial: bool  # True if a long range was thinned to fit the context budget
    provider: str | None
    grounded: bool  # False when the content did not support any question
    message: str | None = None  # set when grounded is false


class QuestionItem(BaseModel):
    """One question as returned by the LLM (internal). Unusable items are dropped by the list validator."""

    model_config = ConfigDict(extra="ignore")

    question: str
    type: QuestionType
    why_important: str = ""
    source: int  # number of the source chunk the question is based on

    @field_validator("question", mode="before")
    @classmethod
    def _question_text(cls, value):
        if not isinstance(value, str) or not 10 <= len(value.strip()) <= 500:
            raise ValueError("question must be text of 10-500 characters")
        return value.strip()

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, value):
        if not isinstance(value, str):
            raise ValueError("type must be a string")
        value = value.strip().lower()
        return _TYPE_SYNONYMS.get(value, value)

    @field_validator("why_important", mode="before")
    @classmethod
    def _why(cls, value):
        return value.strip()[:300] if isinstance(value, str) else ""

    @field_validator("source", mode="before")
    @classmethod
    def _source_number(cls, value):
        if isinstance(value, bool):
            raise ValueError("source must be a number")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise ValueError("source must be a number")


class ImportantQuestionsOutput(BaseModel):
    """What the LLM must return (internal): malformed items are dropped, but at least one must survive."""

    model_config = ConfigDict(extra="ignore")

    insufficient: bool = False
    questions: list[QuestionItem] = Field(default_factory=list)

    @field_validator("questions", mode="before")
    @classmethod
    def _keep_valid_items(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("questions must be a list")
        items = []
        for raw in value:
            try:
                items.append(QuestionItem.model_validate(raw))
            except ValidationError:
                continue
        return items

    @model_validator(mode="after")
    def _some_question_unless_insufficient(self):
        if not self.insufficient and not self.questions:
            raise ValueError("no usable questions")
        return self
