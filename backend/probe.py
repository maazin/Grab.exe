"""Read a link's metadata without downloading anything."""

from __future__ import annotations

import threading
import time
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL

from errors import GrabError, classify

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

CACHE_TTL_S = 600


class _QuietLogger:
    """yt-dlp prints errors to stderr even when quiet; they come back to us as exceptions instead."""

    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


def check_url(url: str) -> str:
    """Return the cleaned URL, or raise invalid_url for anything that isn't YouTube."""
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    try:
        parsed = urlparse(url)
    except ValueError:
        raise GrabError("invalid_url") from None
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in YOUTUBE_HOSTS:
        raise GrabError("invalid_url")
    return url


def is_playlist_url(url: str) -> bool:
    """Only /playlist links are treated as playlists; a watch link with &list= is the single video."""
    parsed = urlparse(url)
    return parsed.path.rstrip("/") == "/playlist" and "list" in parse_qs(parsed.query)


def thumb_for(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _shape(info: dict, playlist: bool) -> dict:
    if not playlist:
        return {
            "video_id": info.get("id"),
            "title": info.get("title") or info.get("id"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration_s": _int(info.get("duration")),
            "thumbnail_url": info.get("thumbnail") or (thumb_for(info["id"]) if info.get("id") else None),
            "is_playlist": False,
            "entries": [],
        }

    entries = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        # Deleted and private videos still show up in flat playlists.
        if e.get("title") in ("[Deleted video]", "[Private video]"):
            continue
        entries.append({"video_id": e["id"], "title": e.get("title") or e["id"], "duration_s": _int(e.get("duration"))})
    thumbs = info.get("thumbnails") or []
    thumb = thumbs[-1].get("url") if thumbs else (thumb_for(entries[0]["video_id"]) if entries else None)
    return {
        "video_id": info.get("id"),
        "title": info.get("title") or "Playlist",
        "uploader": info.get("uploader") or info.get("channel"),
        "duration_s": sum(e["duration_s"] or 0 for e in entries) or None,
        "thumbnail_url": thumb,
        "is_playlist": True,
        "entries": entries,
    }


class Prober:
    """Runs extract_info and keeps results for a few minutes, so creating jobs right after a probe is instant."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def probe(self, url: str) -> dict:
        url = check_url(url)
        with self._lock:
            hit = self._cache.get(url)
            if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
                return hit[1]

        playlist = is_playlist_url(url)
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "logger": _QuietLogger(),
            "noplaylist": not playlist,
        }
        if playlist:
            opts["extract_flat"] = "in_playlist"
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001 - every failure becomes an API error
            raise classify(exc) from exc
        if not info:
            raise GrabError("unavailable")
        if info.get("_type") == "playlist" and not playlist:
            playlist = True
        result = _shape(info, playlist)
        if playlist and not result["entries"]:
            raise GrabError("unavailable", "This playlist is empty or private.")
        if not result["video_id"]:
            raise GrabError("unavailable")

        with self._lock:
            if len(self._cache) > 100:
                self._cache.clear()
            self._cache[url] = (time.monotonic(), result)
        return result
