"""Error mapping, the progress tracker, and SSE throttling."""

import asyncio
import errno

import pytest

from errors import classify
from events import Broadcaster
from probe import check_url, is_playlist_url
from worker import _Progress


@pytest.mark.parametrize(
    "message,code",
    [
        ("ERROR: [youtube] abc: Sign in to confirm you’re not a bot. Use --cookies", "bot_check"),
        ("ERROR: [youtube] abc: Sign in to confirm your age.", "age_restricted"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "unavailable"),
        ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", "unavailable"),
        ("ERROR: [youtube] abc: This video is unavailable", "unavailable"),
        ("ERROR: [youtube] abc: The uploader has not made this video available in your country", "unavailable"),
        ("ERROR: Unsupported URL: https://example.com", "invalid_url"),
        ("ERROR: Postprocessing: ffprobe and ffmpeg not found", "ffmpeg_failed"),
        ("ERROR: something new and strange", "unknown"),
    ],
)
def test_classify(message, code):
    assert classify(Exception(message)).code == code


def test_classify_disk_full():
    assert classify(OSError(errno.ENOSPC, "No space left on device")).code == "disk_full"


def test_unknown_message_is_cleaned():
    err = classify(Exception("ERROR: [youtube] dQw4w9WgXcQ: Something odd\nTraceback..."))
    assert err.message == "Something went wrong: Something odd"


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("youtu.be/dQw4w9WgXcQ", True),
        ("https://youtube.com/shorts/abcdefghijk", True),
        ("https://music.youtube.com/watch?v=abc", True),
        ("https://vimeo.com/123", False),
        ("not a url", False),
        ("ftp://youtube.com/x", False),
    ],
)
def test_check_url(url, ok):
    if ok:
        assert check_url(url).startswith("https://")
    else:
        with pytest.raises(Exception) as info:
            check_url(url)
        assert info.value.code == "invalid_url"


def test_playlist_url_detection():
    assert is_playlist_url("https://www.youtube.com/playlist?list=PL123")
    assert not is_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123")


def test_progress_combines_streams_and_never_goes_backwards():
    p = _Progress()
    fmt = {"requested_formats": [{"filesize": 800}, {"filesize_approx": 200}]}
    a = p.update(
        {"status": "downloading", "filename": "v", "downloaded_bytes": 400, "total_bytes": 800, "speed": 100, "info_dict": fmt}
    )
    assert a["progress_pct"] == 40.0 and a["total_bytes"] == 1000 and a["eta_s"] == 6
    p.update({"status": "finished", "filename": "v", "total_bytes": 800, "info_dict": fmt})
    b = p.update({"status": "downloading", "filename": "a", "downloaded_bytes": 100, "total_bytes": 200, "info_dict": fmt})
    assert b["progress_pct"] == 90.0 and b["downloaded_bytes"] == 900


def test_progress_estimates_from_bitrate():
    p = _Progress()
    fmt = {"duration": 10, "requested_formats": [{"tbr": 800}, {"tbr": 160}]}
    r = p.update(
        {"status": "downloading", "filename": "v", "downloaded_bytes": 100_000, "total_bytes": 1_000_000, "info_dict": fmt}
    )
    assert r["total_bytes"] == 1_200_000


def test_broadcaster_throttles_progress_but_not_status_changes():
    async def run():
        bus = Broadcaster()
        bus.bind(asyncio.get_running_loop())
        q = bus.subscribe()
        for pct in range(10):
            bus.publish({"id": "j", "status": "downloading", "progress_pct": pct})
        bus.publish({"id": "j", "status": "done", "progress_pct": 100})
        await asyncio.sleep(0.01)
        messages = []
        while not q.empty():
            messages.append(q.get_nowait())
        return messages

    messages = asyncio.run(run())
    assert len(messages) == 2
    assert messages[0].startswith("event: job\ndata: ")
    assert '"status":"done"' in messages[1]
