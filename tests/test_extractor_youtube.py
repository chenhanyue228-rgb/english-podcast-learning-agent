from pathlib import Path

import pytest

from src.extractor import youtube


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def extract_info(self, source_url: str, download: bool):
        assert source_url == "https://youtu.be/abc"
        assert download is True
        return {"title": "Example", "id": "abc"}

    def prepare_filename(self, info):
        output_template = self.options["outtmpl"]
        return output_template.replace("%(title).200B", "Example").replace("%(id)s", "abc").replace("%(ext)s", "webm")


def test_extract_youtube_audio_uses_yt_dlp(monkeypatch, tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "Example-abc.mp3"
    expected_mp3.write_bytes(b"audio")

    monkeypatch.setattr(youtube, "YoutubeDL", FakeYoutubeDL, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", type("Module", (), {"YoutubeDL": FakeYoutubeDL}))

    result = youtube.extract_youtube_audio("https://youtu.be/abc", tmp_path)

    assert result == expected_mp3


def test_extract_youtube_audio_requires_mp3_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(youtube, "YoutubeDL", FakeYoutubeDL, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", type("Module", (), {"YoutubeDL": FakeYoutubeDL}))

    with pytest.raises(youtube.YouTubeExtractionError, match="mp3 output"):
        youtube.extract_youtube_audio("https://youtu.be/abc", tmp_path)
