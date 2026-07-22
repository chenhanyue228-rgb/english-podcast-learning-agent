"""Deterministic placeholder provider for weekly review generation."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from src.weekly_review.provider import WeeklyReviewGenerationProvider


def _compact_sources(podcasts: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in podcasts:
        page_id = str(item.get("page_id", "")).strip()
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if not page_id or not title or title.lower().startswith(("unresolved ", "id")):
            continue
        identity = url or page_id
        if identity in seen:
            continue
        seen.add(identity)
        sources.append({"page_id": page_id, "title": title, "url": url})
        if len(sources) == 5:
            break
    return sources


class PlaceholderWeeklyReviewGenerationProvider(WeeklyReviewGenerationProvider):
    """Build a simple weekly review without calling external services."""

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        reflection_context = context.get("reflection_context", {})
        if not isinstance(reflection_context, Mapping):
            reflection_context = {}

        weekly_context = context.get("weekly_learning_context", {})
        if not isinstance(weekly_context, Mapping):
            weekly_context = {}

        metadata = weekly_context.get("metadata", {})
        podcasts = weekly_context.get("podcasts", [])
        expressions = weekly_context.get("learning_expressions", [])
        vocab = weekly_context.get("user_vocabulary", [])

        podcast_list = [item for item in podcasts if isinstance(item, Mapping)]
        expression_list = [item for item in expressions if isinstance(item, Mapping)]
        vocab_list = [item for item in vocab if isinstance(item, Mapping)]

        weekly_theme_value = reflection_context.get("weekly_theme", {})
        weekly_theme = ""
        weekly_category = ""
        if isinstance(weekly_theme_value, Mapping):
            weekly_theme = str(weekly_theme_value.get("theme", "")).strip()
            weekly_category = str(weekly_theme_value.get("category", "")).strip()
        else:
            weekly_theme = str(weekly_theme_value).strip()
        if not weekly_theme:
            topics = [
                str(item.get("topic", "")).strip()
                for item in podcast_list
                if str(item.get("topic", "")).strip()
            ]
            topic_counts = Counter(topics)
            weekly_theme = topic_counts.most_common(1)[0][0] if topic_counts else "Weekly learning reflection"
        if not weekly_category:
            weekly_category = weekly_theme

        mindset_shifts = [
            item
            for item in reflection_context.get("mindset_shifts", [])
            if isinstance(item, Mapping)
        ]
        cross_content_patterns = [
            str(item).strip()
            for item in reflection_context.get("cross_content_patterns", [])
            if str(item).strip()
        ]
        professional_actions = [
            str(item).strip()
            for item in reflection_context.get("professional_actions", [])
            if str(item).strip()
        ]

        key_takeaways: list[str] = []
        for shift in mindset_shifts:
            after = str(shift.get("after", "")).strip()
            before = str(shift.get("before", "")).strip()
            if after and after not in key_takeaways:
                key_takeaways.append(after)
            elif before and before not in key_takeaways:
                key_takeaways.append(before)
        for item in cross_content_patterns:
            if item not in key_takeaways:
                key_takeaways.append(item)
        if not key_takeaways:
            key_takeaways = ["Review the strongest learning signals from the week."]

        knowledge_insights = []
        for shift in mindset_shifts[:3]:
            before = str(shift.get("before", "")).strip()
            after = str(shift.get("after", "")).strip()
            evidence = shift.get("evidence", [])
            evidence_text = ""
            if isinstance(evidence, list):
                evidence_parts = []
                for item in evidence:
                    if isinstance(item, Mapping):
                        source = str(item.get("source", "")).strip()
                        concept = str(item.get("supporting_concept", "")).strip()
                        text = ": ".join(part for part in (source, concept) if part)
                    else:
                        text = str(item).strip()
                    if text:
                        evidence_parts.append(text)
                evidence_text = " ".join(evidence_parts)
            insight = after or before or "The week produced a useful professional insight."
            why_it_matters = (
                evidence_text
                or "This matters because it changes how I approach professional communication."
            )
            application = (
                professional_actions[0]
                if professional_actions
                else "Apply the idea in meetings, updates, or written communication."
            )
            knowledge_insights.append(
                {
                    "insight": insight,
                    "why_it_matters": why_it_matters,
                    "professional_application": application,
                }
            )
        if len(podcast_list) > 1:
            for pattern in cross_content_patterns[:1]:
                knowledge_insights.append(
                    {
                        "insight": pattern,
                        "why_it_matters": "This matters because it is a pattern that transfers across podcasts and work situations.",
                        "professional_application": professional_actions[1]
                        if len(professional_actions) > 1
                        else "Use the pattern in real work communication.",
                    }
                )

        if not knowledge_insights:
            knowledge_insights.append(
                {
                    "insight": "The week produced a useful professional reflection.",
                    "why_it_matters": "It shows which communication habits are worth keeping.",
                    "professional_application": "Use the strongest idea in real work communication.",
                }
            )

        expressions_output = []
        for item in expression_list[:5]:
            expression = str(item.get("expression", "")).strip()
            if not expression:
                continue
            expressions_output.append(
                {
                    "expression": expression,
                    "category": str(item.get("category", "")).strip(),
                    "learning_value": str(item.get("meaning", "")).strip()
                    or str(item.get("usage_context", "")).strip()
                    or "Useful professional expression.",
                    "professional_usage": str(item.get("usage_context", "")).strip()
                    or str(item.get("example", "")).strip()
                    or "Use it in a work conversation.",
                }
            )

        vocabulary_output = []
        for item in vocab_list[:5]:
            word = str(item.get("word", "")).strip()
            if not word:
                continue
            vocabulary_output.append(
                {
                    "word": word,
                    "context": str(item.get("context", "")).strip(),
                    "professional_relevance": str(item.get("professional_relevance", "")).strip()
                    or str(item.get("meaning", "")).strip()
                    or "Worth noticing for work communication.",
                }
            )

        career_application = []
        career_scenarios = [
            "Stakeholder Communication",
            "Negotiation",
            "Leadership",
        ]
        for index, insight in enumerate(knowledge_insights[:3], start=1):
            career_application.append(
                {
                    "scenario": career_scenarios[index - 1] if index - 1 < len(career_scenarios) else f"Scenario {index}",
                    "application": str(insight.get("professional_application", "")).strip()
                    or "Use the learning in a work conversation.",
                }
            )
        if not career_application:
            career_application.append(
                {
                    "scenario": "General work communication",
                    "application": "Apply the week's strongest idea in daily work communication.",
                }
            )

        source_page_ids = [
            str(item.get("page_id", "")).strip()
            for item in podcast_list
            if str(item.get("page_id", "")).strip()
        ]
        first_insight = knowledge_insights[0] if knowledge_insights else {}
        first_shift = mindset_shifts[0] if mindset_shifts else None
        priority_terms = (
            "joint problem solving",
            "question your assumptions",
            "challenge assumptions",
            "relationship management",
            "take ownership",
            "long-term relationships",
            "drilling down",
            "fixed pie",
        )

        def expression_score(item: Mapping[str, Any]) -> tuple[int, int]:
            expression = str(item.get("expression", "")).strip().lower()
            priority = next(
                (len(priority_terms) - index for index, term in enumerate(priority_terms) if term in expression),
                0,
            )
            commonness = 2 if str(item.get("commonness", "")).strip().lower() == "high" else 0
            phrase_fit = 1 if 2 <= len(expression.split()) <= 5 else 0
            return priority + commonness + phrase_fit, -len(expression)

        selected_expressions = []
        for item in sorted(expression_list, key=expression_score, reverse=True):
            expression = str(item.get("expression", "")).strip()
            if not expression or any(existing["expression"].lower() == expression.lower() for existing in selected_expressions):
                continue
            selected_expressions.append(
                {
                    "expression": expression,
                    "contextual_meaning": str(item.get("meaning", "")).strip()
                    or str(item.get("usage_context", "")).strip(),
                    "reusable_example": str(item.get("example", "")).strip(),
                    "communication_function": str(item.get("usage_context", "")).strip()
                    or "Use this to communicate the week's central idea more precisely.",
                }
            )
            if len(selected_expressions) == 5:
                break

        primary_expression = selected_expressions[0]["expression"] if selected_expressions else ""
        action_text = professional_actions[0] if professional_actions else "Use the core idea in one stakeholder conversation."
        if "negotiat" in weekly_theme.lower():
            core_idea_text = "Disagreement becomes more productive when both sides treat the problem, rather than each other, as the object of attention."
            core_why = "This reframing protects the relationship while making hidden interests and workable options easier to surface."
            refined_understanding = "I now see negotiation as relationship management supported by listening, careful framing, and joint problem solving."
        else:
            core_idea_text = str(first_insight.get("insight", "")).strip() or weekly_theme
            core_why = "It offers a reusable way to improve professional judgment and communication."
            refined_understanding = (
                str(first_shift.get("after", "")).strip()
                if isinstance(first_shift, Mapping)
                else core_idea_text
            )
        compounding_ideas = []
        if "negotiat" in weekly_theme.lower():
            compounding_ideas = [
                {
                    "idea": "Listening is a diagnostic tool, not just a courtesy.",
                    "why_it_matters": "Positions often conceal the concern that actually needs to be solved.",
                    "application": "Ask one clarifying question before defending a proposal.",
                    "source_reference": "Negotiation and communication sources",
                },
                {
                    "idea": "Framing determines whether disagreement feels adversarial or collaborative.",
                    "why_it_matters": "A shared frame lowers defensiveness and makes options easier to discuss.",
                    "application": "Name the shared outcome before comparing constraints.",
                    "source_reference": "Negotiation sources",
                },
                {
                    "idea": "An agreement has little value without a credible path to implementation.",
                    "why_it_matters": "The quality of follow-through is part of the negotiation outcome.",
                    "application": "End a decision with ownership, timing, and a next checkpoint.",
                    "source_reference": "Negotiation sources",
                },
            ]
        else:
            for item in knowledge_insights[1:]:
                idea = str(item.get("insight", "")).strip()
                if not idea or idea.lower() == core_idea_text.lower():
                    continue
                compounding_ideas.append(
                    {
                        "idea": idea,
                        "why_it_matters": str(item.get("why_it_matters", "")).strip(),
                        "application": str(item.get("professional_application", "")).strip(),
                        "source_reference": "Weekly podcast learning",
                    }
                )
        for takeaway in key_takeaways:
            if len(compounding_ideas) >= 2:
                break
            if not takeaway or takeaway.lower() == core_idea_text.lower():
                continue
            compounding_ideas.append(
                {
                    "idea": takeaway,
                    "why_it_matters": "It is a compact principle worth retaining beyond the original source.",
                    "application": action_text,
                    "source_reference": "Weekly podcast learning",
                }
            )
        return {
            "period": {
                "start_date": str(metadata.get("period_start", "")),
                "end_date": str(metadata.get("period_end", "")),
                "generated_at": str(metadata.get("generated_at", "")),
                "source": str(metadata.get("source", "Podcast Library")),
            },
            "core_idea": {
                "idea": core_idea_text,
                "why_it_matters": core_why,
                "refined_understanding": refined_understanding,
            },
            "mindset_shift": {
                "before": str(first_shift.get("before", "")).strip(),
                "now": str(first_shift.get("after", "")).strip(),
            } if isinstance(first_shift, Mapping) and first_shift.get("before") and first_shift.get("after") else None,
            "ideas_worth_compounding": compounding_ideas[:4],
            "expressions_worth_reusing": selected_expressions[:5],
            "language_thinking_connection": (
                f"The expression '{primary_expression}' gives the week's core idea a reusable verbal frame, "
                "making it easier to carry the idea into a real professional conversation."
                if primary_expression
                else "The selected language provides a more precise frame for applying the week's core idea."
            ),
            "next_week_application": {
                "scenario": "A stakeholder challenges a proposed direction or constraint",
                "behavior": "Restate the shared outcome before comparing positions or proposing solutions.",
                "phrase_to_use": f"Let's approach this as {primary_expression}." if primary_expression else "Let's clarify the shared outcome before we compare options.",
                "completion_condition": "Use the phrase once and note whether the discussion moves from positions to options.",
            },
            "sources": _compact_sources(podcast_list),
            "source_page_ids": source_page_ids,
            "source_podcast_ids": source_page_ids,
        }
