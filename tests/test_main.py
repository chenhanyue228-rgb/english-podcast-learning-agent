from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src import main as app_main
from src.analyzer.models import AIAnalysisResult, PodcastMetadata, Summary
from src.config.settings import AppSettings
from src.pipeline.validators import AudioValidationError, AudioValidationResult
from src.transcriber.whisper import TranscriptSegment


@dataclass
class FakeTranscript:
    segments: list[TranscriptSegment]

    def to_dict(self):
        return {
            "segments": [
                {"start": segment.start, "end": segment.end, "text": segment.text}
                for segment in self.segments
            ],
            "language": "en",
        }


def test_parse_args_accepts_source() -> None:
    args = app_main.parse_args(["https://youtu.be/abc"])

    assert args.source == "https://youtu.be/abc"


def test_notion_source_type_mapping() -> None:
    from src.extractor.router import SourceType

    assert app_main.notion_source_type(SourceType.YOUTUBE) == "YouTube"
    assert app_main.notion_source_type(SourceType.APPLE_PODCAST) == "Podcast"
    assert app_main.notion_source_type(SourceType.PODCAST_RSS) == "Podcast"
    assert app_main.notion_source_type(SourceType.DIRECT_AUDIO) == "Podcast"
    assert app_main.notion_source_type(SourceType.LOCAL_AUDIO) == "Local Audio"


