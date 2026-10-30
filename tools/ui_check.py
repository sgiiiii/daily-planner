"""Проверка интерфейса в настоящем браузере (Chrome + DevTools Protocol).

Скрипт сам поднимает сервер на временной базе, открывает приложение в headless
Chrome, проходит основные сценарии, проверяет результат и снимает скриншоты.

Запуск:
    python tools/ui_check.py                    # проверки + скриншоты
    python tools/ui_check.py --out screenshots  # своя папка
    python tools/ui_check.py --keep             # не удалять временные файлы
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cdp import CDP, free_port  # noqa: E402

CHROME_CANDIDATES = [
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, details: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  OK   {name}")
    else:
        FAILED.append(f"{name} {details}".strip())
        print(f"  FAIL {name} {details}")


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    raise SystemExit("Chrome/Edge не найден. Укажите путь в переменной CHROME_PATH.")


def start_server(port: int, db_path: str) -> subprocess.Popen:
    env = dict(os.environ)
    env["PLANNER_DB"] = db_path
    env["PLANNER_QUIET"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "run.py"), "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                if response.status == 200:
                    return process
        except Exception:
            time.sleep(0.2)
    process.terminate()
    raise SystemExit("Сервер не запустился")


def start_chrome(executable: str, profile: str, port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [
            executable,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--hide-scrollbars",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--window-size=1600,1100",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1):
                return process
        except Exception:
            time.sleep(0.25)
    process.terminate()
    raise SystemExit("Chrome не запустился")


def login(page: CDP, base: str) -> None:
    page.navigate(base + "/", "document.readyState === 'complete'")
    page.wait_for("!!document.querySelector('.auth')")
    page.fill("#auth-login", "demo")
    page.fill("#auth-password", "demo1234")
    page.click("[data-submit]")
    page.wait_for("!!document.querySelector('.app-header')", timeout=15)
    page.wait_for("!!document.querySelector('.dash')", timeout=15)


def run(page: CDP, base: str, shots: str) -> None:
    os.makedirs(shots, exist_ok=True)

    def shot(name: str) -> None:
        page.screenshot(os.path.join(shots, name))

    # ---------------------------------------------------------- вход
    print("\nВход и главный экран")
    page.set_viewport(1440, 1000)
    page.set_media("light")
    page.navigate(base + "/", "document.readyState === 'complete'")
    page.wait_for("!!document.querySelector('.auth')")
    shot("01-login-desktop.png")
    check("экран входа отрисован", page.count(".auth__form") == 1)
    check("демо-кнопка доступна", page.count("[data-demo]") == 1)

    login(page, base)
    page.wait_for("document.documentElement.dataset.theme === 'light'", timeout=10)
    shot("02-home-desktop.png")
    check("главная: приветствие", "Марсель" in page.text(".page-head h1"))
    check("главная: есть приоритетные задачи", page.count(".priority-list .task") >= 3)
    check("главная: быстрый ввод", page.count("[data-quick-add]") == 1)
    check("главная: сводка дня", page.count(".ring") == 1)
    check("шапка: 5 разделов", page.count(".main-nav__link") == 5)

    # ---------------------------------------------------------- задачи
    print("\nРаздел «Задачи»")
    page.click('a[data-nav="/tasks"]')
    page.wait_for("!!document.querySelector('.task-list')")
    page.wait_for("document.querySelectorAll('.task-list .task').length > 3")
    shot("03-tasks-desktop.png")
    total_tasks = page.count(".task-list .task")
    check("задачи: список загружен", total_tasks >= 6, f"({total_tasks})")

    page.click('[data-filter="work"]')
    page.wait_for("!!document.querySelector('[data-filter=\\'work\\'][aria-pressed=\\'true\\']')")
    page.wait_for("document.querySelectorAll('.task-list .task').length > 0")
    spheres = page.evaluate(
        "Array.from(document.querySelectorAll('.task-list .sphere')).map(n => n.textContent.trim())"
    )
    check("задачи: фильтр по сфере работает", all(item == "Работа" for item in spheres), str(spheres))

    page.click('[data-filter="all"]')
    page.wait_for("document.querySelectorAll('.task-list .task').length > 3")

    # Создание задачи через форму
    page.click("[data-act='add']")
    page.wait_for("!!document.querySelector('#task-title')")
    page.fill("#task-title", "Тестовая задача из браузера")
    page.fill("#task-date", time.strftime("%Y-%m-%d"))
    page.click("[data-save]")
    page.wait_for("!document.querySelector('#task-title')", timeout=10)
    page.wait_for(
        "Array.from(document.querySelectorAll('.task__title')).some(n => n.textContent.includes('Тестовая задача из браузера'))",
        timeout=10,
    )
    check("задачи: создание через форму", True)

    # Отметка выполнения
    page.evaluate(
        "(() => { const rows = Array.from(document.querySelectorAll('.task'));"
        " const row = rows.find(r => r.textContent.includes('Тестовая задача из браузера'));"
        " row.querySelector('.check').click(); return true; })()"
    )
    page.wait_for(
        "Array.from(document.querySelectorAll('.task')).some(n =>"
        " n.textContent.includes('Тестовая задача из браузера') && n.classList.contains('task--done'))",
        timeout=10,
    )
    check("задачи: отметка выполнения", True)

    # Карточка задачи
    page.evaluate(
        "(() => { const rows = Array.from(document.querySelectorAll('.task'));"
        " const row = rows.find(r => r.textContent.includes('Тестовая задача из браузера'));"
        " row.click(); return true; })()"
    )
    page.wait_for("!!document.querySelector('#modal[open]')")
    check("задача: карточка с действиями", page.count("#modal [data-delete]") == 1)
    page.click("#modal [data-modal-close]")
    page.wait_for("!document.querySelector('#modal[open]')")
    page.wait_for("!document.querySelector('#modal [data-delete]')", timeout=5)
    check("закрытие карточки очищает окно", True)

    # Удаление тестовой задачи
    page.evaluate(
        "(() => { const rows = Array.from(document.querySelectorAll('.task'));"
        " const row = rows.find(r => r.textContent.includes('Тестовая задача из браузера'));"
        " row.click(); return true; })()"
    )
    page.wait_for("!!document.querySelector('#modal [data-delete]')")
    page.click("#modal [data-delete]")
    page.wait_for("!!document.querySelector('#modal [data-confirm]')")
    page.click("#modal [data-confirm]")
    page.wait_for(
        "!Array.from(document.querySelectorAll('.task')).some(n => n.textContent.includes('Тестовая задача из браузера'))",
        timeout=10,
    )
    check("задачи: удаление с подтверждением", True)

    # ---------------------------------------------------------- календарь
    print("\nКалендарь")
    page.click('a[data-nav="/calendar"]')
    page.wait_for("!!document.querySelector('.calendar-week')")
    shot("04-calendar-week.png")
    check("календарь: неделя", page.count(".calendar-day") == 7)

    page.click("[data-mode='month']")
    page.wait_for("!!document.querySelector('.calendar-month')")
    page.wait_for("document.querySelectorAll('.calendar-month__cell').length === 42")
    shot("05-calendar-month.png")
    check("календарь: месяц 42 ячейки", page.count(".calendar-month__cell") == 42)

    page.evaluate(
        "(() => { const cells = Array.from(document.querySelectorAll('.calendar-month__cell'));"
        " const busy = cells.find(c => c.querySelector('.calendar-month__count'));"
        " busy.click(); return true; })()"
    )
    page.wait_for("!!document.querySelector('#modal[open] [data-day-content]')")
    page.wait_for("!!document.querySelector('#modal[open] .agenda-row')")
    shot("06-calendar-day-modal.png")
    check("календарь: день открывается списком", page.count("#modal .agenda-row") > 0)
    page.click("#modal [data-modal-close]")
    page.wait_for("!document.querySelector('#modal[open]')")

    page.click("[data-mode='day']")
    page.wait_for("!!document.querySelector('.calendar-day-view, .empty')")
    check("календарь: дневной вид", page.count(".calendar-day-view, .empty") >= 1)

    # ---------------------------------------------------------- итог дня
    print("\nИтог дня")
    page.click('a[data-nav="/review"]')
    page.wait_for("!!document.querySelector('.review-row')")
    shot("07-review-desktop.png")
    pending_before = page.count(".review-row")
    moved_before = page.count(".task [data-undo-move]")

    page.evaluate("document.querySelector('.review-row [data-move]').click()")
    page.wait_for("!!document.querySelector('[data-undo-move]')", timeout=10)
    check("итог: задача перенесена на завтра", page.count("[data-undo-move]") > moved_before)
    check("итог: появился тост с отменой", page.count(".toast [class='toast__action']") >= 1)
    check("итог: список разбора уменьшился", page.count(".review-row") < pending_before)

    page.evaluate(
        "(() => { const toasts = Array.from(document.querySelectorAll('.toast'));"
        " const last = toasts[toasts.length - 1];"
        " const action = last.querySelector('.toast__action');"
        " if (!action) throw new Error('в последнем тосте нет действия');"
        " action.click(); return true; })()"
    )
    page.wait_for("!document.querySelector('[data-undo-move]')", timeout=15)
    check("итог: перенос отменяется", page.count(".review-row") == pending_before)

    page.click("[data-confirm]")
    page.wait_for("!!document.querySelector('.review-final')", timeout=10)
    shot("08-review-final.png")
    check("итог: финальный экран с числами", page.count(".review-final__numbers") == 1)

    # ---------------------------------------------------------- профиль и тема
    print("\nПрофиль и темы")
    page.click('a[data-nav="/profile"]')
    page.wait_for("!!document.querySelector('[data-section]')")
    page.click('[data-section="appearance"]')
    page.wait_for("!!document.querySelector('[data-theme-option]')")
    page.click('[data-theme-option="dark"]')
    page.wait_for("document.documentElement.dataset.theme === 'dark'", timeout=10)
    check("тема: переключение на тёмную", True)
    shot("09-profile-dark.png")

    page.click('a[data-nav="/"]')
    page.wait_for("!!document.querySelector('.dash')")
    page.wait_for("document.documentElement.dataset.theme === 'dark'")
    shot("10-home-dark.png")

    page.click("[data-theme-toggle]")
    page.wait_for("document.documentElement.dataset.theme === 'light'", timeout=10)
    check("тема: переключатель в шапке", True)

    # ---------------------------------------------------------- мобильная версия
    print("\nМобильная версия (390×844)")
    page.set_viewport(390, 844, mobile=True)
    page.navigate(base + "/", "document.readyState === 'complete'")
    page.wait_for("!!document.querySelector('.dash')")
    page.wait_for("document.documentElement.dataset.theme === 'light'")
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("мобильная: нет горизонтальной прокрутки", overflow <= 1, f"({overflow}px)")
    check("мобильная: нижняя навигация", page.evaluate("getComputedStyle(document.querySelector('.bottom-nav')).display") == "grid")
    check("мобильная: 4 пункта меню", page.count(".bottom-nav__link") == 4)
    check("мобильная: кнопка быстрого добавления", page.evaluate("getComputedStyle(document.querySelector('.fab')).display") != "none")
    shot("11-mobile-home.png")

    page.click('a[data-nav="/tasks"]')
    page.wait_for("!!document.querySelector('.task-list')")
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("мобильные задачи: без прокрутки", overflow <= 1, f"({overflow}px)")
    shot("12-mobile-tasks.png")

    page.click('a[data-nav="/calendar"]')
    page.wait_for("!!document.querySelector('.calendar-day-view, .calendar-week, .empty')")
    page.wait_for("document.querySelectorAll('.calendar-day-view .agenda-row').length > 0", timeout=10)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("мобильный календарь: без прокрутки", overflow <= 1, f"({overflow}px)")
    check("мобильный календарь открывается на день", page.count(".calendar-day-view") >= 1)
    shot("13-mobile-calendar.png")

    page.click('a[data-nav="/review"]')
    page.wait_for("!!document.querySelector('.review-row')")
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("мобильный итог дня: без прокрутки", overflow <= 1, f"({overflow}px)")
    shot("14-mobile-review.png")

    page.click('a[data-nav="/profile"]')
    page.wait_for("!!document.querySelector('[data-section]')")
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("мобильный профиль: без прокрутки", overflow <= 1, f"({overflow}px)")
    shot("15-mobile-profile.png")

    # ---------------------------------------------------------- модальное окно на телефоне
    page.click('a[data-nav="/"]')
    page.wait_for("!!document.querySelector('.dash')")
    page.click("[data-fab]")
    page.wait_for("!!document.querySelector('#task-title')")
    shot("16-mobile-task-form.png")
    fits = page.evaluate(
        "(() => { const d = document.querySelector('#modal');"
        " const r = d.getBoundingClientRect();"
        " return r.width <= window.innerWidth && r.bottom <= window.innerHeight + 1; })()"
    )
    check("мобильная форма задачи помещается в экран", bool(fits))
    page.click("#modal [data-cancel]")
    page.wait_for("!document.querySelector('#modal[open]')")

    # ---------------------------------------------------------- регистрация
    print("\nВыход и регистрация нового пользователя")
    page.set_viewport(1440, 1000)
    page.click('a[data-nav="/profile"]')
    page.wait_for("!!document.querySelector('[data-section]')")
    page.click('[data-section="data"]')
    page.wait_for("!!document.querySelector('[data-logout]')")
    page.click("[data-logout]")
    page.wait_for("!!document.querySelector('#modal [data-confirm]')")
    page.click("#modal [data-confirm]")
    page.wait_for("!!document.querySelector('.auth')", timeout=10)
    check("выход из аккаунта", page.count(".auth__form") == 1)

    page.click('[data-mode="register"]')
    page.wait_for("!document.querySelector('[data-name-field]').hidden")
    page.fill("#auth-name", "Новый пользователь")
    page.fill("#auth-login", "newbie_" + str(int(time.time())))
    page.fill("#auth-password", "password123")
    page.click("[data-submit]")
    page.wait_for("!!document.querySelector('.dash')", timeout=15)
    check("регистрация нового аккаунта", "Новый пользователь" in page.text(".page-head h1"))
    check("новый аккаунт: пустое состояние", page.count(".empty") >= 1)
    shot("17-new-account.png")

    page.fill("#quick-title", "Первая задача нового пользователя")
    page.evaluate("document.querySelector('[data-quick-add]').requestSubmit()")
    page.wait_for(
        "Array.from(document.querySelectorAll('.task__title')).some(n => n.textContent.includes('Первая задача'))",
        timeout=10,
    )
    check("быстрое добавление задачи", True)

    shortcut = page.evaluate(
        "(() => { document.body.focus();"
        " const event = new KeyboardEvent('keydown', {key: 'n', bubbles: true});"
        " document.dispatchEvent(event); return true; })()"
    )
    page.wait_for("!!document.querySelector('#task-title')", timeout=10)
    check("горячая клавиша N открывает форму", bool(shortcut))
    page.click("#modal [data-cancel]")
    page.wait_for("!document.querySelector('#modal[open]')")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "screenshots"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    chrome = find_chrome()
    temp = tempfile.mkdtemp(prefix="planner-ui-")
    server = None
    browser = None
    page = None
    try:
        server_port = free_port()
        server = start_server(server_port, os.path.join(temp, "ui.db"))
        base = f"http://127.0.0.1:{server_port}"
        debug_port = free_port()
        browser = start_chrome(chrome, os.path.join(temp, "profile"), debug_port)
        page = CDP(debug_port)
        page.enable()
        try:
            run(page, base, args.out)
        except Exception:
            # Диагностика: без неё в логах CI видно только текст ожидания.
            print("\n--- ДИАГНОСТИКА НА МОМЕНТ ОШИБКИ ---")
            try:
                print("URL:", page.evaluate("location.href"))
                print("dialog open:", page.evaluate("!!document.querySelector('#modal[open]')"))
                print("dialog html:", str(page.evaluate("(document.querySelector('#modal')||{}).outerHTML || ''"))[:1500])
                print("visible buttons:", page.evaluate(
                    "Array.from(document.querySelectorAll('#modal button')).map(b => b.textContent.trim()).join(' | ')"
                ))
                print("console errors:", page.console_errors[:5])

            except Exception as diag_error:
                print("диагностика недоступна:", diag_error)
            raise

        if page.console_errors:
            for error in page.console_errors:
                print(f"  JS ERROR: {error}")
            FAILED.append("ошибки в консоли браузера")
        else:
            check("консоль браузера без ошибок", True)

        print("\nИтог: успешно %d, провалов %d" % (len(PASSED), len(FAILED)))
        if FAILED:
            print("Провалы:")
            for item in FAILED:
                print("  -", item)
            return 1
        print(f"Скриншоты: {os.path.abspath(args.out)}")
        return 0
    finally:
        try:
            page and page.close()
        except Exception:
            pass
        for process in (browser, server):
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        if not args.keep:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
