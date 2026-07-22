"""Generate and validate a Markdown preview for weekly review analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


class WeeklyReviewPreviewError(RuntimeError):
    """Raised when a weekly review preview cannot be generated."""


DEFAULT_ANALYSIS_DIR = Path("data/analysis")
DEFAULT_PREVIEW_DIR = Path("data/previews")

_BASIC_WORDS = {
    "good",
    "great",
    "important",
    "useful",
    "helpful",
    "nice",
    "basic",
    "simple",
    "learn",
    "learning",
    "practice",
    "review",
    "summary",
}


@dataclass(frozen=True)
class WeeklyReviewPreviewIssue:
    severity: str
    message: str


@dataclass(frozen=True)
class WeeklyReviewPreviewValidationResult:
    issues: list[WeeklyReviewPreviewIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


def load_weekly_review_analysis(path: Path) -> Mapping[str, Any]:
    """Load a weekly review analysis JSON document."""
    if not path.exists():
        raise WeeklyReviewPreviewError(f"Weekly review analysis does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WeeklyReviewPreviewError(
            f"Weekly review analysis is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise WeeklyReviewPreviewError("Weekly review analysis must be a JSON object.")
    return payload


def _as_lines(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        lines: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                parts = []
                for key in ("insight", "evidence", "why_it_matters", "what_happened", "my_interpretation", "application"):
                    text = str(item.get(key, "")).strip()
                    if text:
                        parts.append(text)
                text = " | ".join(parts)
            else:
                text = str(item).strip()
            if text:
                lines.append(text)
        return lines
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _analysis_key(analysis: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = analysis.get(name)
        if value is not None:
            return value
    return None


def _format_bullets(items: Sequence[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None"]


def _format_expression_upgrade(expression_upgrade: Sequence[Mapping[str, Any]]) -> list[str]:
    if not expression_upgrade:
        return ["- No expressions were highlighted for review this week."]

    lines: list[str] = []
    for item in expression_upgrade:
        expression = str(item.get("expression", "")).strip() or "(empty expression)"
        meaning = str(item.get("meaning", "")).strip()
        context = str(item.get("context", "")).strip()
        example = str(item.get("example", "")).strip()
        parts = [expression]
        if meaning:
            parts.append(f"Meaning: {meaning}")
        if context:
            parts.append(f"Context: {context}")
        if example:
            parts.append(f"Example: {example}")
        lines.append(f"- {' '.join(parts)}")
    return lines


def _format_knowledge_insights(knowledge_insights: Sequence[Mapping[str, Any]]) -> list[str]:
    if not knowledge_insights:
        return ["- No knowledge insights provided."]

    lines: list[str] = []
    for item in knowledge_insights:
        what_happened = str(item.get("what_happened", "")).strip()
        why_it_matters = str(item.get("why_it_matters", "")).strip()
        my_interpretation = str(item.get("my_interpretation", "")).strip()
        application = str(item.get("application", "")).strip()
        parts = []
        if what_happened:
            parts.append(f"What happened: {what_happened}")
        if why_it_matters:
            parts.append(f"Why it matters: {why_it_matters}")
        if my_interpretation:
            parts.append(f"My interpretation: {my_interpretation}")
        if application:
            parts.append(f"Application: {application}")
        lines.append(f"- {' | '.join(parts)}")
    return lines


def _format_executive_summary(executive_summary: Mapping[str, Any]) -> list[str]:
    overview = str(executive_summary.get("overview", "")).strip()
    takeaway = str(executive_summary.get("takeaway", "")).strip()
    highlights = _as_lines(executive_summary.get("highlights", []))
    lines: list[str] = []
    lines.append(f"- Overview: {overview}" if overview else "- Overview: Not provided.")
    lines.append(f"- Takeaway: {takeaway}" if takeaway else "- Takeaway: Not provided.")
    if highlights:
        lines.append("- Highlights:")
        lines.extend([f"  - {item}" for item in highlights])
    return lines


def _format_career_reflection(career_reflection: Mapping[str, Any]) -> list[str]:
    questions = _as_lines(career_reflection.get("questions", []))
    possible_applications = _as_lines(career_reflection.get("possible_applications", []))
    lines: list[str] = []
    if questions:
        lines.append("- Questions:")
        lines.extend([f"  - {item}" for item in questions])
    if possible_applications:
        lines.append("- Possible applications:")
        lines.extend([f"  - {item}" for item in possible_applications])
    return lines or ["- No career reflection provided."]


def _find_basic_words(items: Sequence[Mapping[str, Any]]) -> bool:
    for item in items:
        expression = str(item.get("expression", "")).strip().lower()
        meaning = str(item.get("meaning", "")).strip().lower()
        context = str(item.get("context", "")).strip().lower()
        if not expression:
            continue
        if expression in _BASIC_WORDS and (not meaning or meaning in _BASIC_WORDS):
            return True
        if expression in {"good", "nice", "important", "learn", "review"}:
            return True
        if context and all(word in _BASIC_WORDS for word in expression.split() if word):
            return True
    return False


def validate_weekly_review_preview(analysis: Mapping[str, Any]) -> WeeklyReviewPreviewValidationResult:
    """Return blocking and non-blocking preview quality issues."""
    issues: list[WeeklyReviewPreviewIssue] = []

    knowledge_insights = _analysis_key(analysis, "knowledge_insights", "learning_insights")
    if not isinstance(knowledge_insights, Sequence) or isinstance(knowledge_insights, (str, bytes)):
        knowledge_insights = []
    if not knowledge_insights:
        issues.append(
            WeeklyReviewPreviewIssue(
                severity="error",
                message="Knowledge Insights are empty.",
            )
        )
    else:
        if all(
            isinstance(item, Mapping) and not str(item.get("my_interpretation", "")).strip()
            for item in knowledge_insights
        ):
            issues.append(
                WeeklyReviewPreviewIssue(
                    severity="error",
                    message="Output looks like content summary only and is missing personal interpretation.",
                )
            )

    expression_upgrade = _analysis_key(analysis, "expression_upgrade", "expression_review")
    if not isinstance(expression_upgrade, Sequence) or isinstance(expression_upgrade, (str, bytes)):
        expression_upgrade = []
    if expression_upgrade and _find_basic_words(expression_upgrade):
        issues.append(
            WeeklyReviewPreviewIssue(
                severity="warning",
                message="Expression Upgrade contains only basic words or low-value expressions.",
            )
        )

    career_reflection = _analysis_key(analysis, "career_reflection", {})
    if not isinstance(career_reflection, Mapping):
        career_reflection = {}
    if not career_reflection or not _as_lines(career_reflection.get("questions", [])):
        issues.append(
            WeeklyReviewPreviewIssue(
                severity="error",
                message="Career Reflection is missing.",
            )
        )

    return WeeklyReviewPreviewValidationResult(issues=issues)


def build_weekly_review_preview(analysis: Mapping[str, Any]) -> str:
    """Convert a weekly review analysis payload into readable Markdown."""
    week = str(analysis.get("week", "")).strip() or "Weekly Review"
    executive_summary = _analysis_key(analysis, "executive_summary", "podcast_summary")
    if not isinstance(executive_summary, Mapping):
        executive_summary = {}

    knowledge_insights = _analysis_key(analysis, "knowledge_insights", "learning_insights")
    if not isinstance(knowledge_insights, Sequence) or isinstance(knowledge_insights, (str, bytes)):
        knowledge_insights = []

    expression_upgrade = _analysis_key(analysis, "expression_upgrade", "expression_review")
    if not isinstance(expression_upgrade, Sequence) or isinstance(expression_upgrade, (str, bytes)):
        expression_upgrade = []

    vocabulary_memory = analysis.get("vocabulary_memory", [])
    if not isinstance(vocabulary_memory, Sequence) or isinstance(vocabulary_memory, (str, bytes)):
        vocabulary_memory = []

    career_reflection = _analysis_key(analysis, "career_reflection", {})
    if not isinstance(career_reflection, Mapping):
        career_reflection = {}

    next_learning_direction = _analysis_key(
        analysis,
        "next_learning_direction",
        "next_week_plan",
    )
    if not isinstance(next_learning_direction, Sequence) or isinstance(next_learning_direction, (str, bytes)):
        next_learning_direction = []

    lines = [
        "# Executive Summary",
        "",
        f"**Week:** {week}",
        "",
    ]
    lines.extend(_format_executive_summary(executive_summary))
    lines.extend(
        [
            "",
            "# Knowledge Insights",
            "",
            *_format_knowledge_insights(knowledge_insights),
            "",
            "# Expression Upgrade",
            "",
            *_format_expression_upgrade(expression_upgrade),
            "",
            "# Vocabulary Memory",
            "",
            *(
                _format_bullets([json.dumps(item, ensure_ascii=False) for item in vocabulary_memory])
                if vocabulary_memory
                else ["- No vocabulary memory items provided."]
            ),
            "",
            "# Career Reflection",
            "",
            *_format_career_reflection(career_reflection),
            "",
            "# Next Learning Direction",
            "",
            *(
                _format_bullets([str(item) for item in next_learning_direction])
                if next_learning_direction
                else ["- No next learning direction provided."]
            ),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_weekly_review_preview(
    analysis_path: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """Read an analysis JSON file and write a Markdown preview."""
    analysis = load_weekly_review_analysis(analysis_path)
    markdown = build_weekly_review_preview(analysis)
    week = str(analysis.get("week", "")).strip()
    target_path = output_path or (DEFAULT_PREVIEW_DIR / f"{week}_weekly_review_preview.md")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(markdown, encoding="utf-8")
    return target_path.resolve()
