from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, SessionDependency
from app.schemas import ConversationCreate, ConversationDetail, ConversationOut
from app.services.conversations import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(user: CurrentUser, session: SessionDependency):
    return ConversationService(session).list_owned(user.id)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, user: CurrentUser, session: SessionDependency):
    return ConversationService(session).create(user.id, payload.title)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int, user: CurrentUser, session: SessionDependency):
    return ConversationService(session).require_owned(conversation_id, user.id, with_messages=True)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, user: CurrentUser, session: SessionDependency):
    ConversationService(session).delete(conversation_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
