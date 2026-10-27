"""API error codes and the mapping from yt-dlp failures to them."""

from __future__ import annotations

import errno
import re

MESSAGES = {
    "invalid_url": "That doesn't look like a YouTube link.",
    "unavailable": "This video is private, removed, or not available in this region.",
    "age_restricted": "This video is age-restricted, which Grab doesn't support.",
    "bot_check": "YouTube blocked the request as a possible bot. Try Update yt-dlp in Settings, or wait a while.",
    "ffmpeg_failed": "Converting the file with ffmpeg failed.",
    "disk_full": "The disk is full. Delete some downloads and try again.",
    "expired": "This file has expired and was deleted. Use Get again to download it again.",
    "not_found": "That job doesn't exist.",
    "invalid_request": "The request was not valid.",
    "unauthorized": "Sign in through Cloudflare Access to use Grab.",
    "unknown": "Something went wrong.",
}

STATUS = {
    "invalid_url": 400,
    "invalid_request": 400,
    "unavailable": 422,
    "age_restricted": 422,
    "bot_check": 503,
    "ffmpeg_failed": 500,
    "disk_full": 507,
    "expired": 410,
    "not_found": 404,
    "unauthorized": 401,
    "unknown": 500,
}


class GrabError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or MESSAGES.get(code, MESSAGES["unknown"])
        super().__init__(self.message)

    @property
    def status(self) -> int:
        return STATUS.get(self.code, 500)

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


# Checked in order; the first pattern that matches wins.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("bot_check", re.compile(r"not a bot|confirm you.re not a bot|HTTP Error 429", re.I)),
    ("age_restricted", re.compile(r"confirm your age|age.restricted|inappropriate for some users", re.I)),
    (
        "unavailable",
        re.compile(
            r"private video|video unavailable|(video|playlist) is unavailable|has been removed|no longer available|"
            r"available in your country|members.only|join this channel|"
            r"does not exist|account associated with this video has been terminated|"
            r"premieres in|live event will begin|this video is not available|playlist does not exist",
            re.I,
        ),
    ),
    ("invalid_url", re.compile(r"unsupported url|is not a valid url|incomplete youtube id", re.I)),
    ("disk_full", re.compile(r"no space left on device", re.I)),
    ("ffmpeg_failed", re.compile(r"ffmpeg|ffprobe|postprocess|conversion failed", re.I)),
]

_PREFIX = re.compile(r"^(ERROR:\s*)?(\[[^\]]+\]\s*)?([\w-]{11}:\s*)?")


def _clean(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return _PREFIX.sub("", first).strip()[:300]


def classify(exc: BaseException) -> GrabError:
    """Turn any exception raised while probing or downloading into a GrabError."""
    if isinstance(exc, GrabError):
        return exc
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return GrabError("disk_full")

    text = str(exc)
    for code, pattern in _PATTERNS:
        if pattern.search(text):
            return GrabError(code)

    # yt-dlp wraps post-processor failures; check the type by name so this
    # module doesn't need to import yt-dlp.
    names = {cls.__name__ for cls in type(exc).__mro__}
    cause = getattr(exc, "exc_info", None)
    if cause and cause[1] is not None:
        names |= {cls.__name__ for cls in type(cause[1]).__mro__}
    if "PostProcessingError" in names:
        return GrabError("ffmpeg_failed")

    detail = _clean(text)
    return GrabError("unknown", f"Something went wrong: {detail}" if detail else None)
