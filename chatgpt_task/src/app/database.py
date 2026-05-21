from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import Job, JobStatus


DB_PATH = Path(__file__).resolve().parent.parent / "tasks.db"


class JobNotFoundError(ValueError):
    pass


class JobStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    bucket TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_bucket_status_scheduled
                ON jobs(bucket, status, scheduled_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status
                ON jobs(status)
                """
            )

    def create_job(self, description: str, scheduled_at: datetime, bucket: str) -> Job:
        now = _utc_naive_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    description, scheduled_at, bucket, status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    description,
                    scheduled_at.isoformat(),
                    bucket,
                    JobStatus.PENDING.value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            job_id = cursor.lastrowid
            if job_id is None:
                raise RuntimeError("failed to create job")
        return self.get_job(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        return [_row_to_job(row) for row in rows]

    def get_job(self, job_id: int) -> Job:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        return _row_to_job(row)

    def cancel_job(self, job_id: int) -> Job:
        now = _utc_naive_now().isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFoundError(f"job {job_id} was not found")

            status = JobStatus(row["status"])
            if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                return self.get_job(job_id)

            conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (JobStatus.CANCELLED.value, now, job_id),
            )
        return self.get_job(job_id)

    def claim_due_jobs(
        self,
        current_bucket: str,
        now: datetime,
        limit: int = 100,
    ) -> list[Job]:
        timestamp = now.isoformat()
        updated_at = _utc_naive_now().isoformat()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE bucket <= ?
                  AND scheduled_at <= ?
                  AND status = ?
                ORDER BY scheduled_at, id
                LIMIT ?
                """,
                (current_bucket, timestamp, JobStatus.PENDING.value, limit),
            ).fetchall()
            job_ids = [int(row["id"]) for row in rows]
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                conn.execute(
                    f"""
                    UPDATE jobs
                    SET status = ?, updated_at = ?
                    WHERE id IN ({placeholders})
                      AND status = ?
                    """,
                    (
                        JobStatus.QUEUED.value,
                        updated_at,
                        *job_ids,
                        JobStatus.PENDING.value,
                    ),
                )
        return [self.get_job(job_id) for job_id in job_ids]

    def mark_running(self, job_id: int) -> bool:
        return self._transition(job_id, JobStatus.QUEUED, JobStatus.RUNNING)

    def mark_completed(self, job_id: int) -> Job:
        now = _utc_naive_now().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, completed_at = ?, error = NULL
                WHERE id = ?
                """,
                (JobStatus.COMPLETED.value, now, now, job_id),
            )
        return self.get_job(job_id)

    def mark_failed(self, job_id: int, error: str) -> Job:
        now = _utc_naive_now().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, error = ?
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, now, error, job_id),
            )
        return self.get_job(job_id)

    def _transition(self, job_id: int, from_status: JobStatus, to_status: JobStatus) -> bool:
        now = _utc_naive_now().isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (to_status.value, now, job_id, from_status.value),
            )
            return cursor.rowcount == 1


def jobs_to_response(jobs: Iterable[Job]) -> list[dict[str, object]]:
    return [job.to_dict() for job in jobs]


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=int(row["id"]),
        description=str(row["description"]),
        scheduled_at=datetime.fromisoformat(row["scheduled_at"]),
        bucket=str(row["bucket"]),
        status=JobStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        ),
        error=str(row["error"]) if row["error"] else None,
    )


def _utc_naive_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)
