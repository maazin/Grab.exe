"""SQLite engine and small query helpers shared by the API, worker, and cleanup."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from models import ACTIVE, Job


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    SQLModel.metadata.create_all(engine)
    return engine


def get_job(engine: Engine, job_id: str) -> Job | None:
    with Session(engine) as s:
        return s.get(Job, job_id)


def add_job(engine: Engine, job: Job) -> Job:
    with Session(engine) as s:
        s.add(job)
        s.commit()
        s.refresh(job)
        return job


def update_job(engine: Engine, job_id: str, only_if_status: tuple[str, ...] | None = None, **fields) -> Job | None:
    """Update a row, optionally only while it is in one of the given statuses.

    Returns the row after the update, or None if nothing matched.
    """
    with Session(engine) as s:
        stmt = update(Job).where(Job.id == job_id).values(**fields)
        if only_if_status:
            stmt = stmt.where(Job.status.in_(only_if_status))
        result = s.exec(stmt)
        s.commit()
        if result.rowcount == 0:
            return None
        return s.get(Job, job_id)


def delete_job(engine: Engine, job_id: str) -> None:
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job:
            s.delete(job)
            s.commit()


def next_queued(engine: Engine) -> Job | None:
    with Session(engine) as s:
        return s.exec(select(Job).where(Job.status == "queued").order_by(Job.created_at, Job.id)).first()


def find_existing(engine: Engine, video_id: str, preset: str) -> Job | None:
    """A job for the same video and preset that is finished with its file on disk, or still in progress."""
    with Session(engine) as s:
        rows = s.exec(
            select(Job)
            .where(Job.video_id == video_id, Job.preset == preset, Job.status.in_(("done", *ACTIVE)))
            .order_by(Job.created_at.desc())
        ).all()
    for job in rows:
        if job.status in ACTIVE:
            return job
        if job.file_path and Path(job.file_path).is_file():
            return job
    return None
