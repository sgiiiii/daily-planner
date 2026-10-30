"""Предметная логика цифрового ежедневника.

Здесь живут все правила: структура задачи, приоритеты, сферы, перенос
невыполненных задач, сводка и итоги дня. Модуль не знает про HTTP.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime, time as Time
from datetime import timedelta

from . import db
SPHERES = ("work", "study", "personal")
PRIORITIES = ("low", "normal", "high", "urgent")
PRIORITY_RANK = {"low": 1, "normal": 2, "high": 3, "urgent": 4}
PRIORITY_ORDER_SQL = (
    "CASE priority WHEN 'urgent' THEN 4 WHEN 'high' THEN 3 "
    "WHEN 'normal' THEN 2 ELSE 1 END"
)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MAX_TITLE = 200
MAX_NOTE = 1000

TASK_COLUMNS = (
    "id, user_id, title, note, sphere, priority, due_date, due_time, done, "
    "done_at, carried, carried_from, created_at, updated_at, deleted_at, cancelled_at"
)


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------

def today_str() -> str:
    return Date.today().isoformat()


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def add_days(value: str, days: int) -> str:
    return (Date.fromisoformat(value) + timedelta(days=days)).isoformat()


def is_time(value: str | None) -> bool:
    return bool(value) and bool(TIME_RE.match(value))


def parse_date(value, field: str = "date") -> str:
    from .errors import ApiError

    if value is None or value == "":
        raise ApiError(422, "date_required", "Укажите дату в формате ГГГГ-ММ-ДД", {field: "required"})
    text = str(value).strip()
    try:
        parsed = Date.fromisoformat(text)
    except ValueError:
        raise ApiError(422, "date_invalid", "Дата должна быть в формате ГГГГ-ММ-ДД", {field: "invalid"}) from None
    if parsed.year < 2000 or parsed.year > 2100:
        raise ApiError(422, "date_invalid", "Дата вне допустимого диапазона", {field: "invalid"})
    return parsed.isoformat()


def task_row(conn, user_id: int, task_id: int, include_deleted: bool = False):
    sql = f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = ? AND user_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    return conn.execute(sql, (task_id, user_id)).fetchone()


def task_json(row, today: str | None = None) -> dict:
    today = today or today_str()
    due = row["due_date"]
    done = bool(row["done"])
    deleted = bool(row["deleted_at"])
    cancelled = bool(row["cancelled_at"])
    if deleted:
        status = "deleted"
    elif cancelled:
        status = "cancelled"
    elif done:
        status = "done"
    elif due < today:
        status = "overdue"
    elif row["carried"]:
        status = "carried"
    else:
        status = "open"
    return {
        "id": row["id"],
        "title": row["title"],
        "note": row["note"] or "",
        "sphere": row["sphere"],
        "priority": row["priority"],
        "date": due,
        "time": row["due_time"],
        "done": done,
        "doneAt": row["done_at"],
        "carried": row["carried"] or 0,
        "carriedFrom": row["carried_from"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "status": status,
        "overdue": (not done) and due < today,
        "isToday": due == today,
    }


def event_json(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "date": row["date"],
        "start": row["start_time"],
        "end": row["end_time"],
        "kind": row["kind"],
    }


# --------------------------------------------------------------------------
# Задачи
# --------------------------------------------------------------------------

def list_tasks(
    conn,
    user_id: int,
    *,
    date: str | None = None,
    sphere: str | None = None,
    status: str = "all",
    query: str | None = None,
    limit: int = 500,
):
    today = today_str()
    where = ["user_id = ?", "deleted_at IS NULL", "cancelled_at IS NULL"]
    params: list = [user_id]

    if status == "overdue":
        where.append("done = 0 AND due_date < ?")
        params.append(today)
    elif status == "carried":
        where.append("carried > 0 AND due_date = ?")
        params.append(date or today)
    elif date:
        where.append("due_date = ?")
        params.append(date)

    if sphere and sphere != "all":
        where.append("sphere = ?")
        params.append(sphere)
    if status == "done":
        where.append("done = 1")
    elif status == "open":
        where.append("done = 0")
    if query:
        where.append(f"(title {db.like_operator()} ? OR note {db.like_operator()} ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like])

    sql = (
        f"SELECT {TASK_COLUMNS} FROM tasks WHERE {' AND '.join(where)} "
        f"ORDER BY done ASC, {PRIORITY_ORDER_SQL} DESC, "
        "COALESCE(due_time, '99:99') ASC, id ASC LIMIT ?"
    )
    params.append(limit)
    return [task_json(row, today) for row in conn.execute(sql, params)]


def create_task(conn, user_id: int, data: dict) -> dict:
    from .errors import ApiError

    title = (data.get("title") or "").strip()
    if not title:
        raise ApiError(422, "title_required", "Введите название задачи", {"title": "required"})
    if len(title) > MAX_TITLE:
        raise ApiError(422, "title_too_long", f"Название не длиннее {MAX_TITLE} символов", {"title": "too_long"})

    due = parse_date(data.get("date") or today_str(), "date")
    if due < today_str():
        raise ApiError(422, "date_in_past", "Срок не может быть раньше текущей даты", {"date": "in_past"})

    sphere = data.get("sphere") or "personal"
    if sphere not in SPHERES:
        raise ApiError(422, "sphere_invalid", "Неизвестная сфера задачи", {"sphere": "invalid"})

    priority = data.get("priority") or "normal"
    if priority not in PRIORITIES:
        raise ApiError(422, "priority_invalid", "Неизвестный приоритет", {"priority": "invalid"})

    due_time = data.get("time") or None
    if due_time in ("", None):
        due_time = None
    elif not is_time(due_time):
        raise ApiError(422, "time_invalid", "Время указывается в формате ЧЧ:ММ", {"time": "invalid"})

    note = (data.get("note") or "").strip()
    if len(note) > MAX_NOTE:
        raise ApiError(422, "note_too_long", f"Заметка не длиннее {MAX_NOTE} символов", {"note": "too_long"})

    now = now_str()
    task_id = db.insert_returning_id(
        conn,
        """INSERT INTO tasks (user_id, title, note, sphere, priority, due_date, due_time,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, note, sphere, priority, due, due_time, now, now),
    )
    row = task_row(conn, user_id, task_id)
    return task_json(row)


