from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from src.lib.config import JWT_SECRET, JWT_EXPIRES_IN_HOURS


def hash_password(plain_text: str) -> str:
    hashed = bcrypt.hashpw(plain_text.encode("utf-8"), bcrypt.gensalt(rounds=10))
    return hashed.decode("utf-8")


def compare_password(plain_text: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain_text.encode("utf-8"), hashed.encode("utf-8"))


def sign_token(payload: dict) -> str:
    now = datetime.now(timezone.utc)
    token_payload = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRES_IN_HOURS)).timestamp()),
    }
    return jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def extract_bearer_token(event: dict) -> str | None:
    headers = event.get("headers") or {}
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.replace("Bearer ", "", 1).strip()
