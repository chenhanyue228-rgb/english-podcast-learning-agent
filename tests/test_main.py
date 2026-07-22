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


def test_parse_args_accepts_publish_highlight_vocab() -> None:
    args = app_main.parse_args(["--publish-highlight-vocab", "11111111111111111111111111111111"])

    assert args.publish_highlight_vocab == "11111111111111111111111111111111"


def test_parse_args_accepts_run_vocabulary_agent() -> None:
    args = app_main.parse_args(["--run-vocabulary-agent"])

    assert args.run_vocabulary_agent is True


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


def test_run_pipeline_publishes_highlight_vocabulary(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    calls = {}

    def fake_publish_highlight_vocabulary(page_id: str):
        calls["page_id"] = page_id
        return type(
            "Result",
            (),
            {
                "page_id": page_id,
                "created": 1,
                "updated": 0,
                "skipped": 0,
            },
        )()

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "publish_highlight_vocabulary", fake_publish_highlight_vocabulary)

    result = app_main.run_pipeline(
        app_main.parse_args(["--publish-highlight-vocab", "11111111111111111111111111111111"])
    )

    assert result is not None
    assert result.kind == "highlight_vocab_page"
    assert calls["page_id"] == "11111111111111111111111111111111"


def test_run_pipeline_previews_highlight_vocabulary_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
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
    calls = {}

    def fake_build_vocabulary_learning_preview(page_id: str):
        calls["page_id"] = page_id
        return {
            "page_id": page_id,
            "approved_vocabulary": [{"word": "fundraising"}],
            "rejected_candidates": [{"word": "Christensen", "reason": "proper name"}],
        }

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "build_vocabulary_learning_preview",
        fake_build_vocabulary_learning_preview,
    )
    monkeypatch.setattr(
        app_main,
        "publish_highlight_vocabulary",
        lambda page_id: pytest.fail("Dry run must not publish or upsert vocabulary."),
    )

    result = app_main.run_pipeline(
        app_main.parse_args(
            [
                "--publish-highlight-vocab",
                "11111111111111111111111111111111",
                "--dry-run",
            ]
        )
    )

    captured = capsys.readouterr()
    assert result is not None
    assert result.kind == "highlight_vocab_dry_run"
    assert result.value == "approved=1, rejected=1"
    assert calls["page_id"] == "11111111111111111111111111111111"
    assert "Highlight vocabulary dry run" in captured.out
    assert "Approved: 1" in captured.out
    assert "Rejected: 1" in captured.out


def test_run_pipeline_runs_vocabulary_sync_agent(monkeypatch, tmp_path: Path) -> None:
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

    calls = {}

    def fake_sync_vocabulary_from_highlight_changes():
        calls["called"] = True
        return type(
            "Result",
            (),
            {
                "scanned_pages": 2,
                "new_highlights": 1,
                "created": 1,
                "updated": 0,
                "skipped": 0,
            },
        )()

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "sync_vocabulary_from_highlight_changes", fake_sync_vocabulary_from_highlight_changes)

    result = app_main.run_pipeline(app_main.parse_args(["--run-vocabulary-agent"]))

    assert result is not None
    assert result.kind == "vocabulary_sync_agent"
    assert calls["called"] is True


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


def test_parse_args_accepts_sync_vocab_comments() -> None:
    args = app_main.parse_args(["--sync-vocab-comments"])

    assert args.sync_vocab_comments is True


def test_parse_args_accepts_debug_comments() -> None:
    args = app_main.parse_args(["--debug-comments"])

    assert args.debug_comments is True


def test_parse_args_accepts_debug_page_comments() -> None:
    args = app_main.parse_args(["--debug-page-comments"])

    assert args.debug_page_comments is True


def test_parse_args_accepts_debug_comment_sources() -> None:
    args = app_main.parse_args(["--debug-comment-sources"])

    assert args.debug_comment_sources is True


def test_parse_args_accepts_weekly_reflection_command() -> None:
    args = app_main.parse_args(["--weekly-reflection"])

    assert args.weekly_reflection == ""


def test_main_accepts_weekly_reflection_subcommand(monkeypatch, capsys) -> None:
    monkeypatch.setattr(app_main, "run_pipeline", lambda args: None)

    exit_code = app_main.main(["weekly-reflection"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""


def test_run_pipeline_sync_vocab_comments_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    def fake_sync_vocab_comments(dry_run=False):
        calls["dry_run"] = dry_run
        return type(
            "Result",
            (),
            {
                "scanned_pages": 3,
                "scanned_comments": 4,
                "matched_comments": 2,
                "created": 2,
                "updated": 0,
                "skipped": 0,
                "previews": [{"Name": "leverage", "Meaning": "", "Category": ""}],
            },
        )()

    monkeypatch.setattr(app_main, "sync_vocab_comments", fake_sync_vocab_comments)

    result = app_main.run_pipeline(app_main.parse_args(["--sync-vocab-comments"]))

    assert result is not None
    assert result.kind == "vocab_comment_sync"
    assert result.value == "created=2, updated=0, skipped=0"
    assert calls["dry_run"] is False


def test_run_pipeline_sync_vocab_comments_dry_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    def fake_sync_vocab_comments(dry_run=False):
        calls["dry_run"] = dry_run
        return type(
            "Result",
            (),
            {
                "scanned_pages": 3,
                "scanned_comments": 4,
                "matched_comments": 2,
                "created": 2,
                "updated": 0,
                "skipped": 0,
                "previews": [{"Name": "leverage", "Meaning": "", "Category": ""}],
            },
        )()

    monkeypatch.setattr(app_main, "sync_vocab_comments", fake_sync_vocab_comments)

    result = app_main.run_pipeline(app_main.parse_args(["--sync-vocab-comments", "--dry-run"]))

    assert result is not None
    assert result.kind == "vocab_comment_sync_dry_run"
    assert result.value == "3"
    assert calls["dry_run"] is True


def test_run_pipeline_debug_comments_command(monkeypatch, tmp_path: Path) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "debug_comment_sync", lambda: calls.setdefault("debug", 7) or 7)

    result = app_main.run_pipeline(app_main.parse_args(["--debug-comments"]))

    assert result is not None
    assert result.kind == "debug_comments"
    assert result.value == "7"
    assert calls["debug"] == 7


def test_run_pipeline_debug_page_comments_command(monkeypatch, tmp_path: Path) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "debug_page_comments", lambda: calls.setdefault("debug_page", 5) or 5)

    result = app_main.run_pipeline(app_main.parse_args(["--debug-page-comments"]))

    assert result is not None
    assert result.kind == "debug_page_comments"
    assert result.value == "5"
    assert calls["debug_page"] == 5


def test_run_pipeline_debug_comment_sources_command(monkeypatch, tmp_path: Path) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(app_main, "debug_comment_sources", lambda: calls.setdefault("debug_sources", 9) or 9)

    result = app_main.run_pipeline(app_main.parse_args(["--debug-comment-sources"]))

    assert result is not None
    assert result.kind == "debug_comment_sources"
    assert result.value == "9"
    assert calls["debug_sources"] == 9


