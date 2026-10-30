"""Демонстрационные данные: аккаунт demo / demo1234.

Данные привязаны к текущей дате, поэтому проект «живой» сразу после запуска:
есть выполненные задачи, приоритеты, перенесённые дела, встречи и планы на
завтра.
"""

from __future__ import annotations

from . import auth, db, planner, settings


def ensure_demo(conn) -> bool:
    """Создать демо-аккаунт, если база пуста. True — если аккаунт создан."""
    if not settings.DEMO_ENABLED:
        return False
    existing = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    if existing["n"]:
        return False

    salt, digest = auth.hash_password("demo1234")
    sql = """INSERT INTO users (login, name, pwd_salt, pwd_hash, theme, rollover_time,
                                 summary_enabled, created_at)
             VALUES (?, ?, ?, ?, 'system', '04:00', 1, ?)
             ON CONFLICT (login) DO NOTHING"""
    params = ("demo", "Марсель", salt, digest, planner.now_str())
    if db.USE_POSTGRES:
        row = conn.execute(sql + " RETURNING id", params).fetchone()
        user_id = row["id"] if row else None
    else:
        cursor = conn.execute(sql, params)
        user_id = cursor.lastrowid if cursor.rowcount == 1 else None
    if not user_id:
        # Параллельный worker уже создал демо-аккаунт.
        return False
    today = planner.today_str()
    yesterday = planner.add_days(today, -1)
    tomorrow = planner.add_days(today, 1)
    day_after = planner.add_days(today, 2)
    now = planner.now_str()

    tasks = [
        # title, note, sphere, priority, date, time, done, carried, carried_from
        ("Подготовить отчёт по проекту", "Раздел с метриками и графиком релиза", "work", "urgent", today, "18:00", 0, 0, None),
        ("Планёрка с командой", "Обсудить блокеры спринта", "work", "high", today, "10:00", 0, 0, None),
        ("Согласовать макеты с командой", "Финальная версия экрана «Итог дня»", "work", "high", today, "15:30", 0, 0, None),
        ("Конспект лекции 8: дизайн-токены", "", "study", "high", today, "20:00", 0, 0, None),
        ("Записаться к стоматологу", "На следующей неделе, утром", "personal", "normal", today, "12:00", 0, 0, None),
        ("Оплатить интернет", "Перенесено со вчера автоматически", "personal", "normal", today, "19:00", 0, 1, yesterday),
        ("Ответить на письма", "", "work", "normal", today, "09:00", 1, 0, None),
        ("Утренняя зарядка", "", "personal", "low", today, "08:00", 1, 0, None),
        ("Проверить бэклог на неделю", "", "work", "normal", yesterday, None, 1, 0, None),
        ("Сдать лабораторную №7", "Юзабилити-тестирование и правки", "study", "high", tomorrow, "23:59", 0, 0, None),
        ("Встреча с куратором", "", "work", "normal", tomorrow, "16:00", 0, 0, None),
        ("Купить продукты", "", "personal", "low", tomorrow, "19:00", 0, 0, None),
        ("Прочитать главу про типографику", "", "study", "normal", day_after, None, 0, 0, None),
    ]
    for title, note, sphere, priority, due, due_time, done, carried, carried_from in tasks:
        conn.execute(
            """INSERT INTO tasks (user_id, title, note, sphere, priority, due_date, due_time,
                                  done, done_at, carried, carried_from, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                title,
                note,
                sphere,
                priority,
                due,
                due_time,
                1 if done else 0,
                now if done else None,
                carried,
                carried_from,
                now,
                now,
            ),
        )

    events = [
        ("Планёрка команды", today, "10:00", "10:30", "meeting"),
        ("Ревью макетов", today, "13:00", "14:00", "meeting"),
        ("Созвон с куратором", today, "16:30", "17:00", "meeting"),
        ("Лекция по проектированию интерфейсов", tomorrow, "09:30", "11:00", "study"),
        ("Консультация по диплому", day_after, "11:00", "12:00", "meeting"),
        ("Спортзал", day_after, "19:00", "20:30", "personal"),
    ]
    for title, date_value, start, end, kind in events:
        conn.execute(
            """INSERT INTO events (user_id, title, date, start_time, end_time, kind, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, title, date_value, start, end, kind, planner.now_str()),
        )

    conn.execute(
        "UPDATE users SET last_rollover = ? WHERE id = ?", (today, user_id)
    )
    return True
