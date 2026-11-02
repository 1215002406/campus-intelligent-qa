import pytest

from app.models import Chunk, Document, Message
from app.repositories import ConversationRepository, MessageRepository
from app.services.vector_index import RetrievalResult


def test_conversation_crud_and_message_detail(client, application, headers):
    auth = headers()
    assert client.get("/api/conversations", headers=auth).json() == []
    created = client.post("/api/conversations", json={}, headers=auth)
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["title"] == "新会话"
    conversation_id = conversation["id"]
    with application.state.database.session_factory() as session, session.begin():
        owned = ConversationRepository(session).get_owned(conversation_id, conversation["user_id"])
        MessageRepository(session).add(owned, role="user", content="图书馆周末开放吗？")
    detail = client.get(f"/api/conversations/{conversation_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["title"] == "图书馆周末开放吗？"
    assert detail.json()["messages"][0]["content"] == "图书馆周末开放吗？"
    assert detail.json()["messages"][0]["sources_json"] == []
    assert client.get("/api/conversations", headers=auth).json()[0]["id"] == conversation_id
    deleted = client.delete(f"/api/conversations/{conversation_id}", headers=auth)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/conversations/{conversation_id}", headers=auth).status_code == 404
    with application.state.database.session_factory() as session:
        assert session.get(Message, detail.json()["messages"][0]["id"]) is None


def test_blank_conversation_is_reused_until_first_message(client, application, headers):
    auth = headers()
    first = client.post("/api/conversations", json={}, headers=auth).json()
    second = client.post("/api/conversations", json={}, headers=auth).json()
    assert second["id"] == first["id"]
    assert len(client.get("/api/conversations", headers=auth).json()) == 1

    with application.state.database.session_factory() as session, session.begin():
        conversation = ConversationRepository(session).get_owned(first["id"], first["user_id"])
        MessageRepository(session).add(conversation, role="user", content="第一条问题")
    third = client.post("/api/conversations", json={}, headers=auth).json()
    assert third["id"] != first["id"]
    assert len(client.get("/api/conversations", headers=auth).json()) == 2


@pytest.mark.parametrize("owner,visitor", [("student", "admin"), ("admin", "student")])
def test_all_conversation_actions_enforce_owner(client, headers, owner, visitor):
    own_auth, other_auth = headers(owner), headers(visitor)
    owned = client.post("/api/conversations", json={"title": "  私有会话  "}, headers=own_auth).json()
    conversation_id = owned["id"]
    assert owned["title"] == "私有会话"
    assert client.get("/api/conversations", headers=other_auth).json() == []
    for resource_id in (conversation_id, 99999):
        detail = client.get(f"/api/conversations/{resource_id}", headers=other_auth)
        deletion = client.delete(f"/api/conversations/{resource_id}", headers=other_auth)
        chat = client.post("/api/chat/stream", json={"conversation_id": resource_id, "question": "你好"}, headers=other_auth)
        assert [detail.status_code, deletion.status_code, chat.status_code] == [404, 404, 404]
        assert detail.json() == deletion.json() == chat.json() == {"detail": "会话不存在"}
    assert client.get(f"/api/conversations/{conversation_id}", headers=own_auth).status_code == 200


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/conversations", None), ("POST", "/api/conversations", {}),
    ("GET", "/api/conversations/1", None), ("DELETE", "/api/conversations/1", None),
    ("POST", "/api/chat/stream", {"conversation_id": 1, "question": "你好"}),
])
def test_all_conversation_routes_require_login(client, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


def test_chat_streams_answer_sources_and_persists_messages(client, application, headers):
    auth = headers()
    conversation = client.post("/api/conversations", json={}, headers=auth).json()
    with application.state.database.session_factory() as session, session.begin():
        document = Document(
            document_code="DOC-CHAT-01",
            title="校园卡指南",
            category="后勤",
            original_name="card.md",
            stored_path="uploads/card.md",
            sha256="c" * 64,
            status="ready",
            index_version="idx-chat",
        )
        session.add(document)
        session.flush()
        chunk = Chunk(
            document_id=document.id,
            index_version="idx-chat",
            section_id="HQ-01",
            chunk_index=0,
            content="校园卡遗失后应立即挂失，再携带身份证到服务大厅补办。",
        )
        session.add(chunk)
        session.flush()
        result = RetrievalResult(
            chunk=chunk,
            document=document,
            score=0.03,
            vector_score=0.8,
            keyword_score=5.0,
        )

    class FakeVectorIndex:
        active_profile_id = "fake"

        def search(self, question, limit, category=None):
            return [result]

    class FakeModel:
        messages = None

        async def stream(self, messages):
            self.messages = messages
            yield "校园卡遗失后应先挂失，"
            yield "再携带身份证到服务大厅补办。[1]"

    application.state.vector_index = FakeVectorIndex()
    application.state.llm_model = FakeModel()
    response = client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation["id"], "question": "校园卡丢了怎么办？"},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: sources" in response.text
    assert "event: message" in response.text
    assert "event: done" in response.text
    assert "校园卡遗失后应先挂失" in response.text

    detail = client.get(f"/api/conversations/{conversation['id']}", headers=auth).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["status"] == "completed"
    assert detail["messages"][1]["sources_json"][0]["section_id"] == "HQ-01"
    assert detail["messages"][1]["content"].endswith("[1]")
    assert "校园资料" in application.state.llm_model.messages[1]["content"]
    assert client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation["id"], "question": "  "},
        headers=auth,
    ).status_code == 422