def test_run_pipeline_publish_weekly_review_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
    calls = {}

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "load_notion_config",
        lambda: type(
            "Config",
            (),
            {
                "token": "secret",
                "vocabulary_database_id": "vocab_db",
                "weekly_database_id": "weekly_db",
            },
        )(),
    )
    monkeypatch.setattr(
        app_main,
        "create_notion_client",
        lambda token: type("Notion", (), {"pages": type("Pages", (), {})()})(),
    )
    def fake_publish_weekly_review(
        payload,
        notion,
        weekly_database_id,
        vocabulary_database_id=None,
    ):
        calls["publish"] = (payload, weekly_database_id, vocabulary_database_id)
        return type(
            "Result",
            (),
            {"page_id": "weekly_page", "page_url": "https://notion.so/weekly_page"},
        )()

    monkeypatch.setattr(app_main, "publish_weekly_review", fake_publish_weekly_review)

    weekly_json = tmp_path / "weekly.json"
    weekly_json.write_text(
        '{"week":"2026-W29","executive_summary":{"overview":"Overview","takeaway":"Takeaway","highlights":[]},"knowledge_insights":[{"what_happened":"Something happened","why_it_matters":"It matters","my_interpretation":"My view","application":"Apply it"}],"expression_upgrade":[{"expression":"take ownership","meaning":"Accept responsibility","context":"Leadership context","example":"We need to take ownership."}],"vocabulary_memory":[{"word":"leverage","context":"Companies can leverage AI.","meaning":"Use resources effectively","professional_category":"Word","my_usage":"We can leverage AI tools.","review_status":"New"}],"career_reflection":{"questions":["What changed?"],"possible_applications":["Use it in meetings."]},"next_learning_direction":["Review the strongest expressions."]}',
        encoding="utf-8",
    )

    result = app_main.run_pipeline(
        app_main.parse_args(["--publish-weekly-review", str(weekly_json)])
    )

    assert result is not None
    assert result.kind == "weekly_review_page"
    assert result.value == "https://notion.so/weekly_page"
    assert calls["publish"][1] == "weekly_db"
    assert calls["publish"][2] == "vocab_db"
    assert calls["publish"][0].week == "2026-W29"


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
        vocabulary_database_id = "vocab_db"

    class FakeNotion:
        pass

    class FakeWeeklyData:
        week = "2026-W29"
        date = "2026-07-17"
        podcasts = [type("Podcast", (), {"page_id": "podcast_1"})()]

    analysis_json = tmp_path / "weekly_review.json"
    analysis_json.write_text(
        '{"week":"2026-W29","executive_summary":{"overview":"Summary","takeaway":"总结","highlights":["Point"]},"knowledge_insights":[{"what_happened":"Something happened","why_it_matters":"It matters","my_interpretation":"Interpretation","application":"Apply it"}],"expression_upgrade":[{"expression":"take ownership","meaning":"Accept responsibility","context":"Useful","example":"We need to take ownership."}],"vocabulary_memory":[],"career_reflection":{"questions":["What changed?"],"possible_applications":["Use it at work."]},"next_learning_direction":["Plan"]}',
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
            "podcast_summary": {"english": "Summary", "chinese": "总结"},
            "key_topics": ["AI Leadership"],
            "expression_review": [
                {
                    "expression": "take ownership",
                    "category": "Business Phrase",
                    "meaning": "Accept responsibility",
                    "original_context": "Companies need to take ownership.",
                    "learning_note": "Useful",
                    "review_priority": 60,
                }
            ],
            "category_distribution": {"Business Phrase": 1},
            "learning_insights": [
                {
                    "insight": "Reusable language matters",
                    "evidence": "Expressions point to leadership language",
                    "why_it_matters": "It saves time",
                }
            ],
            "next_week_plan": ["Plan"],
            "vocabulary_memory": [],
        },
    )

    from src.agents import weekly_review_agent as weekly_agent

    monkeypatch.setattr(weekly_agent, "load_notion_config", lambda: FakeConfig())
    monkeypatch.setattr(weekly_agent, "create_notion_client", lambda token: FakeNotion())
    monkeypatch.setattr(
        weekly_agent,
        "read_generated_analysis_file",
        lambda path: {
            "week": "2026-W29",
            "podcast_summary": {"english": "Summary", "chinese": "总结"},
            "key_topics": ["AI Leadership"],
            "expression_review": [
                {
                    "expression": "take ownership",
                    "category": "Business Phrase",
                    "meaning": "Accept responsibility",
                    "original_context": "Companies need to take ownership.",
                    "learning_note": "Useful",
                    "review_priority": 60,
                }
            ],
            "category_distribution": {"Business Phrase": 1},
            "learning_insights": [
                {
                    "insight": "Reusable language matters",
                    "evidence": "Expressions point to leadership language",
                    "why_it_matters": "It saves time",
                }
            ],
            "next_week_plan": ["Plan"],
            "vocabulary_memory": [],
        },
    )

    class PublishResult:
        page_id = "weekly_page"
        page_url = "https://notion.so/weekly_page"

    def fake_publish(payload, notion, weekly_database_id, vocabulary_database_id=None):
        calls["payload"] = payload
        calls["weekly_database_id"] = weekly_database_id
        calls["vocabulary_database_id"] = vocabulary_database_id
        return PublishResult()

    monkeypatch.setattr(weekly_agent, "publish_weekly_review", fake_publish)

    args = app_main.parse_args(["--weekly-review", "--weekly-review-json", str(analysis_json)])
    result = app_main.run_pipeline(args)

    assert result is not None
    assert result.kind == "weekly_review_page"
    assert result.value == "https://notion.so/weekly_page"
    assert calls["weekly_database_id"] == "weekly_db"
    assert calls["vocabulary_database_id"] == "vocab_db"
    assert calls["payload"].week == "2026-W29"
    assert calls["payload"].expression_upgrade


def test_run_pipeline_weekly_review_new_cli_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
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

    analysis_json = tmp_path / "weekly_review.json"
    analysis_json.write_text(
        '{"week":"2026-W29","podcast_summary":{"english":"Weekly summary","chinese":"周总结"},"key_topics":["AI Leadership"],"expression_review":[{"expression":"take ownership","category":"Business Phrase","meaning":"Accept responsibility","original_context":"Companies need to take ownership.","learning_note":"Useful.","review_priority":60}],"category_distribution":{"Business Phrase":1},"learning_insights":[{"insight":"Reusable language matters","evidence":"Expressions point to leadership language","why_it_matters":"It saves time"}],"next_week_plan":["Practice the strongest expressions."]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "load_notion_config",
        lambda: type(
            "Config",
            (),
            {
                "token": "secret",
                "vocabulary_database_id": "vocab_db",
                "weekly_database_id": "weekly_db",
                "podcast_database_id": "podcast_db",
                "expression_database_id": "expression_db",
            },
        )(),
    )
    monkeypatch.setattr(
        app_main,
        "create_notion_client",
        lambda token: pytest.fail("Notion should not be called in weekly-review dry-run"),
    )

    result = app_main.run_pipeline(
        app_main.parse_args(["--weekly-review", str(analysis_json), "--dry-run"])
    )

    captured = capsys.readouterr()
    assert result is not None
    assert result.kind == "weekly_review_dry_run"
    assert "Weekly Review dry run" in captured.out
    assert "Total expressions:" in captured.out


