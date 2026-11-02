from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Conversation, Message
from app.models.base import utc_now


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_owned(self, user_id: int) -> list[Conversation]:
        return list(self.session.scalars(
            select(Conversation).where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        ))

    def get_owned(self, conversation_id: int, user_id: int, *, with_messages: bool = False) -> Conversation | None:
        query = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        if with_messages:
            query = query.options(selectinload(Conversation.messages))
        return self.session.scalar(query)

    def add(self, user_id: int, title: str | None) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title or "新会话")
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def find_empty_owned(self, user_id: int) -> Conversation | None:
        with_messages = select(Message.conversation_id).distinct()
        return self.session.scalar(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.title == "新会话",
                Conversation.id.not_in(with_messages),
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(1)
        )

    def delete(self, conversation: Conversation) -> None:
        self.session.delete(conversation)


class MessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_completed_recent(self, conversation_id: int, limit: int = 6) -> list[Message]:
        result = list(self.session.scalars(
            select(Message).where(Message.conversation_id == conversation_id, Message.status == "completed")
            .order_by(Message.id.desc()).limit(limit)
        ))
        return list(reversed(result))

    def add(self, conversation: Conversation, *, role: str, content: str, status: str = "completed",
            sources: list[dict] | None = None) -> Message:
        message = Message(conversation_id=conversation.id, role=role, content=content,
                          status=status, sources_json=sources or [])
        if role == "user" and conversation.title == "新会话":
            conversation.title = content[:30]
        conversation.updated_at = utc_now()
        self.session.add(message)
        self.session.flush()
        return message