def test_run_pipeline_without_analysis_json_prepares_codex_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {}
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(
        app_main,
        "extract_audio_from_source",
        lambda source, output_dir: calls.setdefault(
            "extract", (source, output_dir)
        )
        or audio_path,
    )

    def fake_extract(source, output_dir):
        calls["extract"] = (source, output_dir)
        return audio_path

    def fake_transcribe(audio, model_size, device, compute_type):
        calls["transcribe"] = (audio, model_size, device, compute_type)
        return FakeTranscript([TranscriptSegment(0.0, 1.0, "Hello")])

    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "extract_audio_from_source", fake_extract)
    monkeypatch.setattr(
        app_main,
        "validate_audio_source",
        lambda audio: calls.setdefault(
            "validate",
            AudioValidationResult(path=audio_path.resolve(), size_bytes=2048, duration_seconds=60.0),
        ),
    )
    monkeypatch.setattr(app_main, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(
        app_main,
        "publish_complete_learning_materials",
        lambda payload: pytest.fail("Notion page should not be created without analysis JSON"),
    )

    args = app_main.parse_args(
        [
            "https://youtu.be/abc",
            "--title",
            "Example",
            "--model-size",
            "tiny",
        ]
    )

    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "analysis_request"
    assert result.value.endswith("analysis_requests/example.json")
    assert calls["extract"][0] == "https://youtu.be/abc"
    assert calls["validate"].path == audio_path.resolve()
    assert calls["transcribe"] == (audio_path.resolve(), "tiny", "auto", "default")
    transcript_path = tmp_path / "transcripts" / "example.json"
    assert transcript_path.exists()
    assert "Hello" in transcript_path.read_text(encoding="utf-8")
    request_path = tmp_path / "analysis_requests" / "example.json"
    assert request_path.exists()
    request_text = request_path.read_text(encoding="utf-8")
    assert "Hello" in request_text
    assert "summary" in request_text


def test_run_pipeline_uses_resolved_podcast_title(monkeypatch, tmp_path: Path) -> None:
    calls = {}
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(app_main, "resolve_podcast_title", lambda source: "Real Episode Title")
    monkeypatch.setattr(app_main, "extract_audio_from_source", lambda source, output_dir: audio_path)
    monkeypatch.setattr(
        app_main,
        "validate_audio_source",
        lambda audio: AudioValidationResult(
            path=audio_path.resolve(),
            size_bytes=2048,
            duration_seconds=60.0,
        ),
    )
    monkeypatch.setattr(
        app_main,
        "transcribe_audio",
        lambda audio, model_size, device, compute_type: FakeTranscript(
            [TranscriptSegment(0.0, 1.0, "Hello")]
        ),
    )

    result = app_main.run_pipeline(
        app_main.parse_args(["https://podcasts.apple.com/us/podcast/name/id123?i=456"])
    )

    assert result is not None
    assert result.kind == "analysis_request"
    assert result.value.endswith("real_episode_title.json")


def test_run_pipeline_publishes_codex_generated_ai_learning_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {}
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    def fake_transcribe(audio, model_size, device, compute_type):
        calls["transcribe"] = (audio, model_size, device, compute_type)
        return FakeTranscript([TranscriptSegment(0.0, 1.0, "Hello AI")])

    analysis = AIAnalysisResult(
        summary=Summary(english="Summary", chinese="中文", key_points=[]),
        podcast_metadata=PodcastMetadata(
            topic="AI",
            difficulty="Intermediate",
            short_summary="Short summary.",
        ),
    )

    class FakeLearningAnalyzer:
        def prepare_analysis_request(self, transcript_input):
            calls["analysis_request"] = transcript_input

        def validate_generated_analysis(self, generated_output):
            calls["generated_output"] = generated_output
            return analysis

    def fake_publish(payload):
        calls["publish"] = payload
        return type(
            "PublishResult",
            (),
            {
                "podcast_page_id": "page_123",
                "podcast_page_url": "https://notion.so/page_123",
                "expression_page_ids": ["expr_1"],
            },
        )()

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "extract_audio_from_source",
        lambda source, output_dir: audio_path,
    )
    monkeypatch.setattr(
        app_main,
        "validate_audio_source",
        lambda audio: AudioValidationResult(
            path=audio_path.resolve(),
            size_bytes=2048,
            duration_seconds=60.0,
        ),
    )
    monkeypatch.setattr(app_main, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(app_main, "LearningAnalyzer", FakeLearningAnalyzer)
    monkeypatch.setattr(
        app_main,
        "read_generated_analysis_file",
        lambda path: {"summary": {"english": "generated"}},
    )
    monkeypatch.setattr(app_main, "publish_complete_learning_materials", fake_publish)

    analysis_json = tmp_path / "analysis.json"
    analysis_json.write_text("{}", encoding="utf-8")
    args = app_main.parse_args(
        [
            "https://youtu.be/abc",
            "--title",
            "Example",
            "--analysis-json",
            str(analysis_json),
        ]
    )

    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "notion_page"
    assert result.value == "https://notion.so/page_123"
    assert calls["analysis_request"].title == "Example"
    assert calls["analysis_request"].transcript == "Hello AI"
    assert calls["generated_output"] == {"summary": {"english": "generated"}}
    assert calls["publish"].title == "Example"
    assert calls["publish"].source_url == "https://youtu.be/abc"
    assert calls["publish"].source_type == "YouTube"
    assert calls["publish"].analysis is analysis
    assert calls["publish"].transcript == "Hello AI"


def test_run_pipeline_weekly_review_request_only(monkeypatch, tmp_path: Path) -> None:
    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    class FakeConfig:
        token = "secret"
        podcast_database_id = "podcast_db"
        expression_database_id = "expression_db"
        weekly_database_id = "weekly_db"

    class FakeNotion:
        pass

    class FakeWeeklyData:
        week = "2026-W29"
        date = "2026-07-17"
        podcasts = []

    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "load_notion_config", lambda: FakeConfig())
    monkeypatch.setattr(app_main, "create_notion_client", lambda token: FakeNotion())
    monkeypatch.setattr(
        app_main,
        "fetch_weekly_learning_data",
        lambda notion, podcast_database_id, expression_database_id: FakeWeeklyData(),
    )
    monkeypatch.setattr(
        app_main,
        "save_weekly_review_request",
        lambda weekly_data, output_path: calls.setdefault("request_path", output_path) or output_path,
    )
    monkeypatch.setattr(
        app_main,
        "publish_weekly_review",
        lambda payload, notion, weekly_database_id: pytest.fail("Should not publish without weekly review JSON"),
    )

    args = app_main.parse_args(["--weekly-review"])
    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "weekly_review_request"
    assert result.value.endswith("weekly_review_requests/2026-W29.json")
    assert calls["request_path"].name == "2026-W29.json"


