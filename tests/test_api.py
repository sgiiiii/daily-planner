"""Интеграционные тесты REST API.

Запуск:  python -m unittest discover -s tests -v
Тесты поднимают настоящий HTTP-сервер на свободном порту и отдельную БД.
"""

import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import quote
from uuid import uuid4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEMP_DIR = tempfile.mkdtemp(prefix="planner-tests-")
PG_URL = (os.environ.get("PLANNER_TEST_DATABASE_URL") or "").strip()
if PG_URL:
    os.environ["DATABASE_URL"] = PG_URL
    os.environ["PLANNER_DB_RESET"] = "1"
else:
    os.environ["PLANNER_DB"] = os.path.join(TEMP_DIR, "test.db")
os.environ["PLANNER_QUIET"] = "1"

from server import app as server_app  # noqa: E402
from server import auth, db, planner, seed  # noqa: E402
from server import api as server_api  # noqa: E402

SERVER = None
BASE = ""
THREAD = None


def setUpModule():
    global SERVER, BASE, THREAD
    db.init_db()
    with db.session() as conn:
        seed.ensure_demo(conn)
        conn.commit()
    SERVER = ThreadingHTTPServer(("127.0.0.1", 0), server_app.Handler)
    SERVER.daemon_threads = True
    BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"
    THREAD = threading.Thread(target=SERVER.serve_forever, daemon=True)
    THREAD.start()


def tearDownModule():
    if SERVER:
        SERVER.shutdown()
        SERVER.server_close()


