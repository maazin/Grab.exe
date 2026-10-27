"""The jobs table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Field, SQLModel

ACTIVE = ("queued", "downloading", "converting")
RUNNING = ("downloading", "converting")
STATUSES = (*ACTIVE, "done", "failed", "canceled", "expired")


def now_iso() -> str:
    # Microseconds keep jobs created in one request in order, since the queue sorts by created_at.
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid.uuid4())


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=new_id, primary_key=True)
    url: str
    video_id: str = Field(index=True)
    title: str = ""
    uploader: str | None = None
    duration_s: int | None = None
    thumbnail_url: str | None = None
    preset: str
    status: str = "queued"
    progress_pct: float = 0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_s: int | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = Field(default_factory=now_iso, index=True)
    finished_at: str | None = None
    expires_at: str | None = None


def job_dict(job: Job) -> dict:
    data = job.model_dump()
    data["file_name"] = Path(job.file_path).name if job.file_path else None
    return data
