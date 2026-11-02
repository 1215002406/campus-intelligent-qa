from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel

from app.schemas import SourceSnapshot


class StreamEvent(BaseModel):
    event: Literal["status", "message", "sources", "done", "error"]
    data: dict


class AnswerResult(BaseModel):
    content: str
    sources: list[SourceSnapshot]
    citation_valid: bool
    refused: bool


class ChatPipeline(Protocol):
    """Reserved pipeline: ownership is checked before entry; no implementation yet."""

    def stream(self, *, conversation_id: int, question: str, user_id: int) -> AsyncIterator[StreamEvent]: ...
