"""Заявки магазинов с публичной страницы."""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.store import iso, utcnow


@dataclass
class Lead:
    id: int
    shop: str
    contact: str
    plan: str
    note: str
    created_at: str


class LeadStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def add(self, shop: str, contact: str, plan: str, note: str) -> Lead:
        created_at = iso(utcnow())
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO leads (shop, contact, plan, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (shop, contact, plan, note, created_at),
            )
            self._conn.commit()
            lead_id = int(cursor.lastrowid)
        return Lead(lead_id, shop, contact, plan, note, created_at)
