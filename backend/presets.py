"""Download presets and the yt-dlp options behind each one."""

from __future__ import annotations

import copy

OUTTMPL = "%(title).150B [%(id)s].%(ext)s"

_AUDIO_EXTRAS = {
    "writethumbnail": True,
}
_AUDIO_TAIL_POSTPROCESSORS = [
    {"key": "FFmpegMetadata", "add_metadata": True},
    {"key": "EmbedThumbnail", "already_have_thumbnail": False},
]


def _h264(height: int) -> dict:
    return {
        "format": f"bv*[height<={height}]+ba/b[height<={height}]",
        "format_sort": ["vcodec:h264", "acodec:m4a"],
        "merge_output_format": "mp4",
    }


_PRESETS: dict[str, dict] = {
    "video_best": {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
    },
    "video_1080": _h264(1080),
    "video_720": _h264(720),
    "audio_mp3": {
        "format": "ba/b",
        **_AUDIO_EXTRAS,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            *_AUDIO_TAIL_POSTPROCESSORS,
        ],
    },
    "audio_m4a": {
        "format": "ba[ext=m4a]/ba/b",
        **_AUDIO_EXTRAS,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
            *_AUDIO_TAIL_POSTPROCESSORS,
        ],
    },
}

# Extension of the finished file for each preset.
OUTPUT_EXT = {
    "video_best": "mp4",
    "video_1080": "mp4",
    "video_720": "mp4",
    "audio_mp3": "mp3",
    "audio_m4a": "m4a",
}

PRESET_NAMES = tuple(_PRESETS)


def is_preset(name: str) -> bool:
    return name in _PRESETS


def options_for(name: str) -> dict:
    """A fresh yt-dlp options dict for the preset (safe to mutate)."""
    if name not in _PRESETS:
        raise KeyError(f"Unknown preset: {name}")
    opts = copy.deepcopy(_PRESETS[name])
    opts["outtmpl"] = OUTTMPL
    return opts
