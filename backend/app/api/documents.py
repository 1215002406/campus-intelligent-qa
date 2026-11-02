from pathlib import Path
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import (
    AdminUser,
    IngestionDependency,
    SessionDependency,
    SettingsDependency,
    VectorIndexDependency,
)
from app.schemas import (
    BatchUploadItem,
    BatchUploadResponse,
    DocumentDetail,
    DocumentOut,
    DocumentUpdate,
)
from app.services.documents import DocumentService

router = APIRouter(prefix="/admin/documents", tags=["admin documents"])
logger = logging.getLogger(__name__)

DocumentCategory = Literal["教务", "学工", "后勤", "跨部门"]
UploadCategory = Literal["自动", "教务", "学工", "后勤", "跨部门"]
MAX_BATCH_FILES = 20


@router.get("", response_model=list[DocumentOut])
def list_documents(
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
):
    return DocumentService(session, settings).list()


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    file: Annotated[UploadFile, File(description="PDF、DOCX、XLSX、CSV、TXT 或 Markdown 文档")],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    category: Annotated[UploadCategory, Form()],
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
    ingestion: IngestionDependency,
    overwrite: Annotated[bool, Form()] = False,
):
    if not title.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文档标题不能为空")
    result = DocumentService(session, settings).create_from_upload(file, title, category, overwrite)
    ingestion.submit(result.document.id)
    return result.document


@router.post("/batch", response_model=BatchUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_documents(
    files: Annotated[list[UploadFile], File(description="PDF、DOCX、XLSX、CSV、TXT 或 Markdown 文档")],
    category: Annotated[UploadCategory, Form()],
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
    ingestion: IngestionDependency,
    overwrite: Annotated[bool, Form()] = False,
):
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请至少选择一个文件")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"每次最多上传 {MAX_BATCH_FILES} 个文件")

    service = DocumentService(session, settings)
    items: list[BatchUploadItem] = []
    for upload in files:
        filename = Path((upload.filename or "").replace("\\", "/")).name
        title = Path(filename).stem.strip()[:200] or "未命名文档"
        try:
            result = service.create_from_upload(upload, title, category, overwrite)
            ingestion.submit(result.document.id)
            items.append(BatchUploadItem(
                filename=filename or "未命名文件",
                success=True,
                status_code=status.HTTP_202_ACCEPTED,
                document=DocumentOut.model_validate(result.document),
                overwritten=result.overwritten,
            ))
        except HTTPException as exc:
            items.append(BatchUploadItem(
                filename=filename or "未命名文件",
                success=False,
                status_code=exc.status_code,
                error=str(exc.detail),
            ))
        except Exception:
            items.append(BatchUploadItem(
                filename=filename or "未命名文件",
                success=False,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error="文件保存失败",
            ))

    accepted = sum(1 for item in items if item.success)
    return BatchUploadResponse(
        total=len(items),
        accepted=accepted,
        rejected=len(items) - accepted,
        items=items,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
):
    return DocumentService(session, settings).get(document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
):
    return DocumentService(session, settings).update_document(
        document_id,
        title=payload.title,
        category=payload.category,
    )


@router.post("/{document_id}/reindex", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def reindex_document(
    document_id: int,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
    ingestion: IngestionDependency,
):
    document = DocumentService(session, settings).prepare_reindex(document_id)
    ingestion.submit(document.id)
    return document


@router.post("/{document_id}/disable", response_model=DocumentOut)
def disable_document(
    document_id: int,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
):
    return DocumentService(session, settings).disable(document_id)


@router.post("/{document_id}/enable", response_model=DocumentOut)
def enable_document(
    document_id: int,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
):
    return DocumentService(session, settings).enable(document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    user: AdminUser,
    session: SessionDependency,
    settings: SettingsDependency,
    vector_index: VectorIndexDependency,
):
    DocumentService(session, settings).delete(document_id)
    if vector_index is not None:
        try:
            vector_index.delete_document(document_id)
        except Exception:
            logger.exception("Could not delete vectors for document %s", document_id)
    return None
