from __future__ import annotations

from copy import deepcopy

from src.weekly_review.quality_checker import check_weekly_review_quality


def good_review() -> dict:
    return {
        "period": {"start_date": "2026-07-13", "end_date": "2026-07-20", "generated_at": "2026-07-20T12:00:00Z", "source": "Podcast Library"},
        "core_idea": {
            "idea": "Disagreement improves when the problem, not the person, becomes the shared object of attention.",
            "why_it_matters": "It changes conflict from positional defense into collaborative inquiry.",
            "refined_understanding": "Negotiation is relationship management supported by precise framing.",
        },
        "mindset_shift": {"before": "I treated negotiation as winning.", "now": "I now treat it as joint problem solving."},
        "ideas_worth_compounding": [
            {"idea": "Listening reveals the problem behind a stated position.", "why_it_matters": "It prevents solving the wrong problem.", "application": "Ask one clarifying question before proposing a solution.", "source_reference": "Negotiation podcast"},
            {"idea": "Framing determines whether disagreement feels adversarial or shared.", "why_it_matters": "People collaborate more readily around a shared object.", "application": "Name the shared outcome at the start of a difficult discussion.", "source_reference": "Communication podcast"},
        ],
        "expressions_worth_reusing": [
            {"expression": "challenge assumptions", "contextual_meaning": "Test beliefs without attacking people.", "reusable_example": "Let's challenge our assumptions before choosing a direction.", "communication_function": "Constructive disagreement"},
            {"expression": "joint problem solving", "contextual_meaning": "Treat both sides as collaborators.", "reusable_example": "Let's approach this as joint problem solving.", "communication_function": "Collaborative framing"},
            {"expression": "building long-term relationships", "contextual_meaning": "Prioritize durable trust over immediate gain.", "reusable_example": "The decision should support building long-term relationships.", "communication_function": "Long-term orientation"},
        ],
        "language_thinking_connection": "The phrase 'joint problem solving' supplies a mental frame in which the other person is a collaborator and the problem becomes the shared object of attention.",
        "next_week_application": {"scenario": "A stakeholder challenges the launch sequence.", "behavior": "Restate the shared outcome before discussing constraints.", "phrase_to_use": "Let's treat this as joint problem solving.", "completion_condition": "Use the phrase once and record whether positions turn into options."},
        "sources": [{"page_id": "page_1", "title": "Negotiation", "url": "https://example.com"}],
        "source_page_ids": ["page_1"],
    }


def test_good_reflection_passes() -> None:
    report = check_weekly_review_quality(good_review())
    assert report.passed is True
    assert report.score == 100


def test_podcast_summary_fails() -> None:
    review = deepcopy(good_review())
    review["core_idea"]["idea"] = "This episode discusses negotiation."
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("episode summary" in issue for issue in report.issues)


def test_more_than_five_expressions_fails() -> None:
    review = deepcopy(good_review())
    review["expressions_worth_reusing"] *= 2
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("too many expressions" in issue for issue in report.issues)


def test_missing_language_thinking_connection_fails() -> None:
    review = deepcopy(good_review())
    review["language_thinking_connection"] = "Useful."
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("Language-thinking connection" in issue for issue in report.issues)


def test_generic_or_multiple_application_fails() -> None:
    review = deepcopy(good_review())
    review["next_week_application"]["behavior"] = "Practice these expressions."
    review["career_application"] = [{}, {}]
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("generic" in issue.lower() for issue in report.issues)
    assert any("More than one" in issue for issue in report.issues)


def test_repeated_idea_fails() -> None:
    review = deepcopy(good_review())
    review["ideas_worth_compounding"][0]["idea"] = review["core_idea"]["idea"]
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("same idea" in issue for issue in report.issues)


def test_weekly_vocabulary_dump_fails() -> None:
    review = deepcopy(good_review())
    review["personal_vocabulary"] = [{"word": "leverage"}]
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("vocabulary collection" in issue for issue in report.issues)


def test_unjustified_proper_name_expression_fails() -> None:
    review = deepcopy(good_review())
    review["expressions_worth_reusing"][0]["expression"] = "Stan Christensen"
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("Proper name" in issue for issue in report.issues)


def test_single_source_cross_content_claim_fails() -> None:
    review = deepcopy(good_review())
    review["core_idea"]["refined_understanding"] = "This pattern appears across podcasts."
    report = check_weekly_review_quality(review)
    assert report.passed is False
    assert any("Single-source" in issue for issue in report.issues)
