"""Quality gate for the curated Weekly Reflection product contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


LEAKAGE_PATTERNS = (
    r"\bthis episode (discusses|explains|talks about)\b",
    r"\bthe podcast (discusses|explains)\b",
    r"\bthe guest talks about\b",
    r"\bin this episode\b",
)
GENERIC_ACTIONS = (
    "practice these expressions",
    "use this in work",
    "review the vocabulary",
    "apply the idea",
    "use the learning",
)


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: object) -> str:
    return _text(value).lower()


@dataclass(frozen=True)
class WeeklyReviewQualityReport:
    passed: bool
    score: int
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "issues": list(self.issues),
            "suggestions": list(self.suggestions),
        }


def _legacy_issues(review: Mapping[str, Any]) -> list[str]:
    if "core_idea" in review:
        return []
    return ["Weekly Review uses the legacy aggregation contract instead of the curated reflection contract."]


def _summary_leakage(review: Mapping[str, Any]) -> list[str]:
    core = review.get("core_idea", {})
    text = " ".join(_text(core.get(key, "")) for key in ("idea", "why_it_matters", "refined_understanding")) if isinstance(core, Mapping) else ""
    if any(re.search(pattern, text.lower()) for pattern in LEAKAGE_PATTERNS):
        return ["Core idea is an episode summary rather than a transferable reflection."]
    return []


def _curation_issues(review: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    ideas = review.get("ideas_worth_compounding", [])
    expressions = review.get("expressions_worth_reusing", [])
    if not isinstance(ideas, list) or not 2 <= len(ideas) <= 4:
        issues.append("Ideas worth compounding must contain 2-4 curated ideas.")
    if not isinstance(expressions, list) or not 3 <= len(expressions) <= 5:
        issues.append("Expressions worth reusing must contain 3-5 curated expressions.")
    if isinstance(expressions, list) and len(expressions) > 5:
        issues.append("Weekly Reflection aggregates too many expressions.")
    if isinstance(expressions, list):
        for item in expressions:
            if not isinstance(item, Mapping):
                continue
            expression = _text(item.get("expression"))
            function = _normalized(item.get("communication_function"))
            if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}", expression) and not any(
                marker in function for marker in ("term", "name", "industry")
            ):
                issues.append(f"Proper name selected as a language asset without justification: {expression}.")
    if review.get("personal_vocabulary") or (
        isinstance(review.get("language_growth"), Mapping)
        and review.get("language_growth", {}).get("personal_vocabulary")
    ):
        issues.append("Weekly Reflection must not reproduce the weekly vocabulary collection.")
    return issues


def _mindset_issues(review: Mapping[str, Any]) -> list[str]:
    shift = review.get("mindset_shift")
    if shift is None:
        return []
    if not isinstance(shift, Mapping):
        return ["Mindset shift must be an object or null."]
    if not _text(shift.get("before")) or not _text(shift.get("now")):
        return ["Mindset shift is unsupported because before/now evidence is incomplete."]
    return []


def _application_issues(review: Mapping[str, Any]) -> list[str]:
    application = review.get("next_week_application")
    if not isinstance(application, Mapping):
        return ["Exactly one next-week application is required."]
    issues: list[str] = []
    for field_name in ("scenario", "behavior", "phrase_to_use", "completion_condition"):
        if not _text(application.get(field_name)):
            issues.append(f"Next-week application is missing {field_name}.")
    combined = _normalized(" ".join(_text(application.get(key)) for key in application))
    if any(marker in combined for marker in GENERIC_ACTIONS):
        issues.append("Next-week application is generic rather than concrete and observable.")
    if isinstance(review.get("career_application"), list) and len(review.get("career_application", [])) > 1:
        issues.append("More than one next-week application was generated.")
    return issues


def _connection_issues(review: Mapping[str, Any]) -> list[str]:
    connection = _text(review.get("language_thinking_connection"))
    if len(connection) < 40:
        return ["Language-thinking connection is missing or too thin."]
    return []


def _source_scope_issues(review: Mapping[str, Any]) -> list[str]:
    source_ids = [item for item in review.get("source_page_ids", []) if _text(item)]
    if len(source_ids) > 1:
        return []
    serialized = _normalized(review)
    if any(marker in serialized for marker in ("across podcasts", "multiple podcasts", "across episodes")):
        return ["Single-source learning is incorrectly presented as a cross-content pattern."]
    return []


def _duplication_issues(review: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    core = review.get("core_idea", {})
    if isinstance(core, Mapping):
        values.append(_normalized(core.get("idea")))
    for item in review.get("ideas_worth_compounding", []):
        if isinstance(item, Mapping):
            values.append(_normalized(item.get("idea")))
    values = [value for value in values if value]
    if len(values) != len(set(values)):
        return ["The same idea is repeated across multiple sections."]
    return []


def _formatting_issues(review: Mapping[str, Any]) -> list[str]:
    serialized = json.dumps(review, ensure_ascii=False)
    issues: list[str] = []
    if "\\n" in serialized or "{'" in serialized:
        issues.append("Raw dictionary or escaped formatting appears in user-facing content.")
    lowered = serialized.lower()
    if any(marker in lowered for marker in ("pipeline_run", "reflection_context_id", "confidence score")):
        issues.append("Pipeline or debug content appears in the user-facing review.")
    return issues


def check_weekly_review_quality(review: Mapping[str, Any]) -> WeeklyReviewQualityReport:
    issues: list[str] = []
    issues.extend(_legacy_issues(review))
    if not issues:
        issues.extend(_summary_leakage(review))
        issues.extend(_curation_issues(review))
        issues.extend(_mindset_issues(review))
        issues.extend(_application_issues(review))
        issues.extend(_connection_issues(review))
        issues.extend(_source_scope_issues(review))
        issues.extend(_duplication_issues(review))
        issues.extend(_formatting_issues(review))

    suggestions = []
    for issue in issues:
        if "legacy aggregation" in issue:
            suggestions.append("Generate the curated Weekly Reflection artifact before publishing.")
        elif "expressions" in issue.lower():
            suggestions.append("Select only 3-5 natural, reusable professional expressions.")
        elif "application" in issue.lower():
            suggestions.append("Define one scenario, behavior, phrase, and observable completion condition.")
        elif "connection" in issue.lower():
            suggestions.append("Explain how a selected expression changes thinking or communication precision.")
        elif "summary" in issue.lower():
            suggestions.append("Rewrite the core idea as a transferable change in understanding.")

    score = max(0, 100 - len(issues) * 15)
    return WeeklyReviewQualityReport(
        passed=not issues and score >= 85,
        score=score,
        issues=issues,
        suggestions=list(dict.fromkeys(suggestions)),
    )
