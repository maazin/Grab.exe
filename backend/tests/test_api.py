"""Every API route, with yt-dlp faked."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import db
from models import Job
from tests.conftest import PLAYLIST_IDS, wait_for

VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
PLAYLIST = "https://www.youtube.com/playlist?list=PLtest"


def make_job(client, url=VIDEO, preset="video_1080", **extra) -> dict:
    res = client.post("/api/jobs", json={"url": url, "preset": preset, **extra})
    assert res.status_code == 200, res.text
    return res.json()["jobs"][0]


# --- probe ---


def test_probe_video(client):
    res = client.post("/api/probe", json={"url": VIDEO})
    assert res.status_code == 200
    assert res.json() == {
        "video_id": "dQw4w9WgXcQ",
        "title": "Video dQw4w9WgXcQ",
        "uploader": "Uploader",
        "duration_s": 212,
        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hq.jpg",
        "is_playlist": False,
        "entries": [],
    }


def test_probe_playlist(client):
    body = client.post("/api/probe", json={"url": PLAYLIST}).json()
    assert body["is_playlist"] is True
    assert body["title"] == "Test playlist"
    assert [e["video_id"] for e in body["entries"]] == PLAYLIST_IDS
    assert body["entries"][0] == {"video_id": PLAYLIST_IDS[0], "title": "Song 0", "duration_s": 60}


def test_probe_errors(client):
    bad = client.post("/api/probe", json={"url": "https://vimeo.com/1"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_url"

    private = client.post("/api/probe", json={"url": "https://youtu.be/private0001"})
    assert private.status_code == 422
    assert private.json()["error"] == {
        "code": "unavailable",
        "message": "This video is private, removed, or not available in this region.",
    }

    bot = client.post("/api/probe", json={"url": "https://youtu.be/botcheck001"})
    assert bot.json()["error"]["code"] == "bot_check"

    empty = client.post("/api/probe", json={})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "invalid_request"


# --- jobs and worker ---


def test_job_runs_to_done_and_file_downloads(client, settings):
    job = make_job(client)
    assert job["status"] == "queued"
    assert job["title"] == "Video dQw4w9WgXcQ"

    done = wait_for(client, job["id"], ("done",))
    assert done["progress_pct"] == 100
    assert done["file_name"] == "Video dQw4w9WgXcQ [dQw4w9WgXcQ].mp4"
    assert done["file_size_bytes"] == 10_000
    assert done["expires_at"] > done["finished_at"]
    path = Path(done["file_path"])
    assert path.is_file()
    # The thumbnail and temp files are cleaned out of the job folder.
    assert [p.name for p in path.parent.iterdir()] == [path.name]

    res = client.get(f"/api/files/{job['id']}")
    assert res.status_code == 200
    assert res.content == b"0123456789" * 1000
    assert res.headers["content-disposition"].startswith("attachment;")
    assert "dQw4w9WgXcQ" in res.headers["content-disposition"]

    ranged = client.get(f"/api/files/{job['id']}", headers={"Range": "bytes=0-9"})
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"


def test_audio_preset_produces_mp3(client):
    job = make_job(client, preset="audio_mp3")
    done = wait_for(client, job["id"], ("done",))
    assert done["file_name"].endswith(".mp3")


def test_jobs_run_one_at_a_time_in_order(client, fake_ytdlp):
    fake_ytdlp.step_delay = 0.05
    a = make_job(client, url="https://youtu.be/aaaaaaaaaaa")
    b = make_job(client, url="https://youtu.be/bbbbbbbbbbb")
    wait_for(client, a["id"], ("downloading", "converting", "done"))
    assert client.get(f"/api/jobs/{b['id']}").json()["status"] == "queued"
    wait_for(client, b["id"], ("done",))
    assert fake_ytdlp.downloads == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    active = client.get("/api/jobs", params={"status": "active"}).json()["jobs"]
    assert active == []
    assert [j["id"] for j in client.get("/api/jobs").json()["jobs"]] == [b["id"], a["id"]]


def test_live_progress_is_visible_while_downloading(client, fake_ytdlp):
    fake_ytdlp.step_delay = 0.2
    job = make_job(client)
    running = wait_for(client, job["id"], ("downloading",))
    deadline = datetime.now() + timedelta(seconds=3)
    while running["progress_pct"] == 0 and datetime.now() < deadline:
        running = client.get(f"/api/jobs/{job['id']}").json()
    assert 0 < running["progress_pct"] < 100
    assert running["speed_bps"] == 250_000.0
    assert running["total_bytes"] == 1_000_000


def test_duplicate_returns_existing_job(client, fake_ytdlp):
    first = make_job(client)
    wait_for(client, first["id"], ("done",))
    again = make_job(client)
    assert again["id"] == first["id"]
    assert fake_ytdlp.downloads == ["dQw4w9WgXcQ"]
    # A different preset is a different file.
    other = make_job(client, preset="audio_mp3")
    assert other["id"] != first["id"]


def test_duplicate_ignored_once_file_is_gone(client):
    first = make_job(client)
    done = wait_for(client, first["id"], ("done",))
    Path(done["file_path"]).unlink()
    assert make_job(client)["id"] != first["id"]


def test_playlist_creates_one_job_per_checked_video(client):
    picked = [PLAYLIST_IDS[1], PLAYLIST_IDS[4], PLAYLIST_IDS[7]]
    res = client.post("/api/jobs", json={"url": PLAYLIST, "preset": "audio_mp3", "video_ids": picked})
    jobs = res.json()["jobs"]
    assert [j["video_id"] for j in jobs] == picked
    assert [j["title"] for j in jobs] == ["Song 1", "Song 4", "Song 7"]
    assert all(j["preset"] == "audio_mp3" and j["url"] == PLAYLIST for j in jobs)
    for j in jobs:
        wait_for(client, j["id"], ("done",))


def test_playlist_with_nothing_picked_is_rejected(client):
    res = client.post("/api/jobs", json={"url": PLAYLIST, "preset": "audio_mp3", "video_ids": []})
    assert res.status_code == 400


def test_unknown_preset_is_rejected(client):
    res = client.post("/api/jobs", json={"url": VIDEO, "preset": "video_8k"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_request"


def test_cancel_running_job_stops_and_removes_files(client, settings, fake_ytdlp):
    fake_ytdlp.step_delay = 0.2
    fake_ytdlp.steps = 20
    job = make_job(client)
    wait_for(client, job["id"], ("downloading",))
    job_dir = settings.downloads_dir / job["id"]
    assert job_dir.is_dir()

    res = client.post(f"/api/jobs/{job['id']}/cancel")
    assert res.json()["status"] == "canceled"

    # Wait for the worker to notice and clean up.
    for _ in range(200):
        if not job_dir.exists():
            break
        time.sleep(0.02)
    assert not job_dir.exists()
    assert fake_ytdlp.downloads == ["dQw4w9WgXcQ"]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "canceled"


def test_cancel_queued_job_never_runs(client, fake_ytdlp):
    fake_ytdlp.step_delay = 0.1
    first = make_job(client, url="https://youtu.be/aaaaaaaaaaa")
    second = make_job(client, url="https://youtu.be/bbbbbbbbbbb")
    assert client.post(f"/api/jobs/{second['id']}/cancel").json()["status"] == "canceled"
    wait_for(client, first["id"], ("done",))
    assert "bbbbbbbbbbb" not in fake_ytdlp.downloads


def test_failed_job_reports_code_and_retry_requeues(client, fake_ytdlp):
    fake_ytdlp.fail_with = "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot"
    job = make_job(client)
    failed = wait_for(client, job["id"], ("failed",))
    assert failed["error_code"] == "bot_check"
    assert "bot" in failed["error_message"]

    fake_ytdlp.fail_with = None
    retry = client.post(f"/api/jobs/{job['id']}/retry").json()
    assert retry["id"] != job["id"]
    assert retry["status"] == "queued"
    assert wait_for(client, retry["id"], ("done",))["video_id"] == "dQw4w9WgXcQ"


def test_delete_removes_row_and_file(client):
    job = make_job(client)
    done = wait_for(client, job["id"], ("done",))
    res = client.delete(f"/api/jobs/{job['id']}")
    assert res.status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert not Path(done["file_path"]).exists()


def test_missing_job_is_404(client):
    res = client.get("/api/jobs/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"
    assert client.get("/api/files/nope").status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404


# --- files, expiry, cleanup ---


def test_expired_job_returns_410_and_folder_is_gone(client, settings):
    job = make_job(client)
    done = wait_for(client, job["id"], ("done",))
    folder = Path(done["file_path"]).parent

    cleaner = client.app.state.cleaner
    assert cleaner.run_once(now=datetime.now(UTC) + timedelta(hours=23)) == 0
    assert folder.exists()
    assert cleaner.run_once(now=datetime.now(UTC) + timedelta(hours=25)) == 1

    assert not folder.exists()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "expired"
    res = client.get(f"/api/files/{job['id']}")
    assert res.status_code == 410
    assert res.json()["error"]["code"] == "expired"

    # Get again re-queues it.
    again = client.post(f"/api/jobs/{job['id']}/retry").json()
    assert wait_for(client, again["id"], ("done",))["file_path"]


def test_disk_floor_removes_oldest_first(client, monkeypatch):
    a = make_job(client, url="https://youtu.be/aaaaaaaaaaa")
    wait_for(client, a["id"], ("done",))
    b = make_job(client, url="https://youtu.be/bbbbbbbbbbb")
    wait_for(client, b["id"], ("done",))

    cleaner = client.app.state.cleaner
    cleaner.settings.disk_floor_bytes = 100
    frees = iter([0, 1000])  # low, then fine after one file goes
    monkeypatch.setattr(cleaner, "_free", lambda: next(frees))
    cleaner.enforce_disk_floor()

    assert client.get(f"/api/jobs/{a['id']}").json()["status"] == "expired"
    assert client.get(f"/api/jobs/{b['id']}").json()["status"] == "done"


def test_cleanup_removes_orphan_folders(client, settings):
    orphan = settings.downloads_dir / "not-a-job"
    orphan.mkdir()
    (orphan / "junk.part").write_bytes(b"x")
    client.app.state.cleaner.run_once()
    assert not orphan.exists()


# --- history and system ---


def test_history_search_and_pagination(client):
    engine = client.app.state.engine
    for i, title in enumerate(["Lofi beats", "Cat video", "More lofi", "100% real"]):
        db.add_job(
            engine,
            Job(
                url=VIDEO,
                video_id=f"h{i:010d}",
                title=title,
                preset="audio_mp3",
                status="failed",
                created_at=f"2026-01-0{i + 1}T00:00:00",
            ),
        )
    body = client.get("/api/history").json()
    assert body["total"] == 4
    assert [j["title"] for j in body["jobs"]] == ["100% real", "More lofi", "Cat video", "Lofi beats"]

    lofi = client.get("/api/history", params={"q": "LOFI"}).json()
    assert lofi["total"] == 2
    assert {j["title"] for j in lofi["jobs"]} == {"Lofi beats", "More lofi"}

    assert client.get("/api/history", params={"q": "%"}).json()["total"] == 1

    page = client.get("/api/history", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 4
    assert [j["title"] for j in page["jobs"]] == ["Cat video", "Lofi beats"]


def test_system_info(client):
    body = client.get("/api/system").json()
    assert set(body) == {"ytdlp_version", "ffmpeg_version", "app_version", "disk_free_bytes", "downloads_bytes"}
    assert body["disk_free_bytes"] > 0


def test_update_ytdlp_reports_versions(client, monkeypatch):
    import system

    monkeypatch.setattr(system, "update_ytdlp", lambda: {"old_version": "2026.01.01", "new_version": "2026.10.26"})
    restarted = []
    monkeypatch.setattr(system, "restart_soon", lambda delay_s=1.0: restarted.append(delay_s))

    body = client.post("/api/system/update-ytdlp").json()
    assert body["old_version"] == "2026.01.01" and body["new_version"] == "2026.10.26"
    assert body["restarting"] is False and restarted == []  # restart is off outside Docker

    client.app.state.settings.restart_on_update = True
    assert client.post("/api/system/update-ytdlp").json()["restarting"] is True
    assert restarted == [1.0]
