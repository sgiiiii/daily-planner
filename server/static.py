"""Раздача статики и общие заголовки безопасности.

Используется и локальным сервером (``server/app.py``), и WSGI-приложением
(``server/wsgi.py``), чтобы поведение в разработке и в продакшене совпадало:
SPA-маршруты отдают ``index.html``, отсутствующие файлы — 404, выход за
пределы каталога запрещён.
"""

from __future__ import annotations

import mimetypes
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}


def resolve(path: str) -> tuple[bytes, str] | None:
    """Вернуть (содержимое, Content-Type) или None, если файла нет."""
    relative = path.lstrip("/") or "index.html"
    root = os.path.realpath(WEB_DIR)
    candidate = os.path.realpath(os.path.join(root, relative))
    if not (candidate == root or candidate.startswith(root + os.sep)):
        raise PermissionError("Путь выходит за пределы каталога web/")
    if not os.path.isfile(candidate):
        # SPA: «красивые» адреса (/tasks) отдают index.html,
        # отсутствующие файлы с расширением — 404.
        if "." in os.path.basename(relative):
            return None
        candidate = os.path.join(root, "index.html")
        if not os.path.isfile(candidate):
            return None
    with open(candidate, "rb") as handle:
        body = handle.read()
    extension = os.path.splitext(candidate)[1].lower()
    content_type = (
        STATIC_TYPES.get(extension)
        or mimetypes.guess_type(candidate)[0]
        or "application/octet-stream"
    )
    return body, content_type