def test_run_pipeline_weekly_review_publish(monkeypatch, tmp_path: Path) -> None:
    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    class FakeConfig:
        token = "secret"
        podcast_database_id = "podcast_db"
        expression_database_id = "expression_db"
        weekly_database_id = "weekly_db"

    class FakeNotion:
        pass

    class FakeWeeklyData:
        week = "2026-W29"
        date = "2026-07-17"
        podcasts = [type("Podcast", (), {"page_id": "podcast_1"})()]

    analysis_json = tmp_path / "weekly_review.json"
    analysis_json.write_text(
        '{"week":"2026-W29","date":"2026-07-17","statistics":{"podcast_count":1,"expression_count":1,"category_distribution":{}},"summary":{"english":"Summary","chinese":"总结"},"key_learning_points":["Point"],"recommended_review":[{"expression":"take ownership","reason":"Useful"}]}',
        encoding="utf-8",
    )

    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "load_notion_config", lambda: FakeConfig())
    monkeypatch.setattr(app_main, "create_notion_client", lambda token: FakeNotion())
    monkeypatch.setattr(
        app_main,
        "fetch_weekly_learning_data",
        lambda notion, podcast_database_id, expression_database_id: FakeWeeklyData(),
    )
    monkeypatch.setattr(
        app_main,
        "save_weekly_review_request",
        lambda weekly_data, output_path: output_path,
    )
    monkeypatch.setattr(
        app_main,
        "validate_weekly_review_output",
        lambda payload: payload,
    )
    monkeypatch.setattr(
        app_main,
        "read_generated_analysis_file",
        lambda path: {
            "week": "2026-W29",
            "date": "2026-07-17",
            "statistics": {"podcast_count": 1, "expression_count": 1, "category_distribution": {}},
            "summary": {"english": "Summary", "chinese": "总结"},
            "key_learning_points": ["Point"],
            "recommended_review": [{"expression": "take ownership", "reason": "Useful"}],
        },
    )

    class PublishResult:
        page_id = "weekly_page"
        page_url = "https://notion.so/weekly_page"

    def fake_publish(payload, notion, weekly_database_id):
        calls["payload"] = payload
        calls["weekly_database_id"] = weekly_database_id
        return PublishResult()

    monkeypatch.setattr(app_main, "publish_weekly_review", fake_publish)

    args = app_main.parse_args(["--weekly-review", "--weekly-review-json", str(analysis_json)])
    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "weekly_review_page"
    assert result.value == "https://notion.so/weekly_page"
    assert calls["weekly_database_id"] == "weekly_db"
    assert calls["payload"].podcast_page_ids == ["podcast_1"]