def update_task(conn, user_id: int, task_id: int, data: dict) -> dict:
    from .errors import ApiError

    row = task_row(conn, user_id, task_id)
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")

    updates: dict[str, object] = {}

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ApiError(422, "title_required", "Введите название задачи", {"title": "required"})
        if len(title) > MAX_TITLE:
            raise ApiError(422, "title_too_long", f"Название не длиннее {MAX_TITLE} символов", {"title": "too_long"})
        updates["title"] = title

    if "date" in data:
        updates["due_date"] = parse_date(data.get("date"), "date")

    if "time" in data:
        value = data.get("time") or None
        if value and not is_time(value):
            raise ApiError(422, "time_invalid", "Время указывается в формате ЧЧ:ММ", {"time": "invalid"})
        updates["due_time"] = value

    if "sphere" in data:
        if data["sphere"] not in SPHERES:
            raise ApiError(422, "sphere_invalid", "Неизвестная сфера задачи", {"sphere": "invalid"})
        updates["sphere"] = data["sphere"]

    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            raise ApiError(422, "priority_invalid", "Неизвестный приоритет", {"priority": "invalid"})
        updates["priority"] = data["priority"]

    if "note" in data:
        note = (data.get("note") or "").strip()
        if len(note) > MAX_NOTE:
            raise ApiError(422, "note_too_long", f"Заметка не длиннее {MAX_NOTE} символов", {"note": "too_long"})
        updates["note"] = note

    if "carried" in data:
        try:
            carried = max(0, int(data["carried"]))
        except (TypeError, ValueError):
            carried = 0
        updates["carried"] = carried
        updates["carried_from"] = data.get("carriedFrom") if carried else None

    if "done" in data:
        done = bool(data["done"])
        updates["done"] = 1 if done else 0
        updates["done_at"] = now_str() if done else None

    if not updates:
        return task_json(row)

    assignments = ", ".join(f"{column} = ?" for column in updates)
    conn.execute(
        f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
        list(updates.values()) + [now_str(), task_id, user_id],
    )
    return task_json(task_row(conn, user_id, task_id))


