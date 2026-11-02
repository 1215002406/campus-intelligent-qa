from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decode_access_token
from app.llm.openai_compatible import OpenAICompatibleChatModel
from app.models import User
from app.repositories import UserRepository
from app.services.ingestion import IngestionService
from app.services.llm_models import LLMModelService
from app.services.vector_index import VectorIndexService

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ingestion_service(request: Request) -> IngestionService:
    return request.app.state.ingestion


def get_vector_index_service(request: Request) -> VectorIndexService | None:
    return getattr(request.app.state, "vector_index", None)


def get_llm_model(request: Request) -> OpenAICompatibleChatModel:
    return request.app.state.llm_model


def get_llm_model_service(request: Request) -> LLMModelService:
    return request.app.state.llm_models


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.database.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
IngestionDependency = Annotated[IngestionService, Depends(get_ingestion_service)]
VectorIndexDependency = Annotated[VectorIndexService | None, Depends(get_vector_index_service)]
LLMModelDependency = Annotated[OpenAICompatibleChatModel, Depends(get_llm_model)]
LLMModelsDependency = Annotated[LLMModelService, Depends(get_llm_model_service)]


def get_current_user(
    session: SessionDependency,
    settings: SettingsDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录或重新登录", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials, settings.jwt_secret_key.get_secret_value())
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise unauthorized from None
    user = UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
