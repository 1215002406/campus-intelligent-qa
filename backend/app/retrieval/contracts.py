from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas import SourceSnapshot


@dataclass(frozen=True)
class IndexMetadata:
    embedding_model: str
    vector_dimensions: int
    chunk_rule_id: str
    built_at: datetime


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: int
    document_id: int
    index_version: str
    score: float
    source: SourceSnapshot


class VectorIndex(Protocol):
    """Implementations must reject metadata mismatch and use str(chunk.id) as vector IDs."""

    def metadata(self) -> IndexMetadata: ...
    async def query(self, vector: Sequence[float], limit: int = 8) -> list[RetrievalCandidate]: ...
    async def delete_version(self, document_id: int, index_version: str) -> None: ...


class KeywordIndex(Protocol):
    def rebuild(self) -> None: ...
    def search(self, question: str, limit: int = 8) -> list[RetrievalCandidate]: ...


class HybridRetriever(Protocol):
    """Future orchestration filters current ready MySQL versions after vector lookup."""

    async def retrieve(self, question: str, limit: int = 5) -> list[RetrievalCandidate]: ...