def test_run_pipeline_weekly_reflection_command(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
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

    reflection_context = tmp_path / "reflection_context.json"
    weekly_review = tmp_path / "weekly_review.json"
    reflection_context.write_text(
        '{"weekly_theme":{"category":"Negotiation","theme":"Negotiation as relationship management"},"mindset_shifts":[{"before":"A","after":"B","evidence":[{"source":"Podcast summary","supporting_concept":"relationship management"}],"confidence":0.9}],"cross_content_patterns":["Listening before influencing"],"professional_actions":["Pause before replying"]}',
        encoding="utf-8",
    )
    weekly_review.write_text(
        '{"period":{"start_date":"2026-07-13","end_date":"2026-07-20","generated_at":"2026-07-20T12:00:00Z","source":"Podcast Library"},"executive_summary":{"weekly_theme":"Negotiation as relationship management","learning_summary":"Shift","key_takeaways":["Listening first"]},"knowledge_insights":[{"insight":"Insight","why_it_matters":"Matter","professional_application":"Apply"}],"language_growth":{"new_expressions":[{"expression":"challenge assumptions","category":"Business Phrase","learning_value":"Useful"}],"personal_vocabulary":[{"word":"vulnerability","context":"Trust"}]},"career_application":[{"scenario":"Stakeholder Communication","insight":"Listen first","action":"Pause"}],"quality_score":95,"source_page_ids":["page_1"]}',
        encoding="utf-8",
    )

    class FakeConfig:
        token = "secret"
        podcast_database_id = "podcast_db"
        weekly_database_id = "weekly_reflection_db"

    class FakePublishResult:
        page_id = "reflection_page"
        page_url = "https://notion.so/reflection_page"

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "run_weekly_reflection_pipeline",
        lambda weekly_learning_context_path, notion=None, weekly_reflection_database_id=None, podcast_database_id=None, dry_run=False: type(
            "Result",
            (),
            {
                "weekly_learning_context_path": weekly_review,
                "reflection_context_path": reflection_context,
                "weekly_review_path": weekly_review,
                "quality_report": {"passed": True, "score": 95, "issues": [], "suggestions": []},
                "publish_result": FakePublishResult(),
                "weekly_learning_context": {},
                "reflection_context": {"weekly_theme": {"category": "Negotiation", "theme": "Negotiation as relationship management"}},
                "weekly_review": {},
            },
        )(),
    )

    result = app_main.run_pipeline(app_main.parse_args(["--weekly-reflection"]))

    captured = capsys.readouterr()
    assert result is not None
    assert result.kind == "weekly_reflection_page"
    assert "Weekly Reflection Pipeline" in captured.out
    assert "ReflectionContext:" in captured.out
    assert "Quality Gate:" in captured.out


def test_run_pipeline_weekly_reflection_dry_run(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
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

    class FakePublishResult:
        page_id = ""
        page_url = None

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "run_weekly_reflection_pipeline",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "weekly_learning_context_path": tmp_path / "weekly_learning_context.json",
                "reflection_context_path": tmp_path / "reflection_context.json",
                "weekly_review_path": tmp_path / "weekly_review.json",
                "quality_report": {"passed": True, "score": 95, "issues": [], "suggestions": []},
                "publish_result": None,
                "weekly_learning_context": {},
                "reflection_context": {"weekly_theme": {"category": "Negotiation", "theme": "Negotiation as relationship management"}},
                "weekly_review": {},
                "pipeline_run_path": tmp_path / "pipeline_run.json",
                "log_path": tmp_path / "logs" / "weekly_reflection.log",
                "dry_run": True,
            },
        )(),
    )

    result = app_main.main(["--weekly-reflection", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Notion skipped (dry run)" in captured.out
    assert "Weekly Reflection Dry Run:" in captured.out


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


def test_existing_transcript_without_analysis_creates_codex_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript_json = tmp_path / "transcript.json"
    transcript_json.write_text(
        '{"segments":[{"start":0,"end":1,"text":"Existing transcript"}],"language":"en"}',
        encoding="utf-8",
    )
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

    result = app_main.run_pipeline(
        app_main.parse_args(
            [
                "https://youtu.be/abc",
                "--title",
                "Existing Episode",
                "--transcript-json",
                str(transcript_json),
            ]
        )
    )

    assert result is not None
    assert result.kind == "analysis_request"
    request_path = Path(result.value)
    assert request_path.exists()
    assert "Existing transcript" in request_path.read_text(encoding="utf-8")


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
