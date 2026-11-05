"""SQLite-журнал примерок. Файлы лежат рядом, в каталоге задания."""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


@dataclass
class Job:
    id: str
    owner_id: str
    status: str
    model: str
    category: str
    garment_photo_type: str
    seed: int
    num_timesteps: int | None
    guidance_scale: float | None
    segmentation_free: bool
    webhook_url: str | None
    error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model TEXT NOT NULL,
                    category TEXT NOT NULL,
                    garment_photo_type TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    num_timesteps INTEGER,
                    guidance_scale REAL,
                    segmentation_free INTEGER NOT NULL,
                    webhook_url TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create(self, job: Job) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    id, owner_id, status, model, category, garment_photo_type,
                    seed, num_timesteps, guidance_scale, segmentation_free,
                    webhook_url, error, created_at, updated_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.owner_id,
                    job.status,
                    job.model,
                    job.category,
                    job.garment_photo_type,
                    job.seed,
                    job.num_timesteps,
                    job.guidance_scale,
                    int(job.segmentation_free),
                    job.webhook_url,
                    job.error,
                    job.created_at,
                    job.updated_at,
                    job.started_at,
                    job.finished_at,
                ),
            )
            self._conn.commit()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def queued_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at"
            ).fetchall()
        return [row["id"] for row in rows]

    def mark_running(self, job_id: str) -> None:
        now = iso(utcnow())
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'running', started_at = ?, updated_at = ?, error = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, job_id),
            )
            self._conn.commit()

    def mark_succeeded(self, job_id: str) -> None:
        now = iso(utcnow())
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'succeeded', finished_at = ?, updated_at = ?, error = NULL
                WHERE id = ?
                """,
                (now, now, job_id),
            )
            self._conn.commit()

    def mark_failed(self, job_id: str, error: str) -> None:
        now = iso(utcnow())
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', finished_at = ?, updated_at = ?, error = ?
                WHERE id = ?
                """,
                (now, now, error[:2000], job_id),
            )
            self._conn.commit()

    def fail_interrupted(self, error: str) -> None:
        now = iso(utcnow())
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', finished_at = ?, updated_at = ?, error = ?
                WHERE status = 'running'
                """,
                (now, now, error),
            )
            self._conn.commit()

    def expired_ids(self, older_than_hours: int) -> list[str]:
        if older_than_hours <= 0:
            return []
        cutoff = iso(utcnow() - timedelta(hours=older_than_hours))
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM jobs WHERE created_at < ?",
                (cutoff,),
            ).fetchall()
        return [row["id"] for row in rows]

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._conn.commit()


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        owner_id=row["owner_id"],
        status=row["status"],
        model=row["model"],
        category=row["category"],
        garment_photo_type=row["garment_photo_type"],
        seed=row["seed"],
        num_timesteps=row["num_timesteps"],
        guidance_scale=row["guidance_scale"],
        segmentation_free=bool(row["segmentation_free"]),
        webhook_url=row["webhook_url"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )
