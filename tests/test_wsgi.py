"""Тесты WSGI-входа (то, что работает на хостинге).

Проверяют тот же код, что и локальный сервер, но через WSGI-интерфейс:
JSON API, статику, SPA-маршруты, cookie сессии.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Если тесты API уже настроили базу в этом процессе — используем её.
if "server.db" not in sys.modules:
    os.environ.setdefault("PLANNER_DB", os.path.join(tempfile.mkdtemp(prefix="planner-wsgi-"), "wsgi.db"))
os.environ.setdefault("PLANNER_QUIET", "1")

from server import wsgi  # noqa: E402


def call(method="GET", path="/", body=None, cookie=None, query=""):
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(raw)),
        "CONTENT_TYPE": "application/json" if body is not None else "",
        "wsgi.input": io.BytesIO(raw),
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_COOKIE": cookie or "",
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "80",
        "wsgi.url_scheme": "http",
    }
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = int(status.split()[0])
        captured["headers"] = headers

    payload = b"".join(wsgi.application(environ, start_response))
    content_type = dict(captured["headers"]).get("Content-Type", "")
    parsed = json.loads(payload) if payload and content_type.startswith("application/json") else None
    return captured["status"], captured["headers"], parsed, payload


def session_cookie(headers):
    for name, value in headers:
        if name.lower() == "set-cookie" and value.startswith("planner_session="):
            return value.split(";", 1)[0]
    return None


class WsgiTests(unittest.TestCase):
    def setUp(self):
        self.login = "wsgi_" + uuid4().hex[:10]

    def test_health(self):
        status, _, body, _ = call(path="/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn(body["backend"], ("SQLite", "PostgreSQL"))

    def test_config(self):
        status, _, body, _ = call(path="/api/config")
        self.assertEqual(status, 200)
        self.assertIn("demoEnabled", body)
        self.assertIsInstance(body["demoEnabled"], bool)

    def test_index_page(self):
        status, headers, _, payload = call(path="/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", dict(headers)["Content-Type"])
        html = payload.decode("utf-8")
        self.assertIn("Планирование дня", html)
        self.assertIn("app.js", html)

    def test_spa_fallback(self):
        status, headers, _, _ = call(path="/tasks")
        self.assertEqual(status, 200)
        self.assertIn("text/html", dict(headers)["Content-Type"])

    def test_missing_asset(self):
        status, _, body, _ = call(path="/js/missing.js")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_path_traversal(self):
        status, _, _, _ = call(path="/../run.py")
        self.assertIn(status, (403, 404))

    def test_register_and_session(self):
        status, headers, body, _ = call(
            "POST",
            "/api/auth/register",
            {"login": self.login, "password": "secret123", "name": "WSGI"},
        )
        self.assertEqual(status, 200, body)
        cookie = session_cookie(headers)
        self.assertTrue(cookie)

        status, _, me, _ = call(path="/api/me", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["login"], self.login)

    def test_requires_auth(self):
        status, _, body, _ = call(path="/api/tasks")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_task_lifecycle(self):
        status, headers, _, _ = call(
            "POST",
            "/api/auth/register",
            {"login": self.login, "password": "secret123"},
        )
        self.assertEqual(status, 200)
        cookie = session_cookie(headers)

        status, _, created, _ = call(
            "POST",
            "/api/tasks",
            {"title": "Задача из WSGI", "priority": "high"},
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        task_id = created["task"]["id"]

        status, _, day, _ = call(path="/api/day", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(day["stats"]["total"], 1)

        status, _, updated, _ = call(
            "POST", f"/api/tasks/{task_id}/toggle", {"done": True}, cookie=cookie
        )
        self.assertEqual(status, 200)
        self.assertTrue(updated["task"]["done"])

        status, _, removed, _ = call("DELETE", f"/api/tasks/{task_id}", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(removed["task"]["status"], "deleted")

    def test_bad_json(self):
        raw = b"{not json"
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/tasks",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "wsgi.url_scheme": "http",
        }
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status

        payload = b"".join(wsgi.application(environ, start_response))
        self.assertIn("400", captured["status"])
        self.assertEqual(json.loads(payload)["error"]["code"], "invalid_json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
