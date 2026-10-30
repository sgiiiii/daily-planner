"""REST API цифрового ежедневника."""

from __future__ import annotations

import re
import time
from datetime import date as Date
from datetime import datetime
from urllib.parse import parse_qs

from . import auth, db, planner, settings
from .errors import ApiError

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PASSWORD_MIN = 8

ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def decorator(func):
        ROUTES.append((method, re.compile(f"^{pattern}$"), func.__name__))
        return func

    return decorator


class Context:
    """Всё, что нужно обработчику запроса."""

    def __init__(self, conn, method: str, path: str, query: dict, body: dict, token: str | None):
        self.conn = conn
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.token = token
        self.user = None
        self.cookies: list[str] = []

    def need_user(self):
        if self.user is None:
            raise ApiError(401, "unauthorized", "Требуется вход в аккаунт")
        return self.user

    def query_int(self, name: str, default: int, minimum: int = 0, maximum: int = 10_000) -> int:
        raw = self.query.get(name)
        if raw is None:
            return default
        try:
            return max(minimum, min(maximum, int(raw)))
        except ValueError:
            return default


# --------------------------------------------------------------------------
# Пользователи и сессии
# --------------------------------------------------------------------------

def user_json(row) -> dict:
    return {
        "id": row["id"],
        "login": row["login"],
        "name": row["name"],
        "theme": row["theme"],
        "rolloverTime": row["rollover_time"],
        "summaryEnabled": bool(row["summary_enabled"]),
        "createdAt": row["created_at"],
    }


def _check_login(login: str) -> str:
    login = (login or "").strip().lower()
    if not LOGIN_RE.match(login):
        raise ApiError(
            422,
            "login_invalid",
            "Логин: 3–32 символа, латиница, цифры, точка, дефис или подчёркивание",
            {"login": "invalid"},
        )
    return login


def _check_password(password: str) -> str:
    password = password or ""
    if len(password) < PASSWORD_MIN:
        raise ApiError(
            422,
            "password_short",
            f"Пароль должен содержать не меньше {PASSWORD_MIN} символов",
            {"password": "short"},
        )
    if len(password) > 128:
        raise ApiError(422, "password_long", "Пароль слишком длинный", {"password": "long"})
    return password


