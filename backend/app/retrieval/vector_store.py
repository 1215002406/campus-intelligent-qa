from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.models import Chunk
from app.retrieval.embeddings import EmbeddingProfile


@dataclass(frozen=True)
class VectorHit:
    chunk_id: int
    document_id: int
    index_version: str
    score: float


class ChromaVectorStore:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))

    def collection(self, profile: EmbeddingProfile):
        return self.client.get_or_create_collection(
            name=profile.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": profile.model_name,
                "dimensions": profile.dimensions,
            },
            embedding_function=None,
        )

    def upsert(
        self,
        profile: EmbeddingProfile,
        document_id: int,
        index_version: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")
        collection = self.collection(profile)
        for start in range(0, len(chunks), 100):
            batch_chunks = chunks[start:start + 100]
            batch_vectors = vectors[start:start + 100]
            collection.upsert(
                ids=[str(chunk.id) for chunk in batch_chunks],
                embeddings=batch_vectors,
                metadatas=[{
                    "document_id": document_id,
                    "index_version": index_version,
                    "section_id": chunk.section_id,
                    "chunk_index": chunk.chunk_index,
                } for chunk in batch_chunks],
            )

    def delete_other_versions(
        self,
        profile: EmbeddingProfile,
        document_id: int,
        index_version: str,
    ) -> None:
        self.collection(profile).delete(where={
            "$and": [
                {"document_id": document_id},
                {"index_version": {"$ne": index_version}},
            ],
        })

    def delete_version(
        self,
        profile: EmbeddingProfile,
        document_id: int,
        index_version: str,
    ) -> None:
        self.collection(profile).delete(where={
            "$and": [
                {"document_id": document_id},
                {"index_version": index_version},
            ],
        })

    def delete_document(self, profile: EmbeddingProfile, document_id: int) -> None:
        self.collection(profile).delete(where={"document_id": document_id})

    def document_ids(self, profile: EmbeddingProfile, document_id: int, index_version: str) -> set[int]:
        result = self.collection(profile).get(
            where={
                "$and": [
                    {"document_id": document_id},
                    {"index_version": index_version},
                ],
            },
            include=[],
        )
        return {int(identifier) for identifier in result.get("ids", [])}

    def query(
        self,
        profile: EmbeddingProfile,
        query_vector: list[float],
        limit: int = 20,
    ) -> list[VectorHit]:
        result = self.collection(profile).query(
            query_embeddings=[query_vector],
            n_results=limit,
            include=["metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        hits = []
        for identifier, metadata, distance in zip(ids, metadatas, distances):
            hits.append(VectorHit(
                chunk_id=int(identifier),
                document_id=int(metadata["document_id"]),
                index_version=str(metadata["index_version"]),
                score=1.0 - float(distance),
            ))
        return hits

    def count(self, profile: EmbeddingProfile) -> int:
        return self.collection(profile).count()

    def chunk_ids(self, profile: EmbeddingProfile) -> set[int]:
        result = self.collection(profile).get(include=[])
        return {int(identifier) for identifier in result.get("ids", [])}
