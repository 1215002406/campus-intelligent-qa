import json
import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from threading import Lock

import jieba
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from rank_bm25 import BM25Okapi

from app.core.config import Settings
from app.models import Chunk, Document
from app.retrieval.embeddings import EmbeddingProfile, LocalEmbeddingModels
from app.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)
jieba.setLogLevel(logging.ERROR)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: Chunk
    document: Document
    score: float
    vector_score: float
    keyword_score: float


class VectorIndexService:
    def __init__(self, session_factory, settings: Settings):
        self.session_factory = session_factory
        self.settings = settings
        self.embeddings = LocalEmbeddingModels(settings)
        self.store = ChromaVectorStore(settings.chroma_dir)
        self._active_file = settings.chroma_dir / "active-profile.json"
        self._active_profile_id = self._load_active_profile()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vector-index")
        self._futures: set[Future] = set()
        self._futures_lock = Lock()
        self._progress_lock = Lock()
        self._progress = {
            "state": "idle",
            "completed": 0,
            "total": 0,
            "message": "",
            "started_at": None,
            "finished_at": None,
        }
        self._keyword_lock = Lock()
        self._keyword_index: BM25Okapi | None = None
        self._keyword_chunk_ids: list[int] = []

    @property
    def profiles(self) -> dict[str, EmbeddingProfile]:
        return self.embeddings.profiles

    @property
    def active_profile_id(self) -> str:
        return self._active_profile_id

    @property
    def active_profile(self) -> EmbeddingProfile:
        return self.embeddings.profile(self._active_profile_id)

    def index_snapshot(
        self,
        document: Document,
        chunks: list[Chunk],
        index_version: str,
        profile_ids: list[str] | None = None,
    ) -> None:
        if not chunks:
            raise ValueError("Document has no chunks to index")
        selected = profile_ids or list(self.profiles)
        for profile_id in selected:
            profile = self.profiles[profile_id]
            vectors = self.embeddings.encode_documents(profile_id, [chunk.content for chunk in chunks])
            self.store.upsert(profile, document.id, index_version, chunks, vectors)
            actual = self.store.document_ids(profile, document.id, index_version)
            expected = {chunk.id for chunk in chunks}
            if actual != expected:
                raise RuntimeError(f"Vector count verification failed for {profile_id}")

    def finalize_snapshot(self, document_id: int, index_version: str) -> None:
        for profile in self.profiles.values():
            self.store.delete_other_versions(profile, document_id, index_version)

    def rollback_snapshot(self, document_id: int, index_version: str) -> None:
        for profile in self.profiles.values():
            self.store.delete_version(profile, document_id, index_version)

    def delete_document(self, document_id: int) -> None:
        for profile in self.profiles.values():
            self.store.delete_document(profile, document_id)
        self.invalidate_keyword_index()

    def invalidate_keyword_index(self) -> None:
        with self._keyword_lock:
            self._keyword_index = None
            self._keyword_chunk_ids = []

    def start_backfill(self) -> None:
        if self.settings.vector_backfill_on_startup:
            self.submit_rebuild(missing_only=True)

    def submit_rebuild(
        self,
        profile_ids: list[str] | None = None,
        *,
        missing_only: bool = False,
    ) -> None:
        with self._progress_lock:
            if self._progress["state"] in {"queued", "running"}:
                return
            self._progress = {
                "state": "queued",
                "completed": 0,
                "total": 0,
                "message": "等待重建向量索引",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            }
        future = self._executor.submit(self._rebuild_all, profile_ids, missing_only)
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def wait_idle(self) -> None:
        while True:
            with self._futures_lock:
                pending = list(self._futures)
            if not pending:
                return
            for future in pending:
                future.result()

    def stop(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def status(self) -> dict:
        with self.session_factory() as session:
            expected_ids = set(session.scalars(
                select(Chunk.id)
                .join(Document)
                .where(Document.status == "ready", Document.index_version == Chunk.index_version)
            ))
        profile_status = []
        for profile in self.profiles.values():
            indexed = self.store.chunk_ids(profile)
            profile_status.append({
                "id": profile.id,
                "label": profile.label,
                "model": profile.model_name,
                "dimensions": profile.dimensions,
                "indexed_chunks": len(indexed),
                "expected_chunks": len(expected_ids),
                "ready": expected_ids.issubset(indexed),
                "active": profile.id == self._active_profile_id,
            })
        with self._progress_lock:
            progress = dict(self._progress)
        return {"active_profile": self._active_profile_id, "profiles": profile_status, "progress": progress}

    def switch_profile(self, profile_id: str) -> dict:
        if profile_id not in self.profiles:
            raise ValueError("Unknown embedding profile")
        state = self.status()
        profile = next((item for item in state["profiles"] if item["id"] == profile_id), None)
        if profile is None or not profile["ready"]:
            raise RuntimeError("The selected embedding index is incomplete")
        self._active_profile_id = profile_id
        self.settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(
            json.dumps({"active_profile": profile_id}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.status()

    def search(self, question: str, limit: int = 5, category: str | None = None) -> list[RetrievalResult]:
        profile = self.active_profile
        query_vector = self.embeddings.encode_query(profile.id, question)
        vector_hits = self.store.query(profile, query_vector, limit=max(limit * 4, 20))
        keyword_scores = self._keyword_scores(question, limit=max(limit * 4, 20))
        vector_scores = {hit.chunk_id: hit.score for hit in vector_hits}
        keyword_rank = {chunk_id: score for chunk_id, score in keyword_scores}
        fused: dict[int, float] = {}
        for rank, hit in enumerate(vector_hits):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (60 + rank + 1)
        for rank, (chunk_id, _score) in enumerate(keyword_scores):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank + 1)
        if not fused:
            return []
        ids = list(fused)
        with self.session_factory() as session:
            query = (
                select(Chunk)
                .join(Document)
                .options(selectinload(Chunk.document))
                .where(
                    Chunk.id.in_(ids),
                    Chunk.index_version == Document.index_version,
                    Document.status == "ready",
                )
            )
            if category:
                query = query.where(Document.category == category)
            chunks = {chunk.id: chunk for chunk in session.scalars(query)}
        candidates = []
        for chunk_id in sorted(fused, key=fused.get, reverse=True):
            chunk = chunks.get(chunk_id)
            if chunk is not None:
                candidates.append(RetrievalResult(
                    chunk=chunk,
                    document=chunk.document,
                    score=fused[chunk_id],
                    vector_score=vector_scores.get(chunk_id, 0.0),
                    keyword_score=keyword_rank.get(chunk_id, 0.0),
                ))
        return self._deduplicate_results(candidates, limit)

    @classmethod
    def _deduplicate_results(
        cls,
        candidates: list[RetrievalResult],
        limit: int,
    ) -> list[RetrievalResult]:
        results = []
        seen_content: list[str] = []
        for candidate in candidates:
            normalized = cls._normalize_for_deduplication(candidate.chunk.content)
            if any(
                SequenceMatcher(None, normalized, existing).ratio() >= 0.92
                for existing in seen_content
            ):
                continue
            results.append(candidate)
            seen_content.append(normalized)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _normalize_for_deduplication(content: str) -> str:
        normalized = re.sub(r"工作表：.*|CSV\s*表格", "", content, flags=re.IGNORECASE)
        normalized = re.sub(
            r"FAQ_ID：|分类：|问题：|答案：|关键词：|生效日期：|来源文档：|来源章节：|启用：|True|False|是|否",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        return re.sub(r"[\W_]+", "", normalized).lower()

    def _keyword_scores(self, question: str, limit: int) -> list[tuple[int, float]]:
        with self._keyword_lock:
            if self._keyword_index is None:
                with self.session_factory() as session:
                    chunks = list(session.scalars(
                        select(Chunk)
                        .join(Document)
                        .where(Document.status == "ready", Document.index_version == Chunk.index_version)
                        .order_by(Chunk.id)
                    ))
                self._keyword_chunk_ids = [chunk.id for chunk in chunks]
                tokenized = [self._tokens(chunk.content) for chunk in chunks]
                self._keyword_index = BM25Okapi(tokenized) if tokenized else None
            index = self._keyword_index
            chunk_ids = list(self._keyword_chunk_ids)
        if index is None or not chunk_ids:
            return []
        scores = index.get_scores(self._tokens(question))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return [
            (chunk_ids[index], float(score))
            for index, score in ranked[:limit]
            if score > 0
        ]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [
            token.lower()
            for token in jieba.lcut(text)
            if token.strip() and not token.isspace()
        ]

    def _rebuild_all(self, profile_ids: list[str] | None, missing_only: bool) -> None:
        selected = profile_ids or list(self.profiles)
        with self.session_factory() as session:
            documents = list(session.execute(
                select(Document.id, Chunk.id)
                .join(Chunk, Chunk.document_id == Document.id)
                .where(Document.status == "ready", Document.index_version == Chunk.index_version)
                .order_by(Document.id, Chunk.id)
            ))
        document_chunks: dict[int, set[int]] = {}
        for document_id, chunk_id in documents:
            document_chunks.setdefault(document_id, set()).add(chunk_id)
        if missing_only:
            existing = {profile_id: self.store.chunk_ids(self.profiles[profile_id]) for profile_id in selected}
            document_ids = [
                document_id for document_id, chunk_ids in document_chunks.items()
                if any(not chunk_ids.issubset(existing[profile_id]) for profile_id in selected)
            ]
        else:
            document_ids = list(document_chunks)
        with self._progress_lock:
            self._progress.update({
                "state": "running",
                "completed": 0,
                "total": len(document_ids),
                "message": "正在重建向量索引",
            })
        try:
            for index, document_id in enumerate(document_ids, start=1):
                self._index_ready_document(document_id, selected)
                with self._progress_lock:
                    self._progress["completed"] = index
            with self._progress_lock:
                self._progress.update({
                    "state": "completed",
                    "message": "向量索引重建完成",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as exc:
            logger.exception("Vector index rebuild failed")
            with self._progress_lock:
                self._progress.update({
                    "state": "failed",
                    "message": str(exc)[:500] or "向量索引重建失败",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })

    def _index_ready_document(self, document_id: int, profile_ids: list[str]) -> None:
        with self.session_factory() as session:
            document = session.scalar(
                select(Document)
                .options(selectinload(Document.chunks))
                .where(Document.id == document_id, Document.status == "ready")
            )
            if document is None or not document.index_version:
                return
            chunks = [
                chunk for chunk in document.chunks
                if chunk.index_version == document.index_version
            ]
            if not chunks:
                return
            session.expunge_all()
            for profile_id in profile_ids:
                profile = self.profiles[profile_id]
                vectors = self.embeddings.encode_documents(profile_id, [chunk.content for chunk in chunks])
                self.store.upsert(profile, document.id, document.index_version, chunks, vectors)

    def _load_active_profile(self) -> str:
        default = self.settings.embedding_profile
        try:
            data = json.loads(self._active_file.read_text(encoding="utf-8"))
            candidate = data.get("active_profile")
            return candidate if candidate in self.profiles else default
        except (FileNotFoundError, ValueError, OSError):
            return default

    def _discard_future(self, future: Future) -> None:
        with self._futures_lock:
            self._futures.discard(future)