@route("POST", "/api/auth/register")
def auth_register(ctx: Context) -> dict:
    login = _check_login(ctx.body.get("login"))
    password = _check_password(ctx.body.get("password"))
    name = (ctx.body.get("name") or "").strip() or login

    if ctx.conn.execute("SELECT 1 FROM users WHERE login = ?", (login,)).fetchone():
        raise ApiError(409, "login_taken", "Такой логин уже занят", {"login": "taken"})

    salt, digest = auth.hash_password(password)
    user_id = db.insert_returning_id(
        ctx.conn,
        """INSERT INTO users (login, name, pwd_salt, pwd_hash, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (login, name, salt, digest, planner.now_str()),
    )
    token = auth.create_session(ctx.conn, user_id)
    ctx.cookies.append(auth.session_cookie(token))
    row = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"user": user_json(row), "created": True}


@route("POST", "/api/auth/login")
def auth_login(ctx: Context) -> dict:
    login = (ctx.body.get("login") or "").strip().lower()
    password = ctx.body.get("password") or ""
    if not login or not password:
        raise ApiError(422, "credentials_required", "Введите логин и пароль")
    row = ctx.conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()
    if row is None or not auth.verify_password(password, row["pwd_salt"], row["pwd_hash"]):
        raise ApiError(401, "bad_credentials", "Неверный логин или пароль")
    token = auth.create_session(ctx.conn, row["id"])
    ctx.cookies.append(auth.session_cookie(token))
    return {"user": user_json(row)}


@route("POST", "/api/auth/logout")
def auth_logout(ctx: Context) -> dict:
    if ctx.token:
        auth.delete_session(ctx.conn, ctx.token)
    ctx.cookies.append(auth.clear_cookie())
    return {"ok": True}


@route("GET", "/api/me")
def get_me(ctx: Context) -> dict:
    user = ctx.need_user()
    return {"user": user_json(user)}


@route("PATCH", "/api/me")
def update_me(ctx: Context) -> dict:
    user = ctx.need_user()
    fields: dict[str, object] = {}

    if "name" in ctx.body:
        name = (ctx.body.get("name") or "").strip()
        if not name or len(name) > 60:
            raise ApiError(422, "name_invalid", "Имя: от 1 до 60 символов", {"name": "invalid"})
        fields["name"] = name

    if "theme" in ctx.body:
        theme = ctx.body["theme"]
        if theme not in ("light", "dark", "system"):
            raise ApiError(422, "theme_invalid", "Тема: light, dark или system", {"theme": "invalid"})
        fields["theme"] = theme

    if "rolloverTime" in ctx.body:
        value = str(ctx.body["rolloverTime"] or "").strip()
        if not planner.is_time(value):
            raise ApiError(422, "time_invalid", "Время переноса — ЧЧ:ММ", {"rolloverTime": "invalid"})
        fields["rollover_time"] = value

    if "summaryEnabled" in ctx.body:
        fields["summary_enabled"] = 1 if ctx.body["summaryEnabled"] else 0

    if fields:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        ctx.conn.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            list(fields.values()) + [user["id"]],
        )
    row = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": user_json(row)}


@route("POST", "/api/me/password")
def change_password(ctx: Context) -> dict:
    user = ctx.need_user()
    current = ctx.body.get("current") or ""
    if not auth.verify_password(current, user["pwd_salt"], user["pwd_hash"]):
        raise ApiError(422, "password_wrong", "Текущий пароль неверен", {"current": "wrong"})
    password = _check_password(ctx.body.get("password"))
    salt, digest = auth.hash_password(password)
    ctx.conn.execute(
        "UPDATE users SET pwd_salt = ?, pwd_hash = ? WHERE id = ?",
        (salt, digest, user["id"]),
    )
    ctx.conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    token = auth.create_session(ctx.conn, user["id"])
    ctx.cookies.append(auth.session_cookie(token))
    return {"ok": True}


@route("DELETE", "/api/me")
def delete_account(ctx: Context) -> dict:
    user = ctx.need_user()
    ctx.conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    ctx.cookies.append(auth.clear_cookie())
    return {"ok": True}


# --------------------------------------------------------------------------
# Задачи
# --------------------------------------------------------------------------

@route("GET", "/api/tasks")
def tasks_list(ctx: Context) -> dict:
    user = ctx.need_user()
    status = ctx.query.get("status", "all")
    if status not in ("all", "open", "done", "overdue", "carried"):
        raise ApiError(422, "status_invalid", "Неизвестный фильтр статуса")
    sphere = ctx.query.get("sphere")
    if sphere and sphere not in planner.SPHERES and sphere != "all":
        raise ApiError(422, "sphere_invalid", "Неизвестная сфера задачи")
    dates = ctx.query.get("date")
    if dates:
        date_value = planner.parse_date(dates, "date")
    else:
        date_value = None
    tasks = planner.list_tasks(
        ctx.conn,
        user["id"],
        date=date_value,
        sphere=sphere,
        status=status,
        query=ctx.query.get("q"),
    )
    return {"tasks": tasks}


@route("POST", "/api/tasks")
def tasks_create(ctx: Context) -> dict:
    user = ctx.need_user()
    task = planner.create_task(ctx.conn, user["id"], ctx.body)
    return {"task": task}


@route("GET", r"/api/tasks/(\d+)")
def tasks_get(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    row = planner.task_row(ctx.conn, user["id"], int(task_id))
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    return {"task": planner.task_json(row)}


@route("PATCH", r"/api/tasks/(\d+)")
def tasks_update(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    task = planner.update_task(ctx.conn, user["id"], int(task_id), ctx.body)
    return {"task": task}


@route("DELETE", r"/api/tasks/(\d+)")
def tasks_delete(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    task = planner.delete_task(ctx.conn, user["id"], int(task_id))
    return {"task": task, "undo": "POST /api/tasks/%s/restore" % task_id}


@route("POST", r"/api/tasks/(\d+)/restore")
def tasks_restore(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    return {"task": planner.restore_task(ctx.conn, user["id"], int(task_id))}


@route("POST", r"/api/tasks/(\d+)/toggle")
def tasks_toggle(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    if "done" not in ctx.body:
        raise ApiError(422, "done_required", "Передайте поле done")
    return {"task": planner.set_done(ctx.conn, user["id"], int(task_id), bool(ctx.body["done"]))}


@route("POST", r"/api/tasks/(\d+)/carry")
def tasks_carry(ctx: Context, task_id: str) -> dict:
    user = ctx.need_user()
    target = ctx.body.get("date") or planner.add_days(planner.today_str(), 1)
    return {"task": planner.carry_task(ctx.conn, user["id"], int(task_id), target)}


# --------------------------------------------------------------------------
# День, сводка, итоги
# --------------------------------------------------------------------------

@route("GET", "/api/day")
def day_view(ctx: Context) -> dict:
    user = ctx.need_user()
    date_value = planner.parse_date(ctx.query.get("date") or planner.today_str(), "date")
    return {
        "date": date_value,
        "tasks": planner.list_tasks(ctx.conn, user["id"], date=date_value),
        "events": planner.list_events(ctx.conn, user["id"], date_value, date_value),
        "stats": planner.day_stats(ctx.conn, user["id"], date_value),
        "today": planner.today_str(),
    }


@route("GET", "/api/summary")
def summary_get(ctx: Context) -> dict:
    user = ctx.need_user()
    date_value = planner.parse_date(ctx.query.get("date") or planner.today_str(), "date")
    data = planner.summary(ctx.conn, user["id"], date_value)
    data["user"] = user_json(user)
    return data


@route("GET", "/api/review")
def review_get(ctx: Context) -> dict:
    user = ctx.need_user()
    date_value = planner.parse_date(ctx.query.get("date") or planner.today_str(), "date")
    return planner.review(ctx.conn, user["id"], date_value)


@route("POST", "/api/review/confirm")
def review_confirm(ctx: Context) -> dict:
    user = ctx.need_user()
    date_value = planner.parse_date(ctx.body.get("date") or planner.today_str(), "date")
    return planner.confirm_review(ctx.conn, user["id"], date_value)


@route("POST", "/api/review/carry-all")
def review_carry_all(ctx: Context) -> dict:
    user = ctx.need_user()
    date_value = planner.parse_date(ctx.body.get("date") or planner.today_str(), "date")
    target = planner.add_days(date_value, 1)
    open_tasks = planner.list_tasks(ctx.conn, user["id"], date=date_value, status="open")
    for task in open_tasks:
        planner.carry_task(ctx.conn, user["id"], task["id"], target)
    return {"moved": len(open_tasks), "date": target, "tasks": [task["id"] for task in open_tasks]}


@route("POST", "/api/rollover")
def rollover_now(ctx: Context) -> dict:
    """Ручной запуск ежедневного переноса (для проверки и демонстрации)."""
    user = ctx.need_user()
    moved = planner.carry_open_tasks(ctx.conn, user["id"], planner.today_str())
    ctx.conn.execute(
        "UPDATE users SET last_rollover = ? WHERE id = ?",
        (planner.today_str(), user["id"]),
    )
    return {"moved": moved, "date": planner.today_str()}


# --------------------------------------------------------------------------
# События и календарь
# --------------------------------------------------------------------------

@route("GET", "/api/events")
def events_list(ctx: Context) -> dict:
    user = ctx.need_user()
    start = planner.parse_date(ctx.query.get("from") or planner.today_str(), "from")
    end = planner.parse_date(ctx.query.get("to") or start, "to")
    if end < start:
        raise ApiError(422, "range_invalid", "Конец диапазона раньше начала")
    return {"events": planner.list_events(ctx.conn, user["id"], start, end)}


@route("POST", "/api/events")
def events_create(ctx: Context) -> dict:
    user = ctx.need_user()
    return {"event": planner.create_event(ctx.conn, user["id"], ctx.body)}


@route("PATCH", r"/api/events/(\d+)")
def events_update(ctx: Context, event_id: str) -> dict:
    user = ctx.need_user()
    return {"event": planner.update_event(ctx.conn, user["id"], int(event_id), ctx.body)}


@route("DELETE", r"/api/events/(\d+)")
def events_delete(ctx: Context, event_id: str) -> dict:
    user = ctx.need_user()
    planner.delete_event(ctx.conn, user["id"], int(event_id))
    return {"ok": True}


@route("GET", "/api/calendar")
def calendar_get(ctx: Context) -> dict:
    user = ctx.need_user()
    start = planner.parse_date(ctx.query.get("from") or planner.today_str(), "from")
    end = planner.parse_date(ctx.query.get("to") or start, "to")
    span = (Date.fromisoformat(end) - Date.fromisoformat(start)).days
    if span < 0:
        raise ApiError(422, "range_invalid", "Конец диапазона раньше начала")
    if span > 62:
        raise ApiError(422, "range_too_large", "Диапазон не больше 62 дней")
    return planner.calendar(ctx.conn, user["id"], start, end)


# --------------------------------------------------------------------------
# Служебные
# --------------------------------------------------------------------------

@route("GET", "/api/config")
def app_config(ctx: Context) -> dict:
    """Публичные настройки интерфейса (без авторизации)."""
    return {
        "appName": settings.APP_NAME,
        "demoEnabled": settings.DEMO_ENABLED,
        "backend": db.backend_name(),
    }


@route("GET", "/api/health")
def health(ctx: Context) -> dict:
    ctx.conn.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "time": datetime.now().isoformat(timespec="seconds"),
        "backend": db.backend_name(),
    }


# --------------------------------------------------------------------------
# Диспетчеризация
# --------------------------------------------------------------------------

class RateLimiter:
    """Простейший антибрутфорс для попыток входа по IP."""

    def __init__(self, limit: int = 30, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        values = [stamp for stamp in self.hits.get(key, []) if now - stamp < self.window]
        if len(values) >= self.limit:
            self.hits[key] = values
            return False
        values.append(now)
        self.hits[key] = values
        return True

    def reset(self) -> None:
        self.hits.clear()


LIMITER = RateLimiter()


def dispatch(conn, method: str, raw_path: str, raw_query: str, body: dict, token: str | None, client_ip: str):
    """Найти обработчик, выполнить его и вернуть (статус, тело, cookie)."""
    path = raw_path.rstrip("/") or "/"
    if method in ("POST", "PATCH", "DELETE") and path.startswith("/api/auth/"):
        if not LIMITER.allow(client_ip):
            raise ApiError(429, "too_many_requests", "Слишком много попыток. Попробуйте через минуту")

    query = {key: values[0] for key, values in parse_qs(raw_query, keep_blank_values=True).items()}
    ctx = Context(conn, method, path, query, body, token)

    for route_method, pattern, handler_name in ROUTES:
        if route_method != method:
            continue
        match = pattern.match(path)
        if not match:
            continue
        handler = globals()[handler_name]
        try:
            if token:
                ctx.user = auth.user_by_token(conn, token)
            if ctx.user is not None:
                planner.rollover_if_due(conn, ctx.user)
            result = handler(ctx, *match.groups()) if match.groups() else handler(ctx)
        except ApiError:
            raise
        return 200, result, ctx.cookies

    raise ApiError(404, "not_found", "Метод API не найден")
