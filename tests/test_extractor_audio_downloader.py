from pathlib import Path

import pytest

from src.extractor import audio_downloader


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
        return (
            self.options["outtmpl"]
            .replace("%(title).200B", "Example")
            .replace("%(id)s", "abc")
            .replace("%(ext)s", "webm")
        )


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "audio/mpeg"):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.offset = 0
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.offset >= len(self.content):
            return b""
        if size < 0:
            size = len(self.content) - self.offset
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_download_audio_routes_youtube(monkeypatch, tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "youtube.mp3"
    expected_mp3.write_bytes(b"audio")

    monkeypatch.setattr(
        audio_downloader,
        "download_youtube_audio",
        lambda url, output_dir: expected_mp3,
    )

    assert audio_downloader.download_audio("https://youtu.be/abc", tmp_path) == expected_mp3


def test_download_audio_routes_remote_audio(monkeypatch, tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "episode.mp3"
    expected_mp3.write_bytes(b"audio")

    monkeypatch.setattr(
        audio_downloader,
        "download_remote_audio",
        lambda url, output_dir: expected_mp3,
    )

    assert (
        audio_downloader.download_audio("https://cdn.example.com/episode.mp3", tmp_path)
        == expected_mp3
    )


def test_download_youtube_audio_uses_yt_dlp(monkeypatch, tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "Example-abc.mp3"
    expected_mp3.write_bytes(b"audio")

    monkeypatch.setitem(
        __import__("sys").modules,
        "yt_dlp",
        type("Module", (), {"YoutubeDL": FakeYoutubeDL}),
    )

    assert audio_downloader.download_youtube_audio("https://youtu.be/abc", tmp_path) == expected_mp3


def test_download_youtube_audio_requires_mp3_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(
        __import__("sys").modules,
        "yt_dlp",
        type("Module", (), {"YoutubeDL": FakeYoutubeDL}),
    )

    with pytest.raises(audio_downloader.AudioDownloadError, match="not created"):
        audio_downloader.download_youtube_audio("https://youtu.be/abc", tmp_path)


def test_download_remote_audio_keeps_mp3(monkeypatch, tmp_path: Path) -> None:
    response = FakeResponse(b"audio", "audio/mpeg")
    monkeypatch.setattr(
        audio_downloader,
        "urlopen",
        lambda request, timeout=60: response,
    )

    result = audio_downloader.download_remote_audio(
        "https://cdn.example.com/My Episode.mp3",
        tmp_path,
    )

    assert result == (tmp_path / "My_Episode.mp3").resolve()
    assert result.read_bytes() == b"audio"
    assert response.read_sizes[0] == audio_downloader.DOWNLOAD_CHUNK_SIZE_BYTES


def test_download_remote_audio_reuses_existing_mp3(monkeypatch, tmp_path: Path) -> None:
    existing = tmp_path / "episode.mp3"
    existing.write_bytes(b"existing audio")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("urlopen should not be called for existing audio")

    monkeypatch.setattr(audio_downloader, "urlopen", fail_urlopen)

    assert (
        audio_downloader.download_remote_audio(
            "https://cdn.example.com/episode.mp3",
            tmp_path,
        )
        == existing.resolve()
    )


def test_download_remote_audio_reuses_existing_converted_mp3(
    monkeypatch,
    tmp_path: Path,
) -> None:
    existing = tmp_path / "episode.mp3"
    existing.write_bytes(b"existing converted audio")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("urlopen should not be called for existing converted audio")

    monkeypatch.setattr(audio_downloader, "urlopen", fail_urlopen)

    assert (
        audio_downloader.download_remote_audio(
            "https://cdn.example.com/episode.m4a",
            tmp_path,
        )
        == existing.resolve()
    )


def test_download_remote_audio_removes_partial_file_on_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class BrokenResponse(FakeResponse):
        def read(self, size: int = -1) -> bytes:
            if self.offset == 0:
                self.offset += 1
                return b"partial"
            raise OSError("network stalled")

    monkeypatch.setattr(
        audio_downloader,
        "urlopen",
        lambda request, timeout=60: BrokenResponse(b"audio", "audio/mpeg"),
    )

    with pytest.raises(audio_downloader.AudioDownloadError, match="network stalled"):
        audio_downloader.download_remote_audio(
            "https://cdn.example.com/partial.mp3",
            tmp_path,
        )

    assert not (tmp_path / "partial.mp3").exists()


def test_download_remote_audio_retries_after_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {"count": 0}

    def flaky_urlopen(request, timeout=60):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("timed out")
        return FakeResponse(b"audio", "audio/mpeg")

    monkeypatch.setattr(audio_downloader, "urlopen", flaky_urlopen)

    result = audio_downloader.download_remote_audio(
        "https://cdn.example.com/retry.mp3",
        tmp_path,
        max_retries=2,
    )

    assert calls["count"] == 2
    assert result == (tmp_path / "retry.mp3").resolve()
    assert result.read_bytes() == b"audio"


def test_download_remote_audio_raises_after_timeout_retries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {"count": 0}

    def timeout_urlopen(request, timeout=60):
        calls["count"] += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr(audio_downloader, "urlopen", timeout_urlopen)

    with pytest.raises(audio_downloader.AudioDownloadError, match="after 2 attempts"):
        audio_downloader.download_remote_audio(
            "https://cdn.example.com/timeout.mp3",
            tmp_path,
            max_retries=2,
        )

    assert calls["count"] == 2
    assert not (tmp_path / "timeout.mp3").exists()


def test_download_remote_audio_converts_non_mp3(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        audio_downloader,
        "urlopen",
        lambda request, timeout=60: FakeResponse(b"audio", "audio/mp4"),
    )

    def fake_convert(input_path: Path) -> Path:
        assert input_path == tmp_path / "episode.m4a"
        output_path = tmp_path / "episode.mp3"
        output_path.write_bytes(b"mp3")
        return output_path.resolve()

    monkeypatch.setattr(audio_downloader, "convert_to_mp3", fake_convert)

    assert (
        audio_downloader.download_remote_audio("https://cdn.example.com/episode.m4a", tmp_path)
        == (tmp_path / "episode.mp3").resolve()
    )


def test_download_remote_audio_converts_wav(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        audio_downloader,
        "urlopen",
        lambda request, timeout=60: FakeResponse(b"audio", "audio/wav"),
    )

    def fake_convert(input_path: Path) -> Path:
        assert input_path == tmp_path / "episode.wav"
        output_path = tmp_path / "episode.mp3"
        output_path.write_bytes(b"mp3")
        return output_path.resolve()

    monkeypatch.setattr(audio_downloader, "convert_to_mp3", fake_convert)

    assert (
        audio_downloader.download_remote_audio("https://cdn.example.com/episode.wav", tmp_path)
        == (tmp_path / "episode.mp3").resolve()
    )


def test_download_remote_audio_rejects_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(audio_downloader.AudioDownloadError, match="supported audio"):
        audio_downloader.download_remote_audio("https://cdn.example.com/episode.aac", tmp_path)


def test_download_remote_audio_rejects_non_audio_content(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        audio_downloader,
        "urlopen",
        lambda request, timeout=60: FakeResponse(b"html", "text/html"),
    )

    with pytest.raises(audio_downloader.AudioDownloadError, match="did not return audio"):
        audio_downloader.download_remote_audio("https://cdn.example.com/episode.mp3", tmp_path)


def test_convert_to_mp3_requires_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "episode.m4a"
    source.write_bytes(b"audio")
    monkeypatch.setattr(audio_downloader.shutil, "which", lambda name: None)

    with pytest.raises(audio_downloader.AudioDownloadError, match="ffmpeg"):
        audio_downloader.convert_to_mp3(source)


def test_validate_audio_file_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")

    with pytest.raises(audio_downloader.AudioDownloadError, match="empty"):
        audio_downloader.validate_audio_file(empty)
