"""Точка входа WSGI для gunicorn и хостингов.

    gunicorn app_wsgi:app --bind 0.0.0.0:8000
"""

from server.wsgi import application

app = application

__all__ = ["app", "application"]
