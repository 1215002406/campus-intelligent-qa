from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.core.security import verify_password
from app.main import create_app
from app.repositories import UserRepository


def test_health_and_login_contract(client, application, settings):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "stage": "rag",
        "rag_ready": False,
        "vector_index_enabled": False,
    }
    response = client.post("/api/auth/login", json={"username": " root ", "password": "123"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "root"
    assert body["user"]["role"] == "admin"
    assert body["user"]["is_active"] is True
    assert isinstance(body["user"]["id"], int)
    assert body["user"]["created_at"].endswith("Z")
    assert "password" not in str(body["user"])
    token = jwt.decode(body["access_token"], settings.jwt_secret_key.get_secret_value(), algorithms=["HS256"])
    assert token["exp"] - token["iat"] == 8 * 60 * 60
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + body["access_token"]}).json() == body["user"]
    with application.state.database.session_factory() as session:
        user = UserRepository(session).get_by_username("root")
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password("123", user.password_hash)
        assert "123" not in user.password_hash


def test_student_registration_logs_in_and_allows_short_password(client):
    response = client.post("/api/auth/register", json={
        "username": " new-student ",
        "password": "1",
        "role": "student",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "new-student"
    assert body["user"]["role"] == "student"
    assert body["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + body["access_token"]},
    ).json()["username"] == "new-student"

    duplicate = client.post("/api/auth/register", json={
        "username": "new-student",
        "password": "another",
        "role": "student",
    })
    assert duplicate.status_code == 409


def test_admin_registration_requires_invitation_code(client):
    rejected = client.post("/api/auth/register", json={
        "username": "new-admin",
        "password": "1",
        "role": "admin",
        "admin_code": "wrong",
    })
    assert rejected.status_code == 403
    accepted = client.post("/api/auth/register", json={
        "username": "new-admin",
        "password": "1",
        "role": "admin",
        "admin_code": "test-admin-code",
    })
    assert accepted.status_code == 201
    assert accepted.json()["user"]["role"] == "admin"


def test_registration_rejects_empty_password_and_blank_username(client):
    assert client.post("/api/auth/register", json={
        "username": "student-two",
        "password": "",
        "role": "student",
    }).status_code == 400
    assert client.post("/api/auth/register", json={
        "username": " ",
        "password": "1",
        "role": "student",
    }).status_code == 422


@pytest.mark.parametrize("username,password", [("root", "wrong-password"), ("absent", "123")])
def test_login_failures_have_identical_response(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "用户名或密码错误"}


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer broken.token.here"])
def test_missing_and_malformed_auth(client, authorization):
    response = client.get("/api/auth/me", headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("kind", ["expired", "wrong-secret", "wrong-algorithm", "missing-exp", "missing-iat", "invalid-sub", "unknown-user", "future-iat"])
def test_invalid_jwt_is_rejected(client, settings, kind):
    now = datetime.now(timezone.utc)
    payload = {"sub": "1", "iat": now, "exp": now + timedelta(hours=1)}
    secret = settings.jwt_secret_key.get_secret_value()
    algorithm = "HS256"
    if kind == "expired":
        payload["iat"] = now - timedelta(hours=2)
        payload["exp"] = now - timedelta(hours=1)
    elif kind == "wrong-secret":
        secret = "a-different-test-only-secret-at-least-32-bytes"
    elif kind == "wrong-algorithm":
        algorithm = "HS512"
    elif kind == "missing-exp":
        del payload["exp"]
    elif kind == "missing-iat":
        del payload["iat"]
    elif kind == "invalid-sub":
        payload["sub"] = "not-a-user-id"
    elif kind == "unknown-user":
        payload["sub"] = "99999"
    elif kind == "future-iat":
        payload["iat"] = now + timedelta(hours=1)
    token = jwt.encode(payload, secret, algorithm=algorithm)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_active_status_is_checked_on_every_request(client, application, headers):
    auth = headers("admin")
    with application.state.database.session_factory() as session, session.begin():
        user = UserRepository(session).get_by_username("root")
        user.is_active = False
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    assert client.post("/api/auth/login", json={"username": "root", "password": "123"}).status_code == 401


def test_validation_never_echoes_password(client):
    sensitive_input = "sensitive-password-value" * 100
    response = client.post("/api/auth/login", json={"username": "root", "password": sensitive_input})
    assert response.status_code == 401
    assert sensitive_input not in response.text


def test_missing_configuration_fails_before_database_connection(settings):
    incomplete = Settings(**{**settings.model_dump(), "admin_username": "", "admin_password": "", "jwt_secret_key": ""}, _env_file=None)
    with pytest.raises(RuntimeError, match="Missing required configuration"):
        with TestClient(create_app(incomplete)):
            pass


def test_runtime_accepts_any_non_empty_password_length(settings):
    assert settings.admin_password.get_secret_value() == "123"
    settings.validate_runtime()
    blank = Settings(**{**settings.model_dump(), "admin_password": " "}, _env_file=None)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        blank.validate_runtime()


def test_runtime_rejects_weak_secret(settings):
    weak = Settings(**{**settings.model_dump(), "jwt_secret_key": "short"}, _env_file=None)
    with pytest.raises(RuntimeError, match="32 bytes"):
        weak.validate_runtime()


def test_database_url_requires_mysql(settings):
    configured = Settings(_env_file=None, database_url=settings.database_url, upload_dir="uploads")
    assert configured.database_url == settings.database_url
    assert configured.upload_dir == PROJECT_ROOT / "uploads"
    with pytest.raises(ValidationError, match="mysql\\+pymysql"):
        Settings(_env_file=None, database_url="postgresql://localhost/example")
