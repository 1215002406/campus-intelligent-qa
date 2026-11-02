from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["system", "user", "assistant"]
    content: str


class GenerationModel(Protocol):
    model_id: str

    def stream(self, messages: Sequence[ChatTurn]) -> AsyncIterator[str]: ...
    async def complete(self, messages: Sequence[ChatTurn]) -> str: ...


class EmbeddingModel(Protocol):
    model_id: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