def test_chat_rewrites_followup_using_recent_history(client, application, headers):
    auth = headers()
    conversation = client.post("/api/conversations", json={}, headers=auth).json()
    with application.state.database.session_factory() as session, session.begin():
        owned = ConversationRepository(session).get_owned(conversation["id"], conversation["user_id"])
        messages = MessageRepository(session)
        messages.add(owned, role="user", content="国家助学金如何申请？")
        messages.add(owned, role="assistant", content="资料中没有国家助学金的具体流程。")
        document = Document(
            document_code="DOC-CHAT-02",
            title="奖助指南",
            category="学工",
            original_name="aid.md",
            stored_path="uploads/aid.md",
            sha256="d" * 64,
            status="ready",
            index_version="idx-aid",
        )
        session.add(document)
        session.flush()
        chunk = Chunk(
            document_id=document.id,
            index_version="idx-aid",
            section_id="XG-01",
            chunk_index=0,
            content="资料列出了助学成才金、临时困难补助和勤工助学项目。",
        )
        session.add(chunk)
        session.flush()
        result = RetrievalResult(chunk=chunk, document=document, score=0.03, vector_score=0.8, keyword_score=5.0)

    class FakeVectorIndex:
        active_profile_id = "fake"

        def __init__(self):
            self.queries = []

        def search(self, question, limit, category=None):
            self.queries.append(question)
            return [result]

    class FakeModel:
        rewrite_messages = None
        answer_messages = None

        async def complete(self, messages, **kwargs):
            self.rewrite_messages = messages
            return "介绍知识库中已有的奖助学金项目"

        async def stream(self, messages):
            self.answer_messages = messages
            yield "资料中已有助学成才金、临时困难补助和勤工助学项目。[1]"

    vector = FakeVectorIndex()
    model = FakeModel()
    application.state.vector_index = vector
    application.state.llm_model = model
    response = client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation["id"], "question": "介绍一下资料已有的"},
        headers=auth,
    )
    assert response.status_code == 200
    assert vector.queries == ["介绍知识库中已有的奖助学金项目"]
    assert "国家助学金如何申请？" in model.rewrite_messages[1]["content"]
    assert any(
        message["role"] == "assistant" and "国家助学金" in message["content"]
        for message in model.answer_messages
    )
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=auth).json()
    assert len(detail["messages"]) == 4
    assert detail["messages"][-1]["content"].endswith("[1]")


def test_chat_rejects_invalid_citation_ids(client, application, headers):
    auth = headers()
    conversation = client.post("/api/conversations", json={}, headers=auth).json()
    with application.state.database.session_factory() as session, session.begin():
        document = Document(
            document_code="DOC-CITATION-01",
            title="引用测试",
            category="教务",
            original_name="citation.md",
            stored_path="uploads/citation.md",
            sha256="e" * 64,
            status="ready",
            index_version="idx-citation",
        )
        session.add(document)
        session.flush()
        chunk = Chunk(
            document_id=document.id,
            index_version="idx-citation",
            section_id="JY-01",
            chunk_index=0,
            content="测试资料正文。",
        )
        session.add(chunk)
        session.flush()
        result = RetrievalResult(chunk=chunk, document=document, score=0.03, vector_score=0.8, keyword_score=5.0)

    class FakeVectorIndex:
        active_profile_id = "fake"

        def search(self, question, limit, category=None):
            return [result]

    class FakeModel:
        async def stream(self, messages):
            yield "这条回答引用了不存在的来源[9]。"

    application.state.vector_index = FakeVectorIndex()
    application.state.llm_model = FakeModel()
    response = client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation["id"], "question": "测试引用"},
        headers=auth,
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "citation_invalid" in response.text
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=auth).json()
    assert detail["messages"][-1]["status"] == "failed"
    assert detail["messages"][-1]["sources_json"] == []


def test_chat_removes_reasoning_marker_and_duplicate_text(client, application, headers):
    auth = headers()
    conversation = client.post("/api/conversations", json={}, headers=auth).json()
    with application.state.database.session_factory() as session, session.begin():
        document = Document(
            document_code="DOC-THINK-01",
            title="思考标记测试",
            category="教务",
            original_name="think.md",
            stored_path="uploads/think.md",
            sha256="f" * 64,
            status="ready",
            index_version="idx-think",
        )
        session.add(document)
        session.flush()
        chunk = Chunk(
            document_id=document.id,
            index_version="idx-think",
            section_id="JY-01",
            chunk_index=0,
            content="测试资料正文。",
        )
        session.add(chunk)
        session.flush()
        result = RetrievalResult(chunk=chunk, document=document, score=0.03, vector_score=0.8, keyword_score=5.0)

    answer = "这是有效回答[1]。"

    class FakeVectorIndex:
        active_profile_id = "fake"

        def search(self, question, limit, category=None):
            return [result]

    class FakeModel:
        async def stream(self, messages):
            yield f"{answer}\n</think>\n\n{answer}"

    application.state.vector_index = FakeVectorIndex()
    application.state.llm_model = FakeModel()
    response = client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation["id"], "question": "测试思考标记"},
        headers=auth,
    )
    assert response.status_code == 200
    assert "event: message_replace" in response.text
    assert '"content": "这是有效回答[1]。"' in response.text
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=auth).json()
    assert detail["messages"][-1]["content"] == answer
    assert detail["messages"][-1]["status"] == "completed"
