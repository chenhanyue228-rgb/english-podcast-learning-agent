"""Canonical Notion workspace schema for the learning agent.

Keep database properties lean. Database fields are for filtering, relations,
review status, and weekly statistics; long learning content belongs in page
body blocks.
"""

from __future__ import annotations


PODCAST_LIBRARY = "Podcast Library"
EXPRESSION_DATABASE = "Expression Database"
WEEKLY_REVIEW = "Weekly Review"
VOCABULARY_DATABASE = "Vocabulary Database"

WORKSPACE_DATABASE_ORDER = (
    PODCAST_LIBRARY,
    EXPRESSION_DATABASE,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
)

SOURCE_TYPES = ["YouTube", "Podcast", "Local Audio"]
EXPRESSION_CATEGORIES = [
    "Native Expression",
    "Business Phrase",
    "Industry Term",
    "Collocation",
    "Sentence Pattern",
]
REVIEW_STATUSES = ["New", "Reviewing", "Mastered"]
COMMONNESS_LEVELS = ["High", "Medium", "Low"]

CATEGORY_COLORS = {
    "Native Expression": "Green",
    "Business Phrase": "Blue",
    "Industry Term": "Yellow",
    "Collocation": "Purple",
    "Sentence Pattern": "Orange",
}

EXPRESSION_CATEGORY_SELECT_COLORS = {
    category: color.lower()
    for category, color in CATEGORY_COLORS.items()
}
EXPRESSION_COMMONNESS_SELECT_COLORS = {
    "High": "red",
    "Medium": "yellow",
    "Low": "gray",
}
EXPRESSION_REVIEW_STATUS_SELECT_COLORS = {
    "New": "blue",
    "Reviewing": "yellow",
    "Mastered": "green",
}
VOCABULARY_REVIEW_STATUS_SELECT_COLORS = {
    "New": "blue",
    "Reviewing": "yellow",
    "Mastered": "green",
}

HIGHLIGHT_LEGEND = [
    ("Green", "Native expressions"),
    ("Blue", "Business phrases"),
    ("Yellow", "Industry terms"),
    ("Purple", "Collocations"),
    ("Orange", "Sentence patterns"),
]

REQUIRED_DATABASE_PROPERTIES: dict[str, dict[str, str]] = {
    PODCAST_LIBRARY: {
        "Title": "title",
        "URL": "url",
        "Source Type": "select",
        "Date": "date",
        "Topic": "select",
        "Difficulty": "select",
        "Short Summary": "rich_text",
    },
    EXPRESSION_DATABASE: {
        "Expression": "title",
        "Category": "select",
        "Commonness": "select",
        "Source Podcast": "relation",
        "Review Status": "select",
    },
    WEEKLY_REVIEW: {
        "Week": "title",
        "Date": "date",
        "Podcasts": "relation",
    },
    VOCABULARY_DATABASE: {
        "Name": "title",
        "Source": "relation",
        "First Seen": "date",
        "Review Status": "select",
        "Last Review": "date",
    },
}

REQUIRED_DATABASE_RELATIONS: dict[str, dict[str, str]] = {
    EXPRESSION_DATABASE: {
        "Source Podcast": PODCAST_LIBRARY,
    },
    VOCABULARY_DATABASE: {
        "Source": PODCAST_LIBRARY,
    },
    WEEKLY_REVIEW: {
        "Podcasts": PODCAST_LIBRARY,
    },
}


def category_color(category: str) -> str:
    """Return the visual highlight color assigned to an expression category."""
    return CATEGORY_COLORS.get(category, "Default")
