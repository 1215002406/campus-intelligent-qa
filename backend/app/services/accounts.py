import secrets

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, password_hasher, verify_password
from app.repositories import UserRepository

_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def bootstrap_accounts(session: Session, settings: Settings) -> None:
    repository = UserRepository(session)
    username = settings.admin_username
    password = settings.admin_password.get_secret_value()
    user = repository.get_by_username(username)
    if user is None:
        repository.add(username=username, password_hash=hash_password(password), role="admin")
    elif user.role != "admin":
        raise RuntimeError("Configured administrator role conflicts with an existing user; choose another account name")
    elif not verify_password(password, user.password_hash) or password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)


class AuthService:
    def __init__(self, session: Session, settings: Settings):
        self.repository = UserRepository(session)
        self.settings = settings

    def login(self, username: str, password: str):
        user = self.repository.get_by_username(username)
        valid = verify_password(password, user.password_hash if user else _DUMMY_HASH)
        if user is None or not valid or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误", headers={"WWW-Authenticate": "Bearer"})
        return create_access_token(user.id, self.settings.jwt_secret_key.get_secret_value()), user

    def register(self, username: str, password: str, role: str, admin_code: str | None):
        if not password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "密码不能为空")
        if role == "admin":
            expected = self.settings.admin_registration_code.get_secret_value()
            if not expected:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员注册未开放")
            if not admin_code or not secrets.compare_digest(admin_code, expected):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "管理员邀请码不正确")
        if self.repository.get_by_username(username) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
        try:
            user = self.repository.add(
                username=username,
                password_hash=hash_password(password),
                role=role,
            )
            self.repository.session.commit()
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在") from exc
        token = create_access_token(user.id, self.settings.jwt_secret_key.get_secret_value())
        return token, user
