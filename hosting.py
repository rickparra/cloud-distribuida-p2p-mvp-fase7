"""Three-minute, in-memory hosting of small demonstration HTML pages."""

from __future__ import annotations

import secrets
import threading
import time
import html


HOST_SECONDS = 180
HELLO_HTML = "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Hello World</title><h1>Hello World</h1><p>Hospedado por 3 minutos no executor local do MVP.</p><p>Servido pelo nó <strong>__NODE__</strong>.</p></html>"


def validate_html(content: str) -> str:
    if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 20_000:
        raise ValueError("HTML vazio ou maior que 20 KB.")
    if "<script" in content.lower():
        raise ValueError("Scripts nao sao permitidos nesta demonstracao local.")
    return content


def html_for_node(node_code: str) -> str:
    return HELLO_HTML.replace("__NODE__", html.escape(node_code))


class SiteRegistry:
    def __init__(self, now=time.monotonic):
        self._now = now
        self._lock = threading.Lock()
        self._sites: dict[str, tuple[float, str]] = {}

    def start(self, seconds: int = HOST_SECONDS, content: str = HELLO_HTML) -> str:
        if not 0 < seconds <= HOST_SECONDS:
            raise ValueError("Duracao de hospedagem invalida.")
        content = validate_html(content)
        token = secrets.token_urlsafe(18)
        with self._lock:
            self._sites[token] = (self._now() + seconds, content)
        return token

    def status(self, token: str) -> str:
        with self._lock:
            item = self._sites.get(token)
            if item is None:
                return "MISSING"
            expires, _content = item
            if self._now() >= expires:
                self._sites[token] = (0.0, "")
                return "EXPIRED"
            return "ACTIVE"

    def content(self, token: str) -> str | None:
        with self._lock:
            item = self._sites.get(token)
            if item is None:
                return None
            return item[1]

    def stop(self, token: str) -> bool:
        with self._lock:
            if token not in self._sites:
                return False
            self._sites[token] = (0.0, "")
            return True
