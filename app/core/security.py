"""Ключи магазинов, лимит запросов и проверка webhook."""

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse


class AuthError(Exception):
    pass


class RateLimitError(Exception):
    pass


def owner_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def key_is_valid(api_key: str, allowed: set[str]) -> bool:
    if not api_key or not allowed:
        return False
    return any(hmac.compare_digest(api_key, candidate) for candidate in allowed)


def read_presented_key(x_api_key: str | None, authorization: str | None) -> str:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def check_webhook(url: str | None) -> str | None:
    if url is None or not url.strip():
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("webhook_url должен быть адресом http или https.")
    if host in {"169.254.169.254", "metadata.google.internal"}:
        raise ValueError("Этот webhook_url запрещён.")
    return url.strip()


class RateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[bucket]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.limit:
                raise RateLimitError("Слишком много запросов. Подождите минуту.")
            hits.append(now)
