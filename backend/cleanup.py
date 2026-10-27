"""Deletes files 24 hours after they finish, and sooner when the disk runs low."""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import db
from config import Settings
from events import Broadcaster
from models import ACTIVE, Job, job_dict

log = logging.getLogger("grab.cleanup")


class Cleaner:
    def __init__(self, settings: Settings, engine: Engine, broadcaster: Broadcaster) -> None:
        self.settings = settings
        self.engine = engine
        self.bus = broadcaster
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="grab-cleanup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(5)

    def _loop(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("Cleanup failed")
            if self._stop.wait(self.settings.cleanup_interval_s):
                return

    def run_once(self, now: datetime | None = None) -> int:
        with self._lock:
            removed = self._expire_old(now or datetime.now(UTC))
            removed += self._enforce_floor()
            self._remove_orphans()
            return removed

    def enforce_disk_floor(self) -> int:
        with self._lock:
            return self._enforce_floor()

    def expire(self, job: Job) -> None:
        shutil.rmtree(self.settings.downloads_dir / job.id, ignore_errors=True)
        updated = db.update_job(self.engine, job.id, only_if_status=("done",), status="expired", file_path=None)
        if updated:
            self.bus.publish(job_dict(updated))
            log.info("Expired %s (%s)", job.id, job.title)

    def _done_jobs(self) -> list[Job]:
        with Session(self.engine) as s:
            return list(s.exec(select(Job).where(Job.status == "done").order_by(Job.finished_at, Job.created_at)).all())

    def _expire_old(self, now: datetime) -> int:
        count = 0
        for job in self._done_jobs():
            if job.expires_at and datetime.fromisoformat(job.expires_at) <= now:
                self.expire(job)
                count += 1
        return count

    def _free(self) -> int:
        return shutil.disk_usage(self.settings.downloads_dir).free

    def _enforce_floor(self) -> int:
        count = 0
        if self._free() >= self.settings.disk_floor_bytes:
            return 0
        for job in self._done_jobs():  # oldest first
            self.expire(job)
            count += 1
            if self._free() >= self.settings.disk_floor_bytes:
                break
        return count

    def _remove_orphans(self) -> None:
        """Folders on disk that no done or active job points at (failed runs, deleted rows)."""
        root = self.settings.downloads_dir
        if not root.is_dir():
            return
        with Session(self.engine) as s:
            keep = set(s.exec(select(Job.id).where(Job.status.in_(("done", *ACTIVE)))).all())
        for path in root.iterdir():
            if path.is_dir() and path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)
