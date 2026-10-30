"""WSGI-приложение для продакшена (gunicorn, Render, PythonAnywhere).

Тот же код, что и локальный сервер: REST API через ``api.dispatch`` и статика
из ``web/``. Отличие только в транспорте, поэтому поведение в разработке и на
хостинге совпадает.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from http import HTTPStatus
from urllib.parse import unquote

from . import api, db, scheduler, seed, settings, static
from .errors import ApiError

MAX_BODY = 1_000_000

_init_lock = threading.Lock()
_ready = False


def _ensure_ready() -> None:
    """Применить схему и засеять демо-данные один раз на процесс."""
    global _ready
    if _ready:
        return
    with _init_lock:
        if _ready:
            return
        db.init_db()
        with db.session() as conn:
            seed.ensure_demo(conn)
            conn.commit()
        if settings.SCHEDULER_ENABLED:
            scheduler.start()
        _ready = True


def _status_line(status: int) -> str:
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = "OK"
    return f"{status} {phrase}"


def _error_payload(status: int, code: str, message: str) -> dict:
    return ApiError(status, code, message).payload()


def _send_json(start_response, status: int, payload: dict, cookies: list[str] | None = None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    for cookie in cookies or []:
        headers.append(("Set-Cookie", cookie))
    start_response(_status_line(status), headers)
    return [body]


def _cookie_token(environ) -> str | None:
    header = environ.get("HTTP_COOKIE") or ""
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "planner_session" and value:
            return value
    return None


def _client_ip(environ) -> str:
    forwarded = environ.get("HTTP_X_FORWARDED_FOR") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return environ.get("REMOTE_ADDR") or "127.0.0.1"


def _read_body(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    if length > MAX_BODY:
        raise ApiError(413, "payload_too_large", "Слишком большой запрос")
    raw = environ["wsgi.input"].read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "invalid_json", "Тело запроса должно быть корректным JSON") from None
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Ожидался JSON-объект")
    return data


def _handle_api(environ, start_response, method: str, path: str):
    try:
        body = _read_body(environ) if method in ("POST", "PATCH", "PUT") else {}
        with db.session() as conn:
            status, payload, cookies_out = api.dispatch(
                conn,
                method,
                path,
                environ.get("QUERY_STRING", ""),
                body,
                _cookie_token(environ),
                _client_ip(environ),
            )
    except ApiError as error:
        return _send_json(start_response, error.status, error.payload())
    except Exception:
        traceback.print_exc()
        return _send_json(
            start_response, 500, _error_payload(500, "server_error", "Внутренняя ошибка сервера")
        )
    return _send_json(start_response, status, payload, cookies_out)


def _handle_static(environ, start_response, method: str, path: str):
    if method not in ("GET", "HEAD"):
        return _send_json(
            start_response, 405, _error_payload(405, "method_not_allowed", "Метод не поддерживается")
        )
    try:
        result = static.resolve(unquote(path))
    except PermissionError:
        return _send_json(start_response, 403, _error_payload(403, "forbidden", "Доступ запрещён"))
    if result is None:
        return _send_json(start_response, 404, _error_payload(404, "not_found", "Файл не найден"))
    body, content_type = result
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store" if content_type.startswith("text/html") else "no-cache"),
        *static.SECURITY_HEADERS.items(),
    ]
    start_response(_status_line(200), headers)
    return [b""] if method == "HEAD" else [body]


def application(environ, start_response):
    """Точка входа WSGI."""
    try:
        _ensure_ready()
    except Exception:
        traceback.print_exc()
        return _send_json(
            start_response,
            500,
            _error_payload(500, "db_unavailable", "База данных недоступна"),
        )

    method = (environ.get("REQUEST_METHOD") or "GET").upper()
    path = environ.get("PATH_INFO") or "/"
    if path.startswith("/api"):
        return _handle_api(environ, start_response, method, path)
    return _handle_static(environ, start_response, method, path)


# Для gunicorn: gunicorn wsgi:app, где wsgi.py лежит в корне проекта.
app = application


def main(argv: list[str] | None = None) -> int:
    """Локальный запуск WSGI-сервера (для проверки «как в продакшене»)."""
    import argparse
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

    parser = argparse.ArgumentParser(description="WSGI-сервер цифрового ежедневника")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    class ThreadingServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, fmt, *log_args):
            if not os.environ.get("PLANNER_QUIET"):
                super().log_message(fmt, *log_args)

    httpd = make_server(
        args.host, args.port, application, server_class=ThreadingServer, handler_class=QuietHandler
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"WSGI-сервер запущен: {url} (backend: {db.backend_name()})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
