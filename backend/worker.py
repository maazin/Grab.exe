"""The single background thread that runs queued jobs one at a time."""

from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.engine import Engine
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled

import db
import presets
from config import Settings
from errors import GrabError, classify
from events import Broadcaster
from models import RUNNING, Job, job_dict

log = logging.getLogger("grab.worker")

DB_WRITE_INTERVAL_S = 1.0
SKIP_SUFFIXES = {".part", ".ytdl", ".temp", ".jpg", ".jpeg", ".png", ".webp", ".json"}


class Canceled(DownloadCancelled):
    msg = "Canceled by user"


class _YtLogger:
    def debug(self, msg: str) -> None:
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.info(msg)

    def error(self, msg: str) -> None:
        log.warning(msg)


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def find_output(job_dir: Path, preset: str) -> Path | None:
    """The finished media file in a job folder."""
    want = "." + presets.OUTPUT_EXT[preset]
    files = [p for p in job_dir.iterdir() if p.is_file() and p.suffix.lower() not in SKIP_SUFFIXES]
    if not files:
        return None
    exact = [p for p in files if p.suffix.lower() == want]
    return max(exact or files, key=lambda p: p.stat().st_size)


class _Progress:
    """Combines the separate video and audio downloads of one job into one overall percentage."""

    def __init__(self) -> None:
        self.files: dict[str, list[int]] = {}
        self.expected: int | None = None
        self.best_pct = 0.0

    @staticmethod
    def _estimate(fmt: dict, duration) -> float | None:
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if not size and fmt.get("tbr") and duration:
            size = fmt["tbr"] * 1000 / 8 * duration
        return size

    def update(self, d: dict) -> dict:
        info = d.get("info_dict") or {}
        if self.expected is None:
            formats = info.get("requested_formats") or []
            sizes = [self._estimate(f, info.get("duration")) for f in formats]
            if sizes and all(sizes):
                self.expected = int(sum(sizes))

        name = d.get("filename") or d.get("tmpfilename") or "file"
        done = int(d.get("downloaded_bytes") or 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if d.get("status") == "finished":
            done = int(total or done or (Path(name).stat().st_size if Path(name).exists() else 0))
            total = done
        self.files[name] = [done, int(total or 0)]

        downloaded = sum(v[0] for v in self.files.values())
        known = sum(v[1] for v in self.files.values())
        grand = max(self.expected or 0, known) or None
        speed = d.get("speed")
        # Estimates can be off, so the bar never moves backwards.
        pct = min(99.9, downloaded / grand * 100) if grand else 0.0
        self.best_pct = pct = max(self.best_pct, pct)
        eta = int((grand - downloaded) / speed) if grand and speed and grand > downloaded else d.get("eta")
        return {
            "progress_pct": round(pct, 1),
            "downloaded_bytes": downloaded,
            "total_bytes": grand,
            "speed_bps": float(speed) if speed else None,
            "eta_s": int(eta) if eta is not None else None,
        }


class Worker:
    def __init__(self, settings: Settings, engine: Engine, broadcaster: Broadcaster, cleaner=None) -> None:
        self.settings = settings
        self.engine = engine
        self.bus = broadcaster
        self.cleaner = cleaner
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current_id: str | None = None
        self._cancel_id: str | None = None
        self._live: dict | None = None
        self._last_end = 0.0

    # --- control, called from API threads ---

    def start(self) -> None:
        self._recover()
        self._thread = threading.Thread(target=self._run_forever, name="grab-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def wake(self) -> None:
        self._wake.set()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            if self._current_id == job_id:
                self._cancel_id = job_id

    def live(self, job_id: str) -> dict | None:
        with self._lock:
            if self._live and self._live["id"] == job_id:
                return dict(self._live)
        return None

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return self._current_id == job_id

    # --- the loop ---

    def _recover(self) -> None:
        """Jobs that were mid-download when the process stopped go back to the queue."""
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            stuck = s.exec(select(Job).where(Job.status.in_(RUNNING))).all()
        for job in stuck:
            shutil.rmtree(self.settings.downloads_dir / job.id, ignore_errors=True)
            db.update_job(
                self.engine,
                job.id,
                status="queued",
                progress_pct=0,
                downloaded_bytes=None,
                total_bytes=None,
                speed_bps=None,
                eta_s=None,
            )
            log.info("Requeued interrupted job %s", job.id)

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                job = db.next_queued(self.engine)
            except Exception:  # noqa: BLE001
                log.exception("Could not read the queue")
                job = None
            if job is None:
                self._wake.wait(2)
                self._wake.clear()
                continue

            gap = self.settings.job_gap_s - (time.monotonic() - self._last_end)
            if self._last_end and gap > 0:
                if self._stop.wait(gap):
                    break
                continue  # re-read the queue; the job may have been canceled meanwhile

            try:
                self._run(job)
            except Exception:  # noqa: BLE001 - the worker must never die
                log.exception("Job %s crashed the worker loop", job.id)
                self._finish(job.id, status="failed", error_code="unknown", error_message="Something went wrong.")
            finally:
                with self._lock:
                    self._current_id = self._cancel_id = None
                    self._live = None
                self._last_end = time.monotonic()

    def _emit(self, job: Job | None) -> None:
        if job is not None:
            self.bus.publish(job_dict(job))

    def _finish(self, job_id: str, **fields) -> Job | None:
        job = db.update_job(self.engine, job_id, **fields)
        self._emit(job)
        return job

    def _run(self, queued: Job) -> None:
        job = db.update_job(self.engine, queued.id, only_if_status=("queued",), status="downloading", progress_pct=0)
        if job is None:
            return  # canceled or deleted while waiting
        with self._lock:
            self._current_id = job.id
            self._cancel_id = None
            self._live = job_dict(job)
        self._emit(job)

        if self.cleaner is not None:
            self.cleaner.enforce_disk_floor()
        if shutil.disk_usage(self.settings.downloads_dir).free < self.settings.min_free_to_start_bytes:
            err = GrabError("disk_full")
            self._finish(job.id, status="failed", error_code=err.code, error_message=err.message)
            return

        job_dir = self.settings.downloads_dir / job.id
        shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        tracker = _Progress()
        last_write = [0.0]

        def check_cancel() -> None:
            if self._cancel_id == job.id or self._stop.is_set():
                raise Canceled()

        def set_live(**fields) -> None:
            with self._lock:
                if self._live is None:
                    return
                self._live.update(fields)
                snapshot = dict(self._live)
            self.bus.publish(snapshot)

        def on_progress(d: dict) -> None:
            check_cancel()
            if d.get("status") not in ("downloading", "finished"):
                return
            fields = tracker.update(d)
            set_live(**fields)
            now = time.monotonic()
            if now - last_write[0] >= DB_WRITE_INTERVAL_S:
                last_write[0] = now
                db.update_job(self.engine, job.id, only_if_status=RUNNING, **fields)

        def on_postprocess(d: dict) -> None:
            check_cancel()
            starting = d.get("status") == "started" and d.get("postprocessor") != "MoveFiles"
            if starting and self._live and self._live["status"] != "converting":
                updated = db.update_job(
                    self.engine, job.id, only_if_status=RUNNING, status="converting", speed_bps=None, eta_s=None
                )
                if updated:
                    set_live(status="converting", speed_bps=None, eta_s=None)

        opts = presets.options_for(job.preset)
        opts.update(
            {
                "paths": {"home": str(job_dir), "temp": str(job_dir)},
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "logger": _YtLogger(),
                "progress_hooks": [on_progress],
                "postprocessor_hooks": [on_postprocess],
                "retries": 5,
                "fragment_retries": 5,
            }
        )

        try:
            with YoutubeDL(opts) as ydl:
                retcode = ydl.download([video_url(job.video_id)])
            if retcode:  # yt-dlp reports some failures through the return code instead of raising
                raise GrabError("unknown", "The download failed. Check the link and try again.")
            check_cancel()
        except DownloadCancelled:
            shutil.rmtree(job_dir, ignore_errors=True)
            if db.get_job(self.engine, job.id):
                self._finish(job.id, status="canceled", speed_bps=None, eta_s=None)
            return
        except Exception as exc:  # noqa: BLE001
            err = classify(exc)
            log.warning("Job %s failed: %s (%s)", job.id, err.code, exc)
            shutil.rmtree(job_dir, ignore_errors=True)
            self._finish(
                job.id,
                status="failed",
                error_code=err.code,
                error_message=err.message,
                speed_bps=None,
                eta_s=None,
            )
            return

        out = find_output(job_dir, job.preset)
        if out is None:
            shutil.rmtree(job_dir, ignore_errors=True)
            self._finish(
                job.id, status="failed", error_code="unknown", error_message="The download finished but no file was found."
            )
            return
        for leftover in job_dir.iterdir():
            if leftover != out:
                if leftover.is_dir():
                    shutil.rmtree(leftover, ignore_errors=True)
                else:
                    leftover.unlink(missing_ok=True)

        finished = datetime.now(UTC)
        size = out.stat().st_size
        self._finish(
            job.id,
            status="done",
            progress_pct=100,
            downloaded_bytes=size,
            total_bytes=size,
            speed_bps=None,
            eta_s=None,
            file_path=str(out),
            file_size_bytes=size,
            error_code=None,
            error_message=None,
            finished_at=finished.isoformat(timespec="seconds"),
            expires_at=(finished + timedelta(hours=self.settings.expiry_hours)).isoformat(timespec="seconds"),
        )
