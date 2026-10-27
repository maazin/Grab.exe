"""Shared fixtures. yt-dlp is replaced with fakes so tests never touch the network."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from yt_dlp.utils import DownloadError

import probe
import worker
from config import Settings
from main import create_app


@dataclass
class FakeBehavior:
    fail_with: str | None = None  # message for a DownloadError
    step_delay: float = 0.0  # seconds between progress hooks, so tests can cancel mid-download
    steps: int = 4
    downloads: list[str] = field(default_factory=list)


FAKE = FakeBehavior()

PLAYLIST_IDS = [f"vid{i:08d}" for i in range(10)]  # 11 characters, like real IDs


def _video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[1][:11]
    return url.rstrip("/").rsplit("/", 1)[-1][:11]


class FakeProbeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        assert download is False
        if "playlist" in url:
            assert self.opts.get("extract_flat") == "in_playlist"
            return {
                "_type": "playlist",
                "id": "PLtest",
                "title": "Test playlist",
                "uploader": "Test channel",
                "entries": [{"id": vid, "title": f"Song {i}", "duration": 60 + i} for i, vid in enumerate(PLAYLIST_IDS)],
            }
        vid = _video_id(url)
        if vid.startswith("private"):
            raise DownloadError(f"ERROR: [youtube] {vid}: Private video. Sign in if you've been granted access")
        if vid.startswith("botcheck"):
            raise DownloadError(f"ERROR: [youtube] {vid}: Sign in to confirm you're not a bot.")
        return {
            "id": vid,
            "title": f"Video {vid}",
            "uploader": "Uploader",
            "duration": 212,
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hq.jpg",
        }


class FakeDownloadYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        (url,) = urls
        vid = _video_id(url)
        FAKE.downloads.append(vid)
        home = Path(self.opts["paths"]["home"])
        part = home / f"Video {vid} [{vid}].f1.mp4.part"
        total = 1_000_000
        for i in range(1, FAKE.steps + 1):
            part.write_bytes(b"x" * (total // FAKE.steps * i))
            for hook in self.opts["progress_hooks"]:
                hook(
                    {
                        "status": "downloading",
                        "filename": str(part),
                        "downloaded_bytes": total // FAKE.steps * i,
                        "total_bytes": total,
                        "speed": 250_000.0,
                        "eta": FAKE.steps - i,
                        "info_dict": {"id": vid},
                    }
                )
            if FAKE.step_delay:
                time.sleep(FAKE.step_delay)
        if FAKE.fail_with:
            raise DownloadError(FAKE.fail_with)
        for hook in self.opts["progress_hooks"]:
            hook({"status": "finished", "filename": str(part), "total_bytes": total, "info_dict": {"id": vid}})
        for hook in self.opts["postprocessor_hooks"]:
            hook({"status": "started", "postprocessor": "Merger", "info_dict": {}})
        ext = "mp3" if "mp3" in str(self.opts.get("postprocessors")) else "mp4"
        out = home / f"Video {vid} [{vid}].{ext}"
        out.write_bytes(b"0123456789" * 1000)
        part.unlink()
        (home / f"Video {vid} [{vid}].webp").write_bytes(b"thumb")
        for hook in self.opts["postprocessor_hooks"]:
            hook({"status": "finished", "postprocessor": "Merger", "info_dict": {}})
        return 0


@pytest.fixture(autouse=True)
def fake_ytdlp(monkeypatch):
    global FAKE
    FAKE.__init__()
    monkeypatch.setattr(probe, "YoutubeDL", FakeProbeYDL)
    monkeypatch.setattr(worker, "YoutubeDL", FakeDownloadYDL)
    return FAKE


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        downloads_dir=tmp_path / "downloads",
        dev_mode=True,
        job_gap_s=0,
        disk_floor_bytes=0,
        min_free_to_start_bytes=0,
        cleanup_interval_s=3600,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def wait_for(client: TestClient, job_id: str, statuses: tuple[str, ...], timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stuck in {job and job['status']}, wanted {statuses}")
