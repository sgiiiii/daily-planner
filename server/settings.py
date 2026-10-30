"""Настройки, которые задаются переменными окружения.

Значения по умолчанию рассчитаны на локальный запуск: демо-аккаунт создаётся,
планировщик работает, cookie без флага Secure (http://127.0.0.1).
В продакшене эти флаги выставляются в настройках хостинга.
"""

from __future__ import annotations

import os


def flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("", "0", "false", "no", "off")


# Создавать демонстрационный аккаунт при пустой базе.
DEMO_ENABLED = flag("PLANNER_SEED_DEMO", default=True)

# Запускать фоновый поток переноса задач внутри веб-процесса.
SCHEDULER_ENABLED = flag("PLANNER_SCHEDULER", default=True)

# Добавлять флаг Secure к cookie сессии (нужно на HTTPS).
COOKIE_SECURE = flag("PLANNER_COOKIE_SECURE", default=False)

APP_NAME = "Планирование дня"
