from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username.strip()))

    def add(self, *, username: str, password_hash: str, role: str) -> User:
        user = User(username=username.strip(), password_hash=password_hash, role=role)
        self.session.add(user)
        self.session.flush()
        return user
