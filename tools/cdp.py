"""Минимальный клиент Chrome DevTools Protocol (без внешних зависимостей).

Используется служебным скриптом tools/ui_check.py, чтобы открывать приложение
в настоящем браузере, эмулировать размеры экрана, нажимать кнопки и снимать
скриншоты. Реализована только та часть протокола, которая нужна для проверки.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebSocket:
    """Клиент WebSocket поверх stdlib (текстовые кадры, маскирование)."""

    def __init__(self, url: str, timeout: float = 30.0):
        assert url.startswith("ws://"), "Поддерживается только ws://"
        rest = url[len("ws://"):]
        host_port, path = rest.split("/", 1) if "/" in rest else (rest, "")
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buffer = b""
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("Соединение закрыто при рукопожатии")
            response += chunk
        head, _, tail = response.partition(b"\r\n\r\n")
        self.buffer = tail
        if b"101" not in head.split(b"\r\n")[0]:
            raise RuntimeError("WebSocket handshake failed: " + head.decode(errors="replace"))
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expected.encode() not in head:
            raise RuntimeError("Неверный Sec-WebSocket-Accept")

    # ------------------------------------------------------------------ кадры
    def _read_exact(self, size: int) -> bytes:
        while len(self.buffer) < size:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("WebSocket закрыт")
            self.buffer += chunk
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def _read_frame(self):
        header = self._read_exact(2)
        fin = header[0] & 0x80
        opcode = header[0] & 0x0F
        masked = header[1] & 0x80
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return bool(fin), opcode, payload

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", 0x81, 0x80 | length)
        elif length < 1 << 16:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def recv(self) -> str:
        parts = []
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == 0x9:  # ping
                self.sock.sendall(struct.pack("!BB", 0x8A, 0x80) + os.urandom(4))
                continue
            if opcode == 0x8:  # close
                raise ConnectionError("WebSocket закрыт браузером")
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    """Одна страница браузера: навигация, JS, скриншоты."""

    def __init__(self, port: int, timeout: float = 30.0):
        self.port = port
        deadline = time.time() + timeout
        target = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                    targets = json.loads(response.read())
                for item in targets:
                    if item.get("type") == "page":
                        target = item
                        break
                if target:
                    break
            except Exception:
                time.sleep(0.3)
        if not target:
            raise RuntimeError("Не удалось получить список вкладок Chrome")
        self.ws = WebSocket(target["webSocketDebuggerUrl"], timeout=timeout)
        self.next_id = 0
        self.events: list[dict] = []
        self.console_errors: list[str] = []

    def send(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        message_id = self.next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self._handle_event(message)

    def _handle_event(self, message: dict) -> None:
        self.events.append(message)
        method = message.get("method")
        if method == "Runtime.exceptionThrown":
            details = message.get("params", {}).get("exceptionDetails", {})
            self.console_errors.append(details.get("text", "JS exception"))
        elif method == "Log.entryAdded":
            entry = message.get("params", {}).get("entry", {})
            if entry.get("level") == "error" and entry.get("source") != "network":
                self.console_errors.append(entry.get("text", "console error"))
        elif method == "Runtime.consoleAPICalled":
            params = message.get("params", {})
            if params.get("type") == "error":
                args = ", ".join(str(item.get("value", item.get("description", ""))) for item in params.get("args", []))
                self.console_errors.append(args)

    def enable(self) -> None:
        for domain in ("Page", "Runtime", "Log", "Network"):
            try:
                self.send(f"{domain}.enable")
            except RuntimeError:
                pass

    def set_viewport(self, width: int, height: int, mobile: bool = False) -> None:
        self.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": mobile,
            },
        )

    def set_media(self, color_scheme: str = "light") -> None:
        self.send(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": color_scheme}]},
        )

    def navigate(self, url: str, wait: str = "document.readyState === 'complete'", timeout: float = 20.0) -> None:
        self.send("Page.navigate", {"url": url})
        self.wait_for(wait, timeout=timeout)

    def evaluate(self, expression: str, timeout: float = 20.0):
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise RuntimeError(details.get("exception", {}).get("description") or details.get("text", "JS error"))
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, timeout: float = 20.0, interval: float = 0.15) -> None:
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                if self.evaluate(expression):
                    return
                last_error = None
            except RuntimeError as error:
                last_error = error
            time.sleep(interval)
        raise TimeoutError(f"Не дождались условия: {expression}" + (f" ({last_error})" if last_error else ""))

    def screenshot(self, path: str, full_page: bool = False) -> None:
        params = {"format": "png", "captureBeyondViewport": False}
        if full_page:
            params["captureBeyondViewport"] = True
        data = self.send("Page.captureScreenshot", params)
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(data["data"]))

    def click(self, selector: str) -> None:
        self.evaluate(
            "(() => { const el = document.querySelector(%s); if (!el) throw new Error('нет элемента: ' + %s);"
            " el.scrollIntoView({block:'center'}); el.click(); return true; })()"
            % (json.dumps(selector), json.dumps(selector))
        )

    def fill(self, selector: str, value: str) -> None:
        self.evaluate(
            "(() => { const el = document.querySelector(%s); if (!el) throw new Error('нет поля: ' + %s);"
            " el.focus(); el.value = %s;"
            " el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true})); return true; })()"
            % (json.dumps(selector), json.dumps(selector), json.dumps(value))
        )

    def count(self, selector: str) -> int:
        return int(self.evaluate(f"document.querySelectorAll({json.dumps(selector)}).length"))

    def text(self, selector: str) -> str:
        return str(self.evaluate(f"(document.querySelector({json.dumps(selector)})||{{}}).textContent || ''")).strip()

    def close(self) -> None:
        self.ws.close()
