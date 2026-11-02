from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser, VectorIndexDependency
from app.schemas import (
    EmbeddingRebuildRequest,
    EmbeddingSwitchRequest,
    RetrievalHit,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    VectorIndexStatus,
)

router = APIRouter(prefix="/admin/retrieval", tags=["admin retrieval"])


def require_vector_index(vector_index):
    if vector_index is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "向量索引未启用")
    return vector_index


@router.get("/status", response_model=VectorIndexStatus)
def vector_index_status(user: AdminUser, vector_index: VectorIndexDependency):
    return require_vector_index(vector_index).status()


@router.post("/search", response_model=RetrievalSearchResponse)
def search(
    payload: RetrievalSearchRequest,
    user: AdminUser,
    vector_index: VectorIndexDependency,
):
    service = require_vector_index(vector_index)
    try:
        results = service.search(payload.question, payload.limit, payload.category)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "本地向量模型尚未就绪") from exc
    return {
        "profile": service.active_profile_id,
        "hits": [
            RetrievalHit(
                chunk_id=result.chunk.id,
                document_id=result.document.id,
                document_title=result.document.title,
                category=result.document.category,
                section_id=result.chunk.section_id,
                page_start=result.chunk.page_start,
                page_end=result.chunk.page_end,
                content=result.chunk.content,
                score=result.score,
                vector_score=result.vector_score,
                keyword_score=result.keyword_score,
            )
            for result in results
        ],
    }


@router.post("/rebuild", response_model=VectorIndexStatus, status_code=status.HTTP_202_ACCEPTED)
def rebuild(
    payload: EmbeddingRebuildRequest,
    user: AdminUser,
    vector_index: VectorIndexDependency,
):
    service = require_vector_index(vector_index)
    service.submit_rebuild([payload.profile] if payload.profile else None)
    return service.status()


@router.post("/switch", response_model=VectorIndexStatus)
def switch(
    payload: EmbeddingSwitchRequest,
    user: AdminUser,
    vector_index: VectorIndexDependency,
):
    service = require_vector_index(vector_index)
    try:
        return service.switch_profile(payload.profile)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
