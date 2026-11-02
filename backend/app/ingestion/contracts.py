from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParsedSection:
    section_id: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class ChunkDraft:
    section_id: str
    chunk_index: int
    content: str
    page_start: int | None = None
    page_end: int | None = None


class DocumentParser(Protocol):
    def parse(self, path: Path) -> list[ParsedSection]: ...


class TextChunker(Protocol):
    rule_id: str

    def split(self, sections: list[ParsedSection]) -> list[ChunkDraft]: ...


class IngestionQueue(Protocol):
    """Future implementation: one worker; parsing/indexing outside MySQL write transactions."""

    def submit(self, document_id: int) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
