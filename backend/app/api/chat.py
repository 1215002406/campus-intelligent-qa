import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    CurrentUser,
    LLMModelDependency,
    SessionDependency,
    VectorIndexDependency,
)
from app.schemas import ChatRequest
from app.services.conversations import ConversationService
from app.services.rag_chat import RagChatService

router = APIRouter(prefix="/chat", tags=["chat"])


def as_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    user: CurrentUser,
    session: SessionDependency,
    request: Request,
    vector_index: VectorIndexDependency,
    llm_model: LLMModelDependency,
):
    ConversationService(session).require_owned(payload.conversation_id, user.id)
    if vector_index is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "向量索引尚未启用")
    service = RagChatService(
        request.app.state.database.session_factory,
        request.app.state.settings,
        vector_index,
        llm_model,
    )

    async def events():
        async for event, data in service.stream(
            conversation_id=payload.conversation_id,
            question=payload.question,
            user_id=user.id,
        ):
            yield as_sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
