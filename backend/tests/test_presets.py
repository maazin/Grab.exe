import pytest

import presets

TAIL = [
    {"key": "FFmpegMetadata", "add_metadata": True},
    {"key": "EmbedThumbnail", "already_have_thumbnail": False},
]
OUT = "%(title).150B [%(id)s].%(ext)s"


def test_video_best():
    assert presets.options_for("video_best") == {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": OUT,
    }


@pytest.mark.parametrize("name,height", [("video_1080", 1080), ("video_720", 720)])
def test_video_h264(name, height):
    assert presets.options_for(name) == {
        "format": f"bv*[height<={height}]+ba/b[height<={height}]",
        "format_sort": ["vcodec:h264", "acodec:m4a"],
        "merge_output_format": "mp4",
        "outtmpl": OUT,
    }


def test_audio_mp3():
    assert presets.options_for("audio_mp3") == {
        "format": "ba/b",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            *TAIL,
        ],
        "outtmpl": OUT,
    }


def test_audio_m4a():
    assert presets.options_for("audio_m4a") == {
        "format": "ba[ext=m4a]/ba/b",
        "writethumbnail": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}, *TAIL],
        "outtmpl": OUT,
    }


def test_options_are_fresh_copies():
    a = presets.options_for("audio_mp3")
    a["postprocessors"].clear()
    assert presets.options_for("audio_mp3")["postprocessors"]


def test_every_preset_has_an_output_ext():
    assert set(presets.PRESET_NAMES) == set(presets.OUTPUT_EXT)
    with pytest.raises(KeyError):
        presets.options_for("video_4k")
