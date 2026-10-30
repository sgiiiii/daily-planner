"""Пароли и сессии пользователей.

Пароли хранятся как PBKDF2-HMAC-SHA256 с индивидуальной солью, сессии —
случайные токены в HttpOnly-cookie, сервер хранит только сам токен.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from . import settings

ITERATIONS = 210_000
SESSION_DAYS = 30
COOKIE_NAME = "planner_session"


def build_cookie(token: str, max_age: int) -> str:
    """Собрать значение Set-Cookie для сессии."""
    parts = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={max_age}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if settings.COOKIE_SECURE:
        parts.append("Secure")
    return "; ".join(parts)


def session_cookie(token: str) -> str:
    return build_cookie(token, SESSION_DAYS * 24 * 3600)


def clear_cookie() -> str:
    return build_cookie("", 0)


def hash_password(password: str) -> tuple[str, str]:
    """Вернуть (соль, хэш) в hex-виде."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return hmac.compare_digest(digest.hex(), hash_hex)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry() -> str:
    return (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")


def create_session(conn, user_id: int) -> str:
    token = new_token()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, session_expiry()),
    )
    return token


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_by_token(conn, token: str):
    """Найти пользователя по токену сессии, удалив просроченные сессии."""
    if not token:
        return None
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    row = conn.execute(
        """SELECT u.* FROM sessions s
           JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.expires_at >= ?""",
        (token, now),
    ).fetchone()
    return row
