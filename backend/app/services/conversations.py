from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Conversation
from app.repositories import ConversationRepository


class ConversationService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ConversationRepository(session)

    def list_owned(self, user_id: int) -> list[Conversation]:
        return self.repository.list_owned(user_id)

    def create(self, user_id: int, title: str | None) -> Conversation:
        if title is None:
            existing = self.repository.find_empty_owned(user_id)
            if existing is not None:
                return existing
        conversation = self.repository.add(user_id, title)
        self.session.commit()
        return conversation

    def require_owned(self, conversation_id: int, user_id: int, *, with_messages: bool = False) -> Conversation:
        conversation = self.repository.get_owned(conversation_id, user_id, with_messages=with_messages)
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
        return conversation

    def delete(self, conversation_id: int, user_id: int) -> None:
        conversation = self.require_owned(conversation_id, user_id)
        self.repository.delete(conversation)
        self.session.commit()