def test_run_pipeline_with_existing_transcript_skips_audio_and_whisper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {}
    transcript_json = tmp_path / "transcript.json"
    transcript_json.write_text(
        '{"segments":[{"start":0,"end":1,"text":"Existing transcript"}],"language":"en"}',
        encoding="utf-8",
    )
    analysis_json = tmp_path / "analysis.json"
    analysis_json.write_text("{}", encoding="utf-8")

    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )
    analysis = AIAnalysisResult(
        summary=Summary(english="Summary", chinese="中文", key_points=[]),
        podcast_metadata=PodcastMetadata(
            topic="Communication",
            difficulty="Intermediate",
            short_summary="Short summary.",
        ),
    )

    class FakeLearningAnalyzer:
        def prepare_analysis_request(self, transcript_input):
            calls["analysis_request"] = transcript_input

        def validate_generated_analysis(self, generated_output):
            calls["generated_output"] = generated_output
            return analysis

    def fake_publish(payload):
        calls["publish"] = payload
        return type(
            "PublishResult",
            (),
            {
                "podcast_page_id": "page_123",
                "podcast_page_url": "https://notion.so/page_123",
                "expression_page_ids": [],
            },
        )()

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "extract_audio_from_source",
        lambda *args, **kwargs: pytest.fail("audio extraction should be skipped"),
    )
    monkeypatch.setattr(
        app_main,
        "transcribe_audio",
        lambda *args, **kwargs: pytest.fail("Whisper should be skipped"),
    )
    monkeypatch.setattr(app_main, "LearningAnalyzer", FakeLearningAnalyzer)
    monkeypatch.setattr(app_main, "read_generated_analysis_file", lambda path: {})
    monkeypatch.setattr(app_main, "publish_complete_learning_materials", fake_publish)

    result = app_main.run_pipeline(
        app_main.parse_args(
            [
                "https://youtu.be/abc",
                "--title",
                "Example",
                "--transcript-json",
                str(transcript_json),
                "--analysis-json",
                str(analysis_json),
            ]
        )
    )

    assert result is not None
    assert result.kind == "notion_page"
    assert result.value == "https://notion.so/page_123"
    assert calls["analysis_request"].transcript == "Existing transcript"
    assert calls["publish"].transcript == "Existing transcript"


def test_run_pipeline_ai_enabled_without_analysis_json_prepares_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "extract_audio_from_source", lambda source, output_dir: audio_path)
    monkeypatch.setattr(
        app_main,
        "validate_audio_source",
        lambda audio: AudioValidationResult(
            path=audio_path.resolve(),
            size_bytes=2048,
            duration_seconds=60.0,
        ),
    )
    monkeypatch.setattr(
        app_main,
        "transcribe_audio",
        lambda audio, model_size, device, compute_type: FakeTranscript(
            [TranscriptSegment(0.0, 1.0, "Hello AI")]
        ),
    )
    monkeypatch.setattr(
        app_main,
        "publish_complete_learning_materials",
        lambda payload: pytest.fail("Notion page should not be created without analysis JSON"),
    )

    args = app_main.parse_args(["https://youtu.be/abc", "--title", "Example"])

    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "analysis_request"


def test_run_pipeline_stops_before_transcription_when_audio_validation_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"tiny")
    settings = AppSettings(
        environment="test",
        log_level="INFO",
        data_dir=tmp_path,
        audio_output_dir=tmp_path / "audio",
        transcript_output_dir=tmp_path / "transcripts",
        notion_token="secret",
        notion_parent_page_id=None,
        notion_podcast_database_id="podcast_db",
    )

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "extract_audio_from_source", lambda source, output_dir: audio_path)
    monkeypatch.setattr(
        app_main,
        "validate_audio_source",
        lambda audio: (_ for _ in ()).throw(AudioValidationError("Audio file is too small")),
    )
    monkeypatch.setattr(
        app_main,
        "transcribe_audio",
        lambda *args, **kwargs: pytest.fail("transcription should not start"),
    )
    monkeypatch.setattr(
        app_main,
        "publish_complete_learning_materials",
        lambda payload: pytest.fail("Notion page should not be created"),
    )

    with pytest.raises(AudioValidationError, match="too small"):
        app_main.run_pipeline(app_main.parse_args(["https://youtu.be/abc"]))


def test_main_returns_error_for_missing_source(capsys) -> None:
    exit_code = app_main.main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing source" in captured.err
    assert "Traceback" not in captured.err


def test_main_returns_clean_error_for_unsupported_source(capsys) -> None:
    exit_code = app_main.main(["https://example.com/article"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error:" in captured.err
    assert "Unsupported URL type" in captured.err
    assert "Generic podcast platform pages are not supported yet" in captured.err
    assert "Traceback" not in captured.err


def test_main_print_config(monkeypatch, capsys) -> None:
    monkeypatch.setattr(app_main, "print_config", lambda: print("config ok"))

    exit_code = app_main.main(["--print-config"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "config ok" in captured.out
