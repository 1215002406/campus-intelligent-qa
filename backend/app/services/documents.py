import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings
from app.models import Document
from app.repositories import DocumentRepository
from app.services.classification import classify_document

logger = logging.getLogger(__name__)
ALLOWED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".markdown", ".csv"}
PROCESSING_STATUSES = {"pending", "parsing", "indexing"}


@dataclass(frozen=True)
class UploadResult:
    document: Document
    overwritten: bool


class DocumentService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self.repository = DocumentRepository(session)

    def list(self) -> list[Document]:
        return self.repository.list_all()

    def get(self, document_id: int) -> Document:
        document = self.repository.get(document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
        return document

    def update_document(self, document_id: int, *, title: str | None, category: str | None) -> Document:
        document = self.get(document_id)
        if title is not None:
            document.title = title
        if category is not None:
            document.category = category
        self.session.commit()
        return document

    def create_from_upload(
        self,
        upload: UploadFile,
        title: str,
        category: str,
        overwrite: bool = False,
    ) -> UploadResult:
        original_name = PurePosixPath((upload.filename or "").replace("\\", "/")).name[:255]
        suffix = Path(original_name).suffix.lower()
        if not original_name or suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "支持 PDF、DOCX、XLSX、CSV、TXT 和 Markdown 文档",
            )
        existing_name = self.repository.get_by_original_name(original_name)
        if existing_name is not None and not overwrite:
            raise HTTPException(status.HTTP_409_CONFLICT, "知识库中已存在同名文档，请选择是否覆盖")
        if existing_name is not None and existing_name.status in PROCESSING_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, "同名文档正在处理中，暂时不能覆盖")

        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{secrets.token_hex(16)}{suffix}"
        final_path = self.settings.upload_dir / stored_name
        temporary_path = self.settings.upload_dir / f".{stored_name}.uploading"
        digest = hashlib.sha256()
        total = 0
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        try:
            with temporary_path.open("wb") as target:
                while chunk := upload.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"文件不能超过 {self.settings.max_upload_mb} MB",
                        )
                    digest.update(chunk)
                    target.write(chunk)
            if total == 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能上传空文件")

            sha256 = digest.hexdigest()
            sha_owner = self.repository.get_by_sha256(sha256)
            if sha_owner is not None and (existing_name is None or sha_owner.id != existing_name.id):
                raise HTTPException(status.HTTP_409_CONFLICT, "相同内容的文档已经存在")
            os.replace(temporary_path, final_path)

            actual_category = classify_document(title, original_name) if category == "自动" else category
            if existing_name is not None:
                document = existing_name
                old_path = Path(document.stored_path)
                if not old_path.is_absolute():
                    old_path = PROJECT_ROOT / old_path
                document.title = title.strip()
                document.category = actual_category
                document.stored_path = self._stored_path(final_path)
                document.sha256 = sha256
                document.status = "pending"
                document.error_message = None
                overwritten = True
            else:
                old_path = None
                document = Document(
                    document_code=self._new_document_code(),
                    title=title.strip(),
                    category=actual_category,
                    original_name=original_name,
                    stored_path=self._stored_path(final_path),
                    sha256=sha256,
                    status="pending",
                )
                self.repository.add(document)
                overwritten = False
            self.session.commit()
            if overwritten and old_path is not None:
                resolved_old = old_path.resolve()
                if resolved_old.is_relative_to(self.settings.upload_dir.resolve()):
                    try:
                        resolved_old.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Could not delete replaced source file %s", resolved_old)
            return UploadResult(document=document, overwritten=overwritten)
        except IntegrityError as exc:
            self.session.rollback()
            final_path.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_409_CONFLICT, "相同内容的文档已经存在") from exc
        except Exception:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise

    def disable(self, document_id: int) -> Document:
        document = self.get(document_id)
        if document.status != "ready":
            raise HTTPException(status.HTTP_409_CONFLICT, "只有可用文档可以停用")
        document.status = "disabled"
        self.session.commit()
        return document

    def enable(self, document_id: int) -> Document:
        document = self.get(document_id)
        if document.status != "disabled":
            raise HTTPException(status.HTTP_409_CONFLICT, "只有已停用文档可以启用")
        if not document.index_version:
            raise HTTPException(status.HTTP_409_CONFLICT, "文档尚未完成索引，请重新索引")
        document.status = "ready"
        document.error_message = None
        self.session.commit()
        return document

    def prepare_reindex(self, document_id: int) -> Document:
        document = self.get(document_id)
        if document.status not in {"ready", "disabled", "failed"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "文档正在处理中，暂时不能重新索引")
        document.status = "pending"
        document.error_message = None
        self.session.commit()
        return document

    def delete(self, document_id: int) -> None:
        document = self.get(document_id)
        if document.status in {"parsing", "indexing"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "文档正在处理中，暂时不能删除")
        path = Path(document.stored_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        resolved = path.resolve()
        self.session.delete(document)
        self.session.commit()
        if resolved.is_relative_to(self.settings.upload_dir.resolve()):
            try:
                resolved.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete source file %s", resolved)

    def _stored_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    @staticmethod
    def _new_document_code() -> str:
        return f"DOC-{secrets.token_hex(8).upper()}"
