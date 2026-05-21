from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class Job:
    id: int
    description: str
    scheduled_at: datetime
    bucket: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.id,
            "description": self.description,
            "scheduled_at": self.scheduled_at.isoformat(),
            "bucket": self.bucket,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