def set_done(conn, user_id: int, task_id: int, done: bool) -> dict:
    from .errors import ApiError

    row = task_row(conn, user_id, task_id)
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    conn.execute(
        "UPDATE tasks SET done = ?, done_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (1 if done else 0, now_str() if done else None, now_str(), task_id, user_id),
    )
    return task_json(task_row(conn, user_id, task_id))


def delete_task(conn, user_id: int, task_id: int) -> dict:
    """Мягкое удаление: задачу можно вернуть в течение сессии («Вернуть»)."""
    from .errors import ApiError

    row = task_row(conn, user_id, task_id)
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    conn.execute(
        "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (now_str(), now_str(), task_id, user_id),
    )
    return task_json(task_row(conn, user_id, task_id, include_deleted=True))


def restore_task(conn, user_id: int, task_id: int) -> dict:
    from .errors import ApiError

    row = task_row(conn, user_id, task_id, include_deleted=True)
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    conn.execute(
        "UPDATE tasks SET deleted_at = NULL, updated_at = ? WHERE id = ? AND user_id = ?",
        (now_str(), task_id, user_id),
    )
    return task_json(task_row(conn, user_id, task_id))


def carry_task(conn, user_id: int, task_id: int, to_date: str) -> dict:
    from .errors import ApiError

    row = task_row(conn, user_id, task_id)
    if row is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    target = parse_date(to_date, "date")
    conn.execute(
        """UPDATE tasks SET due_date = ?, carried = carried + 1,
               carried_from = COALESCE(carried_from, due_date), updated_at = ?
           WHERE id = ? AND user_id = ?""",
        (target, now_str(), task_id, user_id),
    )
    return task_json(task_row(conn, user_id, task_id))


def carry_open_tasks(conn, user_id: int, target: str | None = None) -> int:
    """Перенести все невыполненные задачи со сроком в прошлом на target."""
    target = target or today_str()
    rows = conn.execute(
        """SELECT id, due_date FROM tasks
           WHERE user_id = ? AND done = 0 AND deleted_at IS NULL
             AND cancelled_at IS NULL AND due_date < ?""",
        (user_id, target),
    ).fetchall()
    if not rows:
        return 0
    now = now_str()
    for row in rows:
        conn.execute(
            """UPDATE tasks SET due_date = ?, carried = carried + 1,
                   carried_from = COALESCE(carried_from, due_date), updated_at = ?
               WHERE id = ?""",
            (target, now, row["id"]),
        )
    return len(rows)


def rollover_if_due(conn, user_row, now: datetime | None = None) -> int:
    """Выполнить ежедневный перенос, если наступило время из настроек."""
    now = now or datetime.now()
    today = now.date().isoformat()
    if user_row["last_rollover"] == today:
        return 0
    try:
        hour, minute = (int(part) for part in (user_row["rollover_time"] or "04:00").split(":"))
        boundary = Time(hour, minute)
    except (ValueError, TypeError):
        boundary = Time(4, 0)
    if now.time() < boundary:
        return 0
    # Атомарно «занимаем» перенос: при нескольких worker-процессах (gunicorn)
    # право на работу получит только один, остальные увидят rowcount = 0.
    claimed = conn.execute(
        """UPDATE users SET last_rollover = ?
           WHERE id = ? AND (last_rollover IS NULL OR last_rollover <> ?)""",
        (today, user_row["id"], today),
    ).rowcount
    if claimed != 1:
        return 0
    return carry_open_tasks(conn, user_row["id"], today)


