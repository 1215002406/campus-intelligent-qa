from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: int
    username: str
    role: Literal["student", "admin"]
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: Username
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class RegisterRequest(BaseModel):
    username: Username
    password: str
    role: Literal["student", "admin"]
    admin_code: str | None = None


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class ConversationOut(ORMModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class SourceSnapshot(BaseModel):
    citation_id: int = Field(ge=1)
    chunk_id: int
    document_code: str
    document_title: str
    section_id: str
    excerpt: str
    page_start: int | None = None
    page_end: int | None = None


class MessageOut(ORMModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["completed", "failed"]
    sources_json: list[SourceSnapshot]
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ChatRequest(BaseModel):
    conversation_id: int = Field(gt=0)
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class DocumentOut(ORMModel):
    id: int
    document_code: str
    title: str
    category: Literal["教务", "学工", "后勤", "跨部门"]
    original_name: str
    status: Literal["pending", "parsing", "indexing", "ready", "failed", "disabled"]
    index_version: str | None
    chunk_count: int = 0
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    category: Literal["教务", "学工", "后勤", "跨部门"] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("文档标题不能为空")
        return value

    @model_validator(mode="after")
    def require_change(self):
        if self.title is None and self.category is None:
            raise ValueError("至少需要修改标题或分类")
        return self


class BatchUploadItem(BaseModel):
    filename: str
    success: bool
    status_code: int
    document: DocumentOut | None = None
    error: str | None = None
    overwritten: bool = False


class BatchUploadResponse(BaseModel):
    total: int
    accepted: int
    rejected: int
    items: list[BatchUploadItem]


class ChunkOut(ORMModel):
    id: int
    document_id: int
    index_version: str
    section_id: str
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    metadata_json: dict[str, Any]
    created_at: datetime


class DocumentDetail(DocumentOut):
    chunks: list[ChunkOut] = Field(validation_alias="current_chunks")


class RetrievalSearchRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    category: Literal["教务", "学工", "后勤", "跨部门"] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class RetrievalHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    category: Literal["教务", "学工", "后勤", "跨部门"]
    section_id: str
    page_start: int | None
    page_end: int | None
    content: str
    score: float
    vector_score: float
    keyword_score: float


class RetrievalSearchResponse(BaseModel):
    profile: str
    hits: list[RetrievalHit]


class EmbeddingProfileStatus(BaseModel):
    id: str
    label: str
    model: str
    dimensions: int
    indexed_chunks: int
    expected_chunks: int
    ready: bool
    active: bool


class VectorIndexStatus(BaseModel):
    active_profile: str
    profiles: list[EmbeddingProfileStatus]
    progress: dict[str, Any]


class EmbeddingRebuildRequest(BaseModel):
    profile: Literal["bge-small", "qwen-0.6b"] | None = None


class EmbeddingSwitchRequest(BaseModel):
    profile: Literal["bge-small", "qwen-0.6b"]


class LLMModelProfileOut(BaseModel):
    id: Literal["local", "remote"]
    label: str
    configured: bool
    active: bool
    base_url: str
    model: str


class LLMModelStatus(BaseModel):
    active_provider: Literal["local", "remote"]
    profiles: list[LLMModelProfileOut]


class LLMModelSwitchRequest(BaseModel):
    provider: Literal["local", "remote"]


class LLMRemoteConfigUpdate(BaseModel):
    base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    api_key: str | None = Field(default=None, max_length=4096)
