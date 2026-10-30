"""Слой доступа к данным.

Локально приложение работает на SQLite, в продакшене — на PostgreSQL
(переменная окружения ``DATABASE_URL``). Оба драйвера спрятаны за небольшим
адаптером: остальной код пишет SQL с плейсхолдерами ``?`` и обращается к
строкам по имени колонки.

Так локальная разработка остаётся «из коробки», а развёрнутый сервис получает
настоящую базу с постоянным хранением.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]

USE_POSTGRES = DATABASE_URL.startswith("postgresql://")
DB_PATH = os.environ.get("PLANNER_DB", os.path.join(BASE_DIR, "data", "planner.db"))
RESET_ON_INIT = os.environ.get("PLANNER_DB_RESET") == "1"

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    pwd_salt TEXT NOT NULL,
    pwd_hash TEXT NOT NULL,
    theme TEXT NOT NULL DEFAULT 'system',
    rollover_time TEXT NOT NULL DEFAULT '04:00',
    summary_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_rollover TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    sphere TEXT NOT NULL DEFAULT 'personal',
    priority TEXT NOT NULL DEFAULT 'normal',
    due_date TEXT NOT NULL,
    due_time TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    carried INTEGER NOT NULL DEFAULT 0,
    carried_from TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    kind TEXT NOT NULL DEFAULT 'meeting',
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS day_reviews (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_date ON tasks(user_id, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_user_done ON tasks(user_id, done);
CREATE INDEX IF NOT EXISTS idx_events_user_date ON events(user_id, date);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    pwd_salt TEXT NOT NULL,
    pwd_hash TEXT NOT NULL,
    theme TEXT NOT NULL DEFAULT 'system',
    rollover_time TEXT NOT NULL DEFAULT '04:00',
    summary_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_rollover TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    sphere TEXT NOT NULL DEFAULT 'personal',
    priority TEXT NOT NULL DEFAULT 'normal',
    due_date TEXT NOT NULL,
    due_time TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    carried INTEGER NOT NULL DEFAULT 0,
    carried_from TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    kind TEXT NOT NULL DEFAULT 'meeting',
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS day_reviews (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_date ON tasks(user_id, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_user_done ON tasks(user_id, done);
CREATE INDEX IF NOT EXISTS idx_events_user_date ON events(user_id, date);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

DROP_TABLES = "DROP TABLE IF EXISTS day_reviews, events, tasks, sessions, users CASCADE"


class Cursor:
    """Единый интерфейс курсора для SQLite и PostgreSQL."""

    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    @property
    def rowcount(self):
        return getattr(self._cursor, "rowcount", -1)


class Connection:
    def __init__(self, raw, is_postgres: bool):
        self.raw = raw
        self.is_postgres = is_postgres

    def execute(self, sql: str, params=()) -> Cursor:
        if self.is_postgres:
            # В SQL проекта нет строковых литералов со знаком вопроса,
            # поэтому замена плейсхолдеров безопасна.
            sql = sql.replace("?", "%s")
        return Cursor(self.raw.execute(sql, params))

    def executescript(self, script: str) -> None:
        statements = [part.strip() for part in script.split(";") if part.strip()]
        for statement in statements:
            self.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def connect() -> Connection:
    """Открыть соединение с базой."""
    if USE_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=15)
        return Connection(raw, True)

    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    raw = sqlite3.connect(DB_PATH, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA busy_timeout = 5000")
    return Connection(raw, False)


@contextmanager
def session():
    """Соединение с автоматическим commit/rollback и закрытием."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Применить схему (идемпотентно). PLANNER_DB_RESET=1 удаляет таблицы."""
    if USE_POSTGRES:
        conn = connect()
        try:
            if RESET_ON_INIT:
                conn.execute(DROP_TABLES)
            conn.executescript(POSTGRES_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        return

    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = connect()
    try:
        if RESET_ON_INIT:
            conn.execute(DROP_TABLES)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_returning_id(conn: Connection, sql: str, params=()) -> int:
    """Выполнить INSERT и вернуть идентификатор новой строки."""
    if conn.is_postgres:
        cursor = conn.execute(sql + " RETURNING id", params)
        return cursor.fetchone()["id"]
    cursor = conn.execute(sql, params)
    return cursor.lastrowid


def like_operator() -> str:
    """В PostgreSQL LIKE зависит от регистра, в SQLite — для ASCII нет."""
    return "ILIKE" if USE_POSTGRES else "LIKE"


def backend_name() -> str:
    return "PostgreSQL" if USE_POSTGRES else "SQLite"
