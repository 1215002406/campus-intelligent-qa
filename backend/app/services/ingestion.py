import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from sqlalchemy import delete, select

from app.core.config import PROJECT_ROOT, Settings
from app.ingestion.parsers import UniversalDocumentParser
from app.ingestion.text import CharacterTextChunker
from app.models import Chunk, Document

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, session_factory, settings: Settings, vector_index=None):
        self.session_factory = session_factory
        self.settings = settings
        self.vector_index = vector_index
        self.parser = UniversalDocumentParser()
        self.chunker = CharacterTextChunker()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-ingestion")
        self._futures: set[Future] = set()
        self._lock = Lock()

    def start(self) -> None:
        with self.session_factory() as session, session.begin():
            interrupted = session.scalars(select(Document).where(
                Document.status.in_(("parsing", "indexing"))
            )).all()
            for document in interrupted:
                document.status = "failed"
                document.error_message = "服务中断，请重新索引"
            pending_ids = list(session.scalars(select(Document.id).where(Document.status == "pending")))
        for document_id in pending_ids:
            self.submit(document_id)

    def submit(self, document_id: int) -> None:
        future = self._executor.submit(self._process, document_id)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def wait_idle(self) -> None:
        while True:
            with self._lock:
                pending = list(self._futures)
            if not pending:
                return
            for future in pending:
                future.result()

    def stop(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _discard_future(self, future: Future) -> None:
        with self._lock:
            self._futures.discard(future)

    def _process(self, document_id: int) -> None:
        index_version = f"idx-{uuid.uuid4().hex}"
        try:
            with self.session_factory() as session, session.begin():
                document = session.get(Document, document_id)
                if document is None or document.status != "pending":
                    return
                document.status = "parsing"
                document.error_message = None
                source_path = self._source_path(document)
                original_name = document.original_name

            sections = self.parser.parse(source_path)
            drafts = self.chunker.split(sections)
            if not drafts:
                raise ValueError("文档没有生成有效切片")

            with self.session_factory() as session, session.begin():
                document = session.get(Document, document_id)
                if document is None:
                    return
                document.status = "indexing"

            with self.session_factory() as session, session.begin():
                document = session.get(Document, document_id)
                if document is None:
                    return
                session.execute(delete(Chunk).where(
                    Chunk.document_id == document_id,
                    Chunk.index_version == index_version,
                ))
                chunks = [
                    Chunk(
                        document_id=document_id,
                        index_version=index_version,
                        section_id=draft.section_id,
                        chunk_index=draft.chunk_index,
                        content=draft.content,
                        page_start=draft.page_start,
                        page_end=draft.page_end,
                        metadata_json={
                            "original_name": original_name,
                            "chunk_rule_id": self.chunker.rule_id,
                        },
                    )
                    for draft in drafts
                ]
                session.add_all(chunks)
                document.error_message = None
                session.flush()

            if self.vector_index is not None:
                self.vector_index.index_snapshot(document, chunks, index_version)

            with self.session_factory() as session, session.begin():
                document = session.get(Document, document_id)
                if document is None:
                    raise RuntimeError("Document disappeared during indexing")
                document.status = "ready"
                document.index_version = index_version
                document.error_message = None
                session.execute(delete(Chunk).where(
                    Chunk.document_id == document_id,
                    Chunk.index_version != index_version,
                ))
            if self.vector_index is not None:
                try:
                    self.vector_index.finalize_snapshot(document_id, index_version)
                    self.vector_index.invalidate_keyword_index()
                except Exception:
                    logger.exception("Could not remove obsolete vectors for %s", document_id)
        except Exception as exc:
            logger.exception("Document ingestion failed for %s", document_id)
            if self.vector_index is not None:
                try:
                    self.vector_index.rollback_snapshot(document_id, index_version)
                except Exception:
                    logger.exception("Could not remove failed vectors for %s", document_id)
            try:
                with self.session_factory() as session, session.begin():
                    session.execute(delete(Chunk).where(
                        Chunk.document_id == document_id,
                        Chunk.index_version == index_version,
                    ))
                    document = session.get(Document, document_id)
                    if document is not None:
                        document.status = "failed"
                        document.error_message = str(exc)[:1000] or "文档处理失败"
            except Exception:
                logger.exception("Could not record ingestion failure for %s", document_id)

    def _source_path(self, document: Document) -> Path:
        path = Path(document.stored_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        resolved = path.resolve()
        upload_root = self.settings.upload_dir.resolve()
        if not resolved.is_relative_to(upload_root) or not resolved.is_file():
            raise ValueError("原始文件不存在或路径无效")
        return resolved
