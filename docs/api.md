# REST API

Базовый адрес: `http://127.0.0.1:8000/api`. Тело запросов и ответов — JSON,
авторизация — cookie `planner_session` (выставляется сервером при входе).

Ошибки:

```json
{
  "error": {
    "code": "title_required",
    "message": "Введите название задачи",
    "fields": { "title": "required" }
  }
}
```

## Проверка и аккаунты

| Метод | Путь | Что делает |
| --- | --- | --- |
| `GET` | `/health` | проверка живости сервера и тип базы (`backend`) |
| `GET` | `/config` | публичные флаги интерфейса: `appName`, `demoEnabled` |
| `GET` | `/me` | текущий пользователь и настройки |
| `PATCH` | `/me` | имя, тема (`light`/`dark`/`system`), время переноса, сводка |
| `POST` | `/auth/register` | регистрация `{login, password, name}` |
| `POST` | `/auth/login` | вход `{login, password}` |
| `POST` | `/auth/logout` | выход |
| `POST` | `/me/password` | `{current, password}` |
| `DELETE` | `/me` | удалить аккаунт со всеми данными |

```bash
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"demo","password":"demo1234"}'
```

## Задачи

| Метод | Путь | Параметры |
| --- | --- | --- |
| `GET` | `/tasks` | `date=YYYY-MM-DD`, `sphere=work|study|personal`, `status=all|open|done|overdue|carried`, `q=текст` |
| `POST` | `/tasks` | `{title, date?, time?, sphere?, priority?, note?}` |
| `GET` | `/tasks/{id}` | — |
| `PATCH` | `/tasks/{id}` | любые из полей задачи; `carried` можно сбросить в `0` |
| `DELETE` | `/tasks/{id}` | мягкое удаление, возвращает снимок задачи |
| `POST` | `/tasks/{id}/restore` | вернуть удалённую |
| `POST` | `/tasks/{id}/toggle` | `{done: true|false}` |
| `POST` | `/tasks/{id}/carry` | `{date: "YYYY-MM-DD"}` — перенести на дату |

Значения по умолчанию при создании: `date` — сегодня, `sphere` — `personal`,
`priority` — `normal`. `date` не может быть раньше сегодняшнего дня (код
`date_in_past`), `time` — только `ЧЧ:ММ`, название — до 200 символов.

Пример задачи в ответе:

```json
{
  "task": {
    "id": 12,
    "title": "Подготовить отчёт по проекту",
    "note": "Раздел с метриками",
    "sphere": "work",
    "priority": "urgent",
    "date": "2026-10-29",
    "time": "18:00",
    "done": false,
    "status": "open",
    "overdue": false,
    "carried": 0,
    "carriedFrom": null,
    "createdAt": "2026-10-29T09:12:04",
    "updatedAt": "2026-10-29T09:12:04"
  }
}
```

## День, сводка, итоги

| Метод | Путь | Что возвращает |
| --- | --- | --- |
| `GET` | `/day?date=` | задачи и события дня, статистику |
| `GET` | `/summary?date=` | сводку: приоритеты, перенесённые, просроченные, встречи, «на завтра» |
| `GET` | `/review?date=` | выполненные и открытые задачи дня, просроченные, признак `reviewed` |
| `POST` | `/review/confirm` | `{date}` — зафиксировать итог дня |
| `POST` | `/review/carry-all` | `{date}` — перенести все открытые задачи на следующий день |
| `POST` | `/rollover` | вручную выполнить ежедневный перенос |

`stats` в ответе: `{total, done, open, overdue, percent}`.

## События и календарь

| Метод | Путь | Параметры |
| --- | --- | --- |
| `GET` | `/events` | `from`, `to` — диапазон дат |
| `POST` | `/events` | `{title, date, start, end?, kind?}`, `kind` — `meeting`/`study`/`personal` |
| `PATCH` | `/events/{id}` | любые поля события |
| `DELETE` | `/events/{id}` | мягкое удаление |
| `GET` | `/calendar` | `from`, `to` — задачи и события диапазона (не больше 62 дней) |

```json
{
  "event": {
    "id": 3,
    "title": "Созвон с куратором",
    "date": "2026-10-29",
    "start": "16:30",
    "end": "17:00",
    "kind": "meeting"
  }
}
```

## Коды ответов

| Код | Когда |
| --- | --- |
| `200` | успех |
| `401` | нет сессии или неверный пароль |
| `404` | объект не найден или принадлежит другому пользователю |
| `409` | логин уже занят |
| `422` | ошибка валидации, в `fields` — проблемные поля |
| `429` | слишком много попыток входа |
| `500` | внутренняя ошибка |
