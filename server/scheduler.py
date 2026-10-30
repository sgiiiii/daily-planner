"""Фоновый планировщик: ежедневный перенос невыполненных задач.

Поток запускается один раз на процесс. Перенос защищён атомарным «захватом»
в ``planner.rollover_if_due``, поэтому несколько worker-процессов не мешают
друг другу.
"""

from __future__ import annotations

import threading
import traceback

from . import db, planner


def loop(stop_event: threading.Event, interval: int = 30) -> None:
    while not stop_event.wait(interval):
        try:
            with db.session() as conn:
                users = conn.execute("SELECT * FROM users").fetchall()
                for user in users:
                    planner.rollover_if_due(conn, user)
                conn.commit()
        except Exception:
            traceback.print_exc()


def start(interval: int = 30) -> threading.Event:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=loop,
        args=(stop_event, interval),
        name="planner-scheduler",
        daemon=True,
    )
    thread.start()
    return stop_event
