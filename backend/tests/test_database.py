import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Chunk, Conversation, Document, Message, User
from app.repositories import ChunkRepository, ConversationRepository, MessageRepository, UserRepository


def make_document(**overrides):
    fields = dict(document_code="DOC-01", title="校园资料", category="教务", original_name="file.txt",
                  stored_path="safe-random-name.txt", sha256="a" * 64, status="ready", index_version="v1")
    fields.update(overrides)
    return Document(**fields)


def test_mysql_schema_and_connection_settings(client, application):
    engine = application.state.database.engine
    assert set(inspect(engine).get_table_names()) == {"users", "conversations", "messages", "documents", "chunks"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT VERSION()")).startswith("8.4.")
        assert connection.scalar(text("SELECT @@character_set_connection")) == "utf8mb4"
        assert connection.scalar(text("SELECT @@collation_connection")) == "utf8mb4_0900_ai_ci"
        assert connection.scalar(text("SELECT @@transaction_isolation")) == "READ-COMMITTED"
        assert connection.scalar(text("SELECT @@time_zone")) == "+00:00"


def test_normalized_username_unique_constraint(client, application):
    with application.state.database.session_factory() as session:
        with pytest.raises(IntegrityError):
            UserRepository(session).add(username=" student ", password_hash="not-a-login", role="student")
        session.rollback()
        user = UserRepository(session).add(username=" second ", password_hash="not-a-login", role="student")
        assert user.username == "second"


def test_foreign_keys_and_user_cascade(client, application):
    with application.state.database.session_factory() as session:
        session.add(Conversation(user_id=99999, title="invalid"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        user = UserRepository(session).add(username="disposable", password_hash="not-a-login", role="student")
        conversation = ConversationRepository(session).add(user.id, None)
        message = MessageRepository(session).add(conversation, role="user", content="hello")
        user_id, conversation_id, message_id = user.id, conversation.id, message.id
        session.commit()
    with application.state.database.session_factory() as session, session.begin():
        session.delete(session.get(User, user_id))
    with application.state.database.session_factory() as session:
        assert session.get(Conversation, conversation_id) is None
        assert session.get(Message, message_id) is None


def test_chunk_uniqueness_versions_and_history_snapshot(client, application):
    with application.state.database.session_factory() as session, session.begin():
        document = make_document()
        session.add(document)
        session.flush()
        for version in ("v1", "v2"):
            session.add(Chunk(document_id=document.id, index_version=version, section_id="A-1", chunk_index=0, content="原文"))
        session.flush()
        current = ChunkRepository(session).list_current_ready()
        assert len(current) == 1 and current[0].index_version == "v1"
        conversation = ConversationRepository(session).add(UserRepository(session).get_by_username("student").id, None)
        snapshot = {"citation_id": 1, "chunk_id": current[0].id, "document_code": document.document_code,
                    "document_title": document.title, "section_id": "A-1", "excerpt": "原文", "page_start": None, "page_end": None}
        message = MessageRepository(session).add(conversation, role="assistant", content="回答[1]", sources=[snapshot])
        document_id, message_id = document.id, message.id
    with application.state.database.session_factory() as session:
        session.add(Chunk(document_id=document_id, index_version="v1", section_id="A-1", chunk_index=0, content="重复"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.get(Document, document_id).status = "disabled"
        session.commit()
        assert ChunkRepository(session).list_current_ready() == []
        session.delete(session.get(Document, document_id))
        session.commit()
    with application.state.database.session_factory() as session:
        assert list(session.scalars(select(Chunk))) == []
        assert session.get(Message, message_id).sources_json == [snapshot]


@pytest.mark.parametrize("model", [
    lambda: User(username=" bad ", password_hash="hash", role="student"),
    lambda: User(username="bad-role", password_hash="hash", role="root"),
    lambda: make_document(status="invalid"),
    lambda: make_document(category="invalid"),
])
def test_database_rejects_invalid_states(client, application, model):
    with application.state.database.session_factory() as session:
        session.add(model())
        with pytest.raises(DBAPIError):
            session.commit()
