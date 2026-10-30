"""Ошибки уровня API."""

from __future__ import annotations


class ApiError(Exception):
    """Ошибка, которую сервер возвращает клиенту в виде JSON."""

    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}

    def payload(self) -> dict:
        data = {"error": {"code": self.code, "message": self.message}}
        if self.fields:
            data["error"]["fields"] = self.fields
        return data