# --------------------------------------------------------------------------
# События (встречи и дела со временем)
# --------------------------------------------------------------------------

def list_events(conn, user_id: int, date_from: str, date_to: str) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM events
           WHERE user_id = ? AND deleted_at IS NULL AND date BETWEEN ? AND ?
           ORDER BY date, start_time, id""",
        (user_id, date_from, date_to),
    ).fetchall()
    return [event_json(row) for row in rows]


def create_event(conn, user_id: int, data: dict) -> dict:
    from .errors import ApiError

    title = (data.get("title") or "").strip()
    if not title:
        raise ApiError(422, "title_required", "Введите название события", {"title": "required"})
    if len(title) > MAX_TITLE:
        raise ApiError(422, "title_too_long", f"Название не длиннее {MAX_TITLE} символов", {"title": "too_long"})
    event_date = parse_date(data.get("date"), "date")
    start = data.get("start") or ""
    if not is_time(start):
        raise ApiError(422, "time_invalid", "Укажите время начала в формате ЧЧ:ММ", {"start": "invalid"})
    end = data.get("end") or None
    if end and not is_time(end):
        raise ApiError(422, "time_invalid", "Время окончания в формате ЧЧ:ММ", {"end": "invalid"})
    if end and end <= start:
        raise ApiError(422, "time_order", "Время окончания должно быть позже начала", {"end": "order"})
    kind = data.get("kind") or "meeting"
    if kind not in ("meeting", "study", "personal"):
        kind = "meeting"
    event_id = db.insert_returning_id(
        conn,
        """INSERT INTO events (user_id, title, date, start_time, end_time, kind, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, event_date, start, end, kind, now_str()),
    )
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return event_json(row)


