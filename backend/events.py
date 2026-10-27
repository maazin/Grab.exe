"""Fan job updates out to every open server-sent events stream."""

from __future__ import annotations

import asyncio
import json
import threading
import time

THROTTLE_S = 0.5  # at most 2 progress events per second per job


class Broadcaster:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue[str]] = set()
        self._lock = threading.Lock()
        # job id -> (time sent, status sent)
        self._last: dict[str, tuple[float, str]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._queues.discard(q)

    def publish(self, job: dict, force: bool = False) -> None:
        """Send a job to all streams. Safe to call from any thread.

        Progress-only updates are throttled per job; a status change always goes out.
        """
        job_id, status = job["id"], job["status"]
        now = time.monotonic()
        with self._lock:
            last = self._last.get(job_id)
            if not force and last and last[1] == status and now - last[0] < THROTTLE_S:
                return
            self._last[job_id] = (now, status)
            if len(self._last) > 500:
                self._last = dict(list(self._last.items())[-200:])

        if self._loop is None or self._loop.is_closed():
            return
        message = f"event: job\ndata: {json.dumps(job, separators=(',', ':'))}\n\n"
        try:
            self._loop.call_soon_threadsafe(self._fanout, message)
        except RuntimeError:
            pass  # loop shutting down

    def _fanout(self, message: str) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass  # a stuck client misses updates; it resyncs on reconnect
