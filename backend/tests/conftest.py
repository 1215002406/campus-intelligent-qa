import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

# Also support `python -m pytest backend/tests` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app
from app.models import Base
from app.repositories import UserRepository

def resolve_test_database_url() -> str:
    configured = os.getenv("CAMPUS_TEST_DATABASE_URL", "").strip()
    if configured:
        candidate = configured
    else:
        application_url = Settings().database_url.strip()
        if not application_url:
            raise RuntimeError(
                "Set CAMPUS_TEST_DATABASE_URL or configure DATABASE_URL in backend/.env before running tests"
            )
        candidate = make_url(application_url).set(database="campus_qa_test").render_as_string(hide_password=False)
    if make_url(candidate).database != "campus_qa_test":
        raise RuntimeError("The test database URL must target the campus_qa_test database")
    return candidate


TEST_DATABASE_URL = resolve_test_database_url()


@pytest.fixture
def settings(tmp_path):
    reset_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"charset": "utf8mb4", "connect_timeout": 5},
    )
    Base.metadata.drop_all(reset_engine)
    Base.metadata.create_all(reset_engine)
    reset_engine.dispose()
    return Settings(
        _env_file=None,
        admin_username="root", admin_password="123", admin_registration_code="test-admin-code",
        jwt_secret_key="test-only-signing-secret-for-isolated-databases-123456",
        database_url=TEST_DATABASE_URL,
        upload_dir=tmp_path / "uploads", chroma_dir=tmp_path / "chroma",
        model_cache_dir=tmp_path / "models",
        vector_index_enabled=False,
        vector_backfill_on_startup=False,
    )


@pytest.fixture
def application(settings):
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        with application.state.database.session_factory() as session, session.begin():
            UserRepository(session).add(
                username="student",
                password_hash=hash_password("test-student-password"),
                role="student",
            )
        yield test_client


@pytest.fixture
def headers(client, settings):
    def get(role="student"):
        if role == "student":
            username, password = "student", "test-student-password"
        else:
            username = settings.admin_username
            password = settings.admin_password.get_secret_value()
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200
        return {"Authorization": "Bearer " + response.json()["access_token"]}
    return get