def update_event(conn, user_id: int, event_id: int, data: dict) -> dict:
    from .errors import ApiError

    row = conn.execute(
        "SELECT * FROM events WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (event_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "event_not_found", "Событие не найдено")

    fields: dict[str, object] = {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ApiError(422, "title_required", "Введите название события", {"title": "required"})
        fields["title"] = title
    if "date" in data:
        fields["date"] = parse_date(data.get("date"), "date")
    if "start" in data:
        if not is_time(data.get("start")):
            raise ApiError(422, "time_invalid", "Укажите время начала в формате ЧЧ:ММ", {"start": "invalid"})
        fields["start_time"] = data["start"]
    if "end" in data:
        value = data.get("end") or None
        if value and not is_time(value):
            raise ApiError(422, "time_invalid", "Время окончания в формате ЧЧ:ММ", {"end": "invalid"})
        fields["end_time"] = value
    if "kind" in data and data["kind"] in ("meeting", "study", "personal"):
        fields["kind"] = data["kind"]

    start = fields.get("start_time", row["start_time"])
    end = fields.get("end_time", row["end_time"])
    if end and end <= start:
        raise ApiError(422, "time_order", "Время окончания должно быть позже начала", {"end": "order"})

    if fields:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE events SET {assignments} WHERE id = ? AND user_id = ?",
            list(fields.values()) + [event_id, user_id],
        )
    return event_json(
        conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    )


def delete_event(conn, user_id: int, event_id: int) -> None:
    from .errors import ApiError

    row = conn.execute(
        "SELECT id FROM events WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (event_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "event_not_found", "Событие не найдено")
    conn.execute(
        "UPDATE events SET deleted_at = ? WHERE id = ? AND user_id = ?",
        (now_str(), event_id, user_id),
    )


# --------------------------------------------------------------------------
# Сводка, итоги дня, календарь
# --------------------------------------------------------------------------

def day_stats(conn, user_id: int, date: str) -> dict:
    row = conn.execute(
        """SELECT
             COUNT(*) AS total,
             COALESCE(SUM(done), 0) AS done,
             COALESCE(SUM(CASE WHEN done = 0 AND due_date < ? THEN 1 ELSE 0 END), 0) AS overdue
           FROM tasks
           WHERE user_id = ? AND due_date = ? AND deleted_at IS NULL AND cancelled_at IS NULL""",
        (today_str(), user_id, date),
    ).fetchone()
    total = row["total"] or 0
    done = row["done"] or 0
    open_count = total - done
    return {
        "total": total,
        "done": done,
        "open": open_count,
        "overdue": row["overdue"] or 0,
        "percent": round(done / total * 100) if total else 0,
    }


def summary(conn, user_id: int, date: str) -> dict:
    today = today_str()
    tasks = list_tasks(conn, user_id, date=date)
    priorities = [task for task in tasks if not task["done"]][:5]
    carried = [task for task in tasks if task["carried"] and not task["done"]]
    overdue_all = list_tasks(conn, user_id, status="overdue")

    next_event = None
    current = datetime.now().strftime("%H:%M")
    events = list_events(conn, user_id, date, date)
    if date == today:
        upcoming = [event for event in events if event["start"] >= current]
        next_event = upcoming[0] if upcoming else (events[-1] if events else None)
    elif events:
        next_event = events[0]

    tomorrow = add_days(date, 1)
    tomorrow_stats = day_stats(conn, user_id, tomorrow)
    return {
        "date": date,
        "today": today,
        "stats": day_stats(conn, user_id, date),
        "priorities": priorities,
        "carried": carried,
        "overdue": overdue_all,
        "events": events,
        "nextEvent": next_event,
        "tomorrow": {"date": tomorrow, "total": tomorrow_stats["total"]},
        "reviewed": is_reviewed(conn, user_id, date),
    }


def review(conn, user_id: int, date: str) -> dict:
    tasks = list_tasks(conn, user_id, date=date)
    done = [task for task in tasks if task["done"]]
    open_tasks = [task for task in tasks if not task["done"]]
    overdue = list_tasks(conn, user_id, status="overdue")
    return {
        "date": date,
        "done": done,
        "open": open_tasks,
        "overdue": overdue,
        "stats": day_stats(conn, user_id, date),
        "tomorrow": add_days(date, 1),
        "reviewed": is_reviewed(conn, user_id, date),
    }


def is_reviewed(conn, user_id: int, date: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM day_reviews WHERE user_id = ? AND date = ?", (user_id, date)
    ).fetchone()
    return row is not None


def confirm_review(conn, user_id: int, date: str) -> dict:
    conn.execute(
        """INSERT INTO day_reviews (user_id, date, confirmed_at) VALUES (?, ?, ?)
           ON CONFLICT(user_id, date) DO UPDATE SET confirmed_at = excluded.confirmed_at""",
        (user_id, date, now_str()),
    )
    stats = day_stats(conn, user_id, date)
    tomorrow = add_days(date, 1)
    return {
        "date": date,
        "confirmed": True,
        "stats": stats,
        "tomorrow": tomorrow,
        "tomorrowTotal": day_stats(conn, user_id, tomorrow)["total"],
        "open": len(list_tasks(conn, user_id, date=date, status="open")),
    }


def calendar(conn, user_id: int, date_from: str, date_to: str) -> dict:
    tasks = conn.execute(
        f"""SELECT {TASK_COLUMNS} FROM tasks
            WHERE user_id = ? AND deleted_at IS NULL AND cancelled_at IS NULL
              AND due_date BETWEEN ? AND ?
            ORDER BY due_date, COALESCE(due_time, '99:99'), id""",
        (user_id, date_from, date_to),
    ).fetchall()
    events = list_events(conn, user_id, date_from, date_to)
    today = today_str()
    return {
        "from": date_from,
        "to": date_to,
        "tasks": [task_json(row, today) for row in tasks],
        "events": events,
        "today": today,
    }
