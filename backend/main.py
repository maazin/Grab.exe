"""Grab: the FastAPI app, its routes, and the built frontend."""

from __future__ import annotations

import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import db
import presets
import system
from auth import AccessVerifier, access_middleware
from cleanup import Cleaner
from config import Settings
from errors import GrabError
from events import Broadcaster
from models import ACTIVE, RUNNING, Job, job_dict
from probe import Prober, thumb_for
from worker import Worker

log = logging.getLogger("grab")

HEARTBEAT_S = 15


class ProbeBody(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class JobsBody(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    preset: str
    video_ids: list[str] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)

    engine = db.make_engine(settings.db_path)
    bus = Broadcaster()
    prober = Prober()
    cleaner = Cleaner(settings, engine, bus)
    worker = Worker(settings, engine, bus, cleaner)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bus.bind(asyncio.get_running_loop())
        cleaner.start()
        worker.start()
        log.info("Grab %s started (dev mode: %s)", settings.app_version, settings.dev_mode)
        yield
        worker.stop()
        cleaner.stop()

    app = FastAPI(title="Grab", version=settings.app_version, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.worker = worker
    app.state.cleaner = cleaner
    app.state.prober = prober
    app.state.bus = bus

    app.state.verifier = AccessVerifier(settings)
    app.middleware("http")(access_middleware(settings, app.state.verifier))

    # --- errors ---

    @app.exception_handler(GrabError)
    async def _grab_error(_req: Request, err: GrabError):
        return JSONResponse(err.body(), status_code=err.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_req: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg')}" if where else "The request was not valid."
        return JSONResponse(GrabError("invalid_request", message).body(), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "unknown"
        return JSONResponse(GrabError(code, str(exc.detail) if code == "unknown" else None).body(), status_code=exc.status_code)

    # --- helpers ---

    def with_live(job: Job) -> dict:
        """The row, with the worker's in-memory progress laid over it while it runs."""
        live = worker.live(job.id) if job.status in RUNNING else None
        return live or job_dict(job)

    def require(job_id: str) -> Job:
        job = db.get_job(engine, job_id)
        if job is None:
            raise GrabError("not_found")
        return job

    def queue_copy(source: Job) -> Job:
        existing = db.find_existing(engine, source.video_id, source.preset)
        if existing:
            return existing
        job = db.add_job(
            engine,
            Job(
                url=source.url,
                video_id=source.video_id,
                title=source.title,
                uploader=source.uploader,
                duration_s=source.duration_s,
                thumbnail_url=source.thumbnail_url,
                preset=source.preset,
            ),
        )
        bus.publish(job_dict(job))
        worker.wake()
        return job

    # --- routes ---

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    @app.post("/api/probe")
    async def probe(body: ProbeBody):
        return await run_in_threadpool(prober.probe, body.url)

    @app.post("/api/jobs")
    async def create_jobs(body: JobsBody):
        if not presets.is_preset(body.preset):
            raise GrabError("invalid_request", f"Unknown preset: {body.preset}")
        info = await run_in_threadpool(prober.probe, body.url)

        if info["is_playlist"]:
            entries = info["entries"]
            if body.video_ids is not None:
                wanted = set(body.video_ids)
                entries = [e for e in entries if e["video_id"] in wanted]
            if not entries:
                raise GrabError("invalid_request", "Pick at least one video from the playlist.")
            items = [
                {
                    "video_id": e["video_id"],
                    "title": e["title"],
                    "uploader": info["uploader"],
                    "duration_s": e["duration_s"],
                    "thumbnail_url": thumb_for(e["video_id"]),
                }
                for e in entries
            ]
        else:
            items = [{k: info[k] for k in ("video_id", "title", "uploader", "duration_s", "thumbnail_url")}]

        jobs = []
        for item in items:
            existing = db.find_existing(engine, item["video_id"], body.preset)
            if existing:
                jobs.append(with_live(existing))
                continue
            job = db.add_job(engine, Job(url=body.url.strip(), preset=body.preset, **item))
            bus.publish(job_dict(job))
            jobs.append(job_dict(job))
        worker.wake()
        return {"jobs": jobs}

    @app.get("/api/jobs")
    async def list_jobs(status: str | None = None, limit: int = Query(50, ge=1, le=200)):
        stmt = select(Job).order_by(col(Job.created_at).desc()).limit(limit)
        if status == "active":
            stmt = stmt.where(col(Job.status).in_(ACTIVE))
        elif status:
            stmt = stmt.where(Job.status == status)
        with Session(engine) as s:
            rows = s.exec(stmt).all()
        return {"jobs": [with_live(j) for j in rows]}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        return with_live(require(job_id))

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        job = require(job_id)
        if job.status in ACTIVE:
            updated = db.update_job(engine, job_id, only_if_status=ACTIVE, status="canceled", speed_bps=None, eta_s=None)
            if job.status in RUNNING or worker.is_running(job_id):
                worker.cancel(job_id)
            if updated:
                job = updated
                bus.publish(job_dict(job), force=True)
        return job_dict(job)

    @app.post("/api/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        job = require(job_id)
        if job.status in ACTIVE:
            return with_live(job)
        return job_dict(queue_copy(job))

    @app.delete("/api/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str):
        job = require(job_id)
        if job.status in ACTIVE:
            worker.cancel(job_id)
        db.delete_job(engine, job_id)
        await run_in_threadpool(shutil.rmtree, settings.downloads_dir / job_id, True)
        return Response(status_code=204)

    @app.get("/api/events")
    async def events():
        queue = bus.subscribe()

        async def stream():
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        yield await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                    except TimeoutError:
                        yield ": ping\n\n"
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/files/{job_id}")
    async def get_file(job_id: str):
        job = require(job_id)
        if job.status == "expired":
            raise GrabError("expired")
        if job.status != "done" or not job.file_path:
            raise GrabError("not_found", "This file isn't ready yet.")
        path = Path(job.file_path)
        if not path.is_file():
            raise GrabError("expired")
        return FileResponse(path, filename=path.name, content_disposition_type="attachment")

    @app.get("/api/history")
    async def history(q: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        where = []
        if q.strip():
            escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append(col(Job.title).ilike(f"%{escaped}%", escape="\\"))
        with Session(engine) as s:
            total = s.exec(select(func.count()).select_from(Job).where(*where)).one()
            rows = s.exec(select(Job).where(*where).order_by(col(Job.created_at).desc()).offset(offset).limit(limit)).all()
        return {"jobs": [with_live(j) for j in rows], "total": total}

    @app.get("/api/system")
    async def system_info():
        return await run_in_threadpool(system.info, settings)

    @app.post("/api/system/update-ytdlp")
    async def update_ytdlp():
        try:
            result = await run_in_threadpool(system.update_ytdlp)
        except Exception as exc:  # noqa: BLE001
            raise GrabError("unknown", f"Updating yt-dlp failed: {exc}") from exc
        result["restarting"] = settings.restart_on_update and result["old_version"] != result["new_version"]
        if result["restarting"]:
            system.restart_soon(1.0)
        return result

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(rest: str):
        raise GrabError("not_found", "No such API endpoint.")

    # --- the built frontend ---

    static = settings.static_dir
    if static and (static / "index.html").is_file():
        root = static.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            target = (root / path).resolve()
            if path and target.is_file() and target.is_relative_to(root):
                cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
                return FileResponse(target, headers={"Cache-Control": cache})
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
    else:

        @app.get("/", include_in_schema=False)
        async def hello():
            return Response(
                "<!doctype html><title>Grab</title><p>Grab API is running. Build the frontend or use the Vite dev server.</p>",
                media_type="text/html",
            )

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Run with: uvicorn main:create_app --factory
