from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=8)
password_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(user_id: int, secret: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL}, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> int:
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "iat", "exp"]})
    subject = payload["sub"]
    if (not isinstance(subject, str) or not subject.isdecimal() or len(subject) > 19
            or not 1 <= int(subject) <= 9223372036854775807):
        raise jwt.InvalidTokenError("Invalid subject")
    return int(subject)
