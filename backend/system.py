"""Versions, disk usage, and updating yt-dlp in place."""

from __future__ import annotations

import functools
import os
import shutil
import signal
import subprocess
import sys
import threading
from importlib import metadata
from pathlib import Path

from config import Settings


def ytdlp_version() -> str:
    from yt_dlp.version import __version__

    return __version__


def installed_ytdlp_version() -> str:
    """The version on disk, which differs from the loaded one right after an update."""
    out = subprocess.run(
        [sys.executable, "-c", "import importlib.metadata as m; print(m.version('yt-dlp'))"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return out.stdout.strip() or metadata.version("yt-dlp")


@functools.cache
def ffmpeg_version() -> str | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    first = out.splitlines()[0] if out else ""
    parts = first.split()
    return parts[2] if len(parts) > 2 and parts[0] == "ffmpeg" else first or None


def folder_size(path: Path) -> int:
    total = 0
    if path.is_dir():
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
    return total


def info(settings: Settings) -> dict:
    return {
        "ytdlp_version": ytdlp_version(),
        "ffmpeg_version": ffmpeg_version(),
        "app_version": settings.app_version,
        "disk_free_bytes": shutil.disk_usage(settings.downloads_dir).free,
        "downloads_bytes": folder_size(settings.downloads_dir),
    }


def update_ytdlp() -> dict:
    old = ytdlp_version()
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-U", "yt-dlp[default]"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["pip failed"]
        raise RuntimeError(tail[0])
    return {"old_version": old, "new_version": installed_ytdlp_version()}


def restart_soon(delay_s: float = 1.0) -> None:
    """Exit so Docker's restart policy brings the app back with the new yt-dlp loaded."""
    threading.Timer(delay_s, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
