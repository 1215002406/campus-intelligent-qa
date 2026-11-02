from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Chunk, Document


class DocumentRepository:
    """Persistence primitives; ingestion state transitions belong in a future service."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, document_id: int) -> Document | None:
        return self.session.scalar(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
        )

    def list_all(self) -> list[Document]:
        return list(self.session.scalars(
            select(Document)
            .options(selectinload(Document.chunks))
            .order_by(Document.created_at.desc(), Document.id.desc())
        ))

    def get_by_sha256(self, digest: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.sha256 == digest))

    def get_by_original_name(self, original_name: str) -> Document | None:
        return self.session.scalar(
            select(Document)
            .where(func.lower(Document.original_name) == original_name.casefold())
            .order_by(Document.updated_at.desc(), Document.id.desc())
        )

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document

    def delete(self, document: Document) -> None:
        self.session.delete(document)


class ChunkRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_current_ready(self) -> list[Chunk]:
        return list(self.session.scalars(
            select(Chunk).join(Document).where(
                Document.status == "ready", Document.index_version == Chunk.index_version
            ).order_by(Chunk.document_id, Chunk.chunk_index, Chunk.id)
        ))

    def add_many(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)
        self.session.flush()