class Client:
    """Мини-клиент с cookie-jar, как у браузера."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(self, method, path, payload=None):
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read()
            body = json.loads(raw) if raw else {}
            return error.code, body

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload=None):
        return self.request("POST", path, payload or {})

    def patch(self, path, payload=None):
        return self.request("PATCH", path, payload or {})

    def delete(self, path):
        return self.request("DELETE", path)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        server_api.LIMITER.reset()
        self.client = Client()
        self.login = "user_" + uuid4().hex[:10]
        status, body = self.client.post(
            "/api/auth/register",
            {"login": self.login, "password": "secret123", "name": "Тест"},
        )
        self.assertEqual(status, 200, body)
        self.user = body["user"]
        # Отключаем ленивый автоперенос, чтобы он не мешал проверкам просрочки.
        with db.session() as conn:
            conn.execute(
                "UPDATE users SET last_rollover = ? WHERE id = ?",
                (planner.today_str(), self.user["id"]),
            )
            conn.commit()

    def create_task(self, **overrides):
        payload = {
            "title": "Проверить макет",
            "date": planner.today_str(),
            "sphere": "work",
            "priority": "high",
        }
        payload.update(overrides)
        status, body = self.client.post("/api/tasks", payload)
        self.assertEqual(status, 200, body)
        return body["task"]


class AuthTests(ApiTestCase):
    def test_me_requires_session(self):
        status, body = Client().get("/api/me")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_me_returns_current_user(self):
        status, body = self.client.get("/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["login"], self.login)

    def test_duplicate_login(self):
        status, body = Client().post(
            "/api/auth/register", {"login": self.login, "password": "secret123"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "login_taken")

    def test_short_password_rejected(self):
        status, body = Client().post(
            "/api/auth/register", {"login": "shorty", "password": "123"}
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["fields"]["password"], "short")

    def test_bad_login_rejected(self):
        status, body = Client().post(
            "/api/auth/register", {"login": "a", "password": "secret123"}
        )
        self.assertEqual(status, 422)

    def test_login_and_logout(self):
        client = Client()
        status, body = client.post("/api/auth/login", {"login": self.login, "password": "secret123"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["user"]["name"], "Тест")
        status, _ = client.post("/api/auth/logout")
        self.assertEqual(status, 200)
        status, _ = client.get("/api/me")
        self.assertEqual(status, 401)

    def test_wrong_password(self):
        status, body = Client().post(
            "/api/auth/login", {"login": self.login, "password": "nope-nope"}
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "bad_credentials")

    def test_change_password(self):
        status, body = self.client.post(
            "/api/me/password", {"current": "secret123", "password": "secret456"}
        )
        self.assertEqual(status, 200, body)
        fresh = Client()
        status, _ = fresh.post("/api/auth/login", {"login": self.login, "password": "secret456"})
        self.assertEqual(status, 200)
        status, _ = fresh.post("/api/auth/login", {"login": self.login, "password": "secret123"})
        self.assertEqual(status, 401)

    def test_settings_update(self):
        status, body = self.client.patch(
            "/api/me", {"name": "Новое имя", "theme": "dark", "rolloverTime": "03:30"}
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["user"]["name"], "Новое имя")
        self.assertEqual(body["user"]["theme"], "dark")
        self.assertEqual(body["user"]["rolloverTime"], "03:30")

    def test_invalid_theme(self):
        status, body = self.client.patch("/api/me", {"theme": "neon"})
        self.assertEqual(status, 422)


class TaskTests(ApiTestCase):
    def test_create_with_defaults(self):
        status, body = self.client.post("/api/tasks", {"title": "  Позвонить  "})
        self.assertEqual(status, 200, body)
        task = body["task"]
        self.assertEqual(task["title"], "Позвонить")
        self.assertEqual(task["sphere"], "personal")
        self.assertEqual(task["priority"], "normal")
        self.assertEqual(task["date"], planner.today_str())
        self.assertFalse(task["done"])
        self.assertEqual(task["status"], "open")

    def test_create_validation(self):
        cases = [
            ({"title": ""}, "title_required"),
            ({"title": "x" * 201}, "title_too_long"),
            ({"title": "ok", "date": "2000-01-01"}, "date_in_past"),
            ({"title": "ok", "date": "01.02.2026"}, "date_invalid"),
            ({"title": "ok", "time": "25:00"}, "time_invalid"),
            ({"title": "ok", "sphere": "space"}, "sphere_invalid"),
            ({"title": "ok", "priority": "max"}, "priority_invalid"),
        ]
        for payload, code in cases:
            with self.subTest(code=code):
                status, body = self.client.post("/api/tasks", payload)
                self.assertEqual(status, 422)
                self.assertEqual(body["error"]["code"], code)

    def test_list_and_filters(self):
        self.create_task(title="Рабочее", sphere="work", priority="urgent")
        self.create_task(title="Личное", sphere="personal", priority="low")
        done_task = self.create_task(title="Готово", sphere="study")
        self.client.post(f"/api/tasks/{done_task['id']}/toggle", {"done": True})

        status, body = self.client.get("/api/tasks?date=" + planner.today_str())
        self.assertEqual(status, 200)
        self.assertEqual(len(body["tasks"]), 3)
        self.assertEqual(body["tasks"][0]["priority"], "urgent")

        status, body = self.client.get("/api/tasks?sphere=work")
        self.assertEqual([task["title"] for task in body["tasks"]], ["Рабочее"])

        status, body = self.client.get("/api/tasks?status=done")
        self.assertEqual([task["title"] for task in body["tasks"]], ["Готово"])

        status, body = self.client.get("/api/tasks?status=open")
        self.assertEqual(len(body["tasks"]), 2)

        status, body = self.client.get("/api/tasks?q=" + quote("Личн"))
        self.assertEqual(len(body["tasks"]), 1)

    def test_toggle_and_update(self):
        task = self.create_task()
        status, body = self.client.post(f"/api/tasks/{task['id']}/toggle", {"done": True})
        self.assertEqual(status, 200)
        self.assertTrue(body["task"]["done"])
        self.assertEqual(body["task"]["status"], "done")

        status, body = self.client.patch(
            f"/api/tasks/{task['id']}",
            {"title": "Новый заголовок", "priority": "urgent", "time": "18:30", "note": "детали"},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["task"]["title"], "Новый заголовок")
        self.assertEqual(body["task"]["priority"], "urgent")
        self.assertEqual(body["task"]["time"], "18:30")
        self.assertEqual(body["task"]["note"], "детали")

        status, body = self.client.post(f"/api/tasks/{task['id']}/toggle", {"done": False})
        self.assertFalse(body["task"]["done"])

    def test_delete_and_restore(self):
        task = self.create_task()
        status, body = self.client.delete(f"/api/tasks/{task['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["task"]["status"], "deleted")
        status, _ = self.client.get(f"/api/tasks/{task['id']}")
        self.assertEqual(status, 404)

        status, body = self.client.post(f"/api/tasks/{task['id']}/restore")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["task"]["status"], "open")

    def test_cannot_touch_foreign_task(self):
        task = self.create_task()
        stranger = Client()
        status, _ = stranger.post(
            "/api/auth/register", {"login": "other_" + uuid4().hex[:8], "password": "secret123"}
        )
        self.assertEqual(status, 200)
        status, body = stranger.get(f"/api/tasks/{task['id']}")
        self.assertEqual(status, 404)
        status, _ = stranger.patch(f"/api/tasks/{task['id']}", {"title": "хак"})
        self.assertEqual(status, 404)
        status, _ = stranger.delete(f"/api/tasks/{task['id']}")
        self.assertEqual(status, 404)

    def test_carry_manual(self):
        task = self.create_task()
        tomorrow = planner.add_days(planner.today_str(), 1)
        status, body = self.client.post(f"/api/tasks/{task['id']}/carry", {"date": tomorrow})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["task"]["date"], tomorrow)
        self.assertEqual(body["task"]["carried"], 1)

    def test_rollover_moves_overdue(self):
        overdue_id = self._insert_task_in_past()
        status, body = self.client.post("/api/rollover")
        self.assertEqual(status, 200, body)
        self.assertGreaterEqual(body["moved"], 1)
        status, body = self.client.get(f"/api/tasks/{overdue_id}")
        self.assertEqual(body["task"]["date"], planner.today_str())
        self.assertEqual(body["task"]["carried"], 1)
        self.assertEqual(body["task"]["carriedFrom"], planner.add_days(planner.today_str(), -1))

    def test_rollover_keeps_priority_and_sphere(self):
        overdue_id = self._insert_task_in_past()
        self.client.post("/api/rollover")
        _, body = self.client.get(f"/api/tasks/{overdue_id}")
        self.assertEqual(body["task"]["priority"], "urgent")
        self.assertEqual(body["task"]["sphere"], "study")

    def _insert_task_in_past(self):
        with db.session() as conn:
            task_id = db.insert_returning_id(
                conn,
                """INSERT INTO tasks (user_id, title, sphere, priority, due_date,
                                      created_at, updated_at)
                   VALUES (?, 'Просроченная', 'study', 'urgent', ?, ?, ?)""",
                (
                    self.user["id"],
                    planner.add_days(planner.today_str(), -1),
                    planner.now_str(),
                    planner.now_str(),
                ),
            )
            conn.commit()
            return task_id


class DayTests(ApiTestCase):
    def test_day_payload(self):
        task = self.create_task()
        self.client.post(f"/api/tasks/{task['id']}/toggle", {"done": True})
        status, body = self.client.get("/api/day")
        self.assertEqual(status, 200)
        self.assertEqual(body["stats"]["total"], 1)
        self.assertEqual(body["stats"]["done"], 1)
        self.assertEqual(body["stats"]["percent"], 100)

    def test_summary_priorities_and_counts(self):
        low = self.create_task(title="Мелочь", priority="low")
        urgent = self.create_task(title="Горит", priority="urgent", time="09:00")
        high = self.create_task(title="Важно", priority="high")
        self.client.post(f"/api/tasks/{low['id']}/toggle", {"done": True})

        status, body = self.client.get("/api/summary")
        self.assertEqual(status, 200, body)
        titles = [task["title"] for task in body["priorities"]]
        self.assertEqual(titles[0], "Горит")
        self.assertIn("Важно", titles)
        self.assertEqual(body["stats"]["done"], 1)
        self.assertEqual(body["stats"]["total"], 3)
        self.assertIn("tomorrow", body)

    def test_review_and_confirm(self):
        done_task = self.create_task(title="Сделано")
        open_task = self.create_task(title="Не сделано")
        self.client.post(f"/api/tasks/{done_task['id']}/toggle", {"done": True})

        status, body = self.client.get("/api/review")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["done"]), 1)
        self.assertEqual(len(body["open"]), 1)
        self.assertFalse(body["reviewed"])

        status, body = self.client.post("/api/review/confirm", {"date": planner.today_str()})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["confirmed"])
        self.assertEqual(body["stats"]["done"], 1)
        self.assertEqual(body["stats"]["total"], 2)
        self.assertEqual(body["open"], 1)

        status, body = self.client.get("/api/review")
        self.assertTrue(body["reviewed"])

    def test_carry_all(self):
        self.create_task(title="Один")
        self.create_task(title="Два")
        done = self.create_task(title="Три")
        self.client.post(f"/api/tasks/{done['id']}/toggle", {"done": True})

        status, body = self.client.post("/api/review/carry-all", {"date": planner.today_str()})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["moved"], 2)
        _, body = self.client.get("/api/tasks?status=open&date=" + planner.add_days(planner.today_str(), 1))
        self.assertEqual(len(body["tasks"]), 2)

    def test_overdue_list(self):
        with db.session() as conn:
            conn.execute(
                """INSERT INTO tasks (user_id, title, sphere, priority, due_date, created_at, updated_at)
                   VALUES (?, 'Старая', 'personal', 'normal', ?, ?, ?)""",
                (
                    self.user["id"],
                    planner.add_days(planner.today_str(), -2),
                    planner.now_str(),
                    planner.now_str(),
                ),
            )
            conn.commit()
        status, body = self.client.get("/api/tasks?status=overdue")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["tasks"]), 1)
        self.assertTrue(body["tasks"][0]["overdue"])


class CalendarTests(ApiTestCase):
    def test_events_crud(self):
        today = planner.today_str()
        status, body = self.client.post(
            "/api/events",
            {"title": "Созвон", "date": today, "start": "11:00", "end": "12:00"},
        )
        self.assertEqual(status, 200, body)
        event = body["event"]
        self.assertEqual(event["start"], "11:00")

        status, body = self.client.get(f"/api/events?from={today}&to={today}")
        self.assertEqual(len(body["events"]), 1)

        status, body = self.client.patch(
            f"/api/events/{event['id']}", {"title": "Созвон с командой"}
        )
        self.assertEqual(body["event"]["title"], "Созвон с командой")

        status, body = self.client.post(
            "/api/events", {"title": "Кривое", "date": today, "start": "12:00", "end": "11:00"}
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "time_order")

        status, _ = self.client.delete(f"/api/events/{event['id']}")
        self.assertEqual(status, 200)
        _, body = self.client.get(f"/api/events?from={today}&to={today}")
        self.assertEqual(body["events"], [])

    def test_calendar_returns_tasks_and_events(self):
        today = planner.today_str()
        self.create_task(title="Со временем", time="09:00")
        self.create_task(title="Без времени")
        self.client.post("/api/events", {"title": "Встреча", "date": today, "start": "10:00"})

        status, body = self.client.get(f"/api/calendar?from={today}&to={today}")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["tasks"]), 2)
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["today"], today)

    def test_calendar_range_guard(self):
        status, body = self.client.get("/api/calendar?from=2026-01-01&to=2026-12-31")
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "range_too_large")


class StaticTests(unittest.TestCase):
    def test_index_page_served(self):
        request = urllib.request.Request(BASE + "/")
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
            html = response.read().decode("utf-8")
        self.assertIn("Планирование дня", html)
        self.assertIn("app.js", html)

    def test_spa_route_fallback(self):
        with urllib.request.urlopen(BASE + "/tasks") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])

    def test_missing_asset(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(BASE + "/js/missing.js")
        self.assertEqual(context.exception.code, 404)

    def test_path_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(BASE + "/../run.py")
        self.assertIn(context.exception.code, (403, 404))


if __name__ == "__main__":
    unittest.main(verbosity=2)
