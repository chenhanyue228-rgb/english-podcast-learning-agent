from __future__ import annotations

from pathlib import Path


def test_weekly_extraction_script_calls_pipeline(monkeypatch, capsys, tmp_path: Path) -> None:
    import scripts.test_weekly_extraction as script

    called = {}

    def fake_run_weekly_learning_extraction(output_path):
        called["output_path"] = output_path
        return (
            {
                "metadata": {},
                "podcasts": [{}],
                "learning_expressions": [{}],
                "ai_highlights": [{}],
                "user_vocabulary": [{}],
            },
            type(
                "Report",
                (),
                {
                    "to_dict": lambda self: {
                        "podcast_pages_scanned": 1,
                        "successfully_extracted": 1,
                        "expressions_found": 1,
                        "ai_highlights_found": 1,
                        "pink_highlights_found": 1,
                        "failures": 0,
                    }
                },
            )(),
            tmp_path / "weekly_learning_context.json",
        )

    monkeypatch.setattr(script, "run_weekly_learning_extraction", fake_run_weekly_learning_extraction)

    exit_code = script.main(["--output", str(tmp_path / "weekly_learning_context.json")])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["output_path"] == tmp_path / "weekly_learning_context.json"
    assert "Podcast count: 1" in output
    assert "Saved JSON:" in output
