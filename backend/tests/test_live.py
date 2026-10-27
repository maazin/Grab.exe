"""One real download against YouTube. Skipped by default; run with: pytest -m live"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import create_app
from tests.conftest import wait_for

SHORT_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19 seconds


@pytest.mark.live
def test_real_mp3_download(settings, monkeypatch):
    from yt_dlp import YoutubeDL

    import probe
    import worker

    monkeypatch.setattr(probe, "YoutubeDL", YoutubeDL)
    monkeypatch.setattr(worker, "YoutubeDL", YoutubeDL)

    with TestClient(create_app(settings)) as client:
        info = client.post("/api/probe", json={"url": SHORT_VIDEO}).json()
        assert info["video_id"] == "jNQXAC9IVRw"
        assert info["duration_s"] == 19

        job = client.post("/api/jobs", json={"url": SHORT_VIDEO, "preset": "audio_mp3"}).json()["jobs"][0]
        done = wait_for(client, job["id"], ("done", "failed"), timeout=120)
        assert done["status"] == "done", done["error_message"]
        assert done["file_name"].endswith(".mp3")
        assert client.get(f"/api/files/{job['id']}").content[:3] in (b"ID3", b"\xff\xfb")
