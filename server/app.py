"""HTTP-сервер для локальной разработки.

Обслуживает REST API (/api/...) и статический интерфейс (web/) без внешних
зависимостей. В продакшене тот же код работает через WSGI (``server/wsgi.py``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import api, auth, db, scheduler, seed, settings, static
from .errors import ApiError

MAX_BODY = 1_000_000


class Handler(BaseHTTPRequestHandler):
    server_version = "DailyPlanner/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    # Служебное
    # ------------------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:
        if os.environ.get("PLANNER_QUIET"):
            return
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if content_type.startswith("text/html"):
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "no-cache")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict, cookies_out: list[str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for line in cookies_out or []:
            self.send_header("Set-Cookie", line)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, code: str, message: str, fields: dict | None = None) -> None:
        self._send_json(status, ApiError(status, code, message, fields).payload())

    def _session_token(self) -> str | None:
        header = cookies.SimpleCookie()
        if self.headers.get("Cookie"):
            try:
                header.load(self.headers["Cookie"])
            except cookies.CookieError:
                return None
        morsel = header.get(auth.COOKIE_NAME)
        return morsel.value if morsel else None

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ApiError(413, "payload_too_large", "Слишком большой запрос")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "invalid_json", "Тело запроса должно быть корректным JSON") from None
        if not isinstance(data, dict):
            raise ApiError(400, "invalid_json", "Ожидался JSON-объект")
        return data

    # ------------------------------------------------------------------
    # Маршрутизация
    # ------------------------------------------------------------------
    def do_GET(self) -> None:
        self._handle("GET")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api"):
            self._handle_api(method, path, parsed.query)
        else:
            self._handle_static(method, path)

    def _handle_api(self, method: str, path: str, query: str) -> None:
        try:
            body = self._read_body() if method in ("POST", "PATCH", "PUT") else {}
            with db.session() as conn:
                status, payload, cookies_out = api.dispatch(
                    conn,
                    method,
                    path,
                    query,
                    body,
                    self._session_token(),
                    self.client_address[0],
                )
        except ApiError as error:
            self._send_json(error.status, error.payload())
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            traceback.print_exc()
            self._error(500, "server_error", "Внутренняя ошибка сервера")
            return
        self._send_json(status, payload, cookies_out)

    def _handle_static(self, method: str, path: str) -> None:
        if method not in ("GET", "HEAD"):
            self._error(405, "method_not_allowed", "Метод не поддерживается")
            return
        try:
            result = static.resolve(path)
        except PermissionError:
            self._error(403, "forbidden", "Доступ запрещён")
            return
        if result is None:
            self._error(404, "not_found", "Файл не найден")
            return
        body, content_type = result
        self._send(200, body, content_type, static.SECURITY_HEADERS)


class PlannerServer(ThreadingHTTPServer):
    """HTTP-сервер, который не считает обрыв соединения аварийной ситуацией."""

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        error = sys.exc_info()[1]
        if isinstance(
            error,
            (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError),
        ):
            return
        super().handle_error(request, client_address)





def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Цифровой ежедневник — локальный сервер")
    parser.add_argument("--host", default="127.0.0.1", help="адрес (по умолчанию 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="порт (по умолчанию 8000)")
    parser.add_argument("--open", action="store_true", help="открыть браузер после запуска")
    parser.add_argument("--reset", action="store_true", help="удалить базу данных и начать заново")
    args = parser.parse_args(argv)

    if args.reset and not db.USE_POSTGRES and os.path.exists(db.DB_PATH):
        for suffix in ("", "-wal", "-shm"):
            path = db.DB_PATH + suffix
            if os.path.exists(path):
                os.remove(path)
        print("База данных удалена, создаём новую.")

    db.init_db()
    with db.session() as conn:
        created = seed.ensure_demo(conn)
        conn.commit()
    if created:
        print("Создан демонстрационный аккаунт: demo / demo1234")

    stop_event = scheduler.start() if settings.SCHEDULER_ENABLED else threading.Event()

    httpd = PlannerServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print("Цифровой ежедневник запущен: " + url)
    print(f"База данных: {db.backend_name()}. Остановка — Ctrl+C.")
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        stop_event.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
