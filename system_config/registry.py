"""
Every tunable value in the system, with its default.

Rows in the SystemConfig table override these defaults and can be edited in
Django admin without a deploy. Missing rows are created automatically after
`migrate`, so adding a key here is all that's needed to expose a new setting.
"""

from dataclasses import dataclass
from typing import Any

from django.conf import settings


INT = "int"
FLOAT = "float"
BOOL = "bool"
STR = "str"
JSON = "json"

VALUE_TYPES = [
    (INT, "Integer"),
    (FLOAT, "Decimal"),
    (BOOL, "True / False"),
    (STR, "Text"),
    (JSON, "JSON"),
]


@dataclass(frozen=True)
class ConfigDefinition:
    key: str
    default: Any
    value_type: str
    category: str
    description: str
    # Public keys are returned by GET /api/config/ so the frontend can use them.
    is_public: bool = False
    min_value: float | None = None
    max_value: float | None = None


DEFINITIONS = [
    # Skill verification quiz
    ConfigDefinition(
        key="quiz.question_count",
        default=10,
        value_type=INT,
        category="quiz",
        description="Number of questions in each skill verification quiz.",
        is_public=True,
        min_value=1,
        max_value=50,
    ),
    ConfigDefinition(
        key="quiz.pass_score",
        default=7,
        value_type=INT,
        category="quiz",
        description="Correct answers needed to pass the quiz and verify the skill.",
        is_public=True,
        min_value=1,
        max_value=50,
    ),
    ConfigDefinition(
        key="quiz.cooldown_hours",
        default=24,
        value_type=INT,
        category="quiz",
        description="Hours a user must wait after an attempt before retrying the quiz.",
        is_public=True,
        min_value=0,
    ),
    ConfigDefinition(
        key="quiz.start_grace_seconds",
        default=10,
        value_type=INT,
        category="quiz",
        description=(
            "A repeated Start within this many seconds returns the same questions "
            "instead of counting the first quiz as abandoned."
        ),
        min_value=0,
    ),
    ConfigDefinition(
        key="quiz.difficulty_mix",
        default={"easy": 4, "medium": 3, "hard": 3},
        value_type=JSON,
        category="quiz",
        description=(
            "Relative share of easy / medium / hard questions in each quiz and in "
            "newly generated questions. Quizzes are ordered from easy to hard."
        ),
    ),

    # Question bank
    ConfigDefinition(
        key="quiz_bank.size",
        default=100,
        value_type=INT,
        category="quiz_bank",
        description="Maximum questions stored per skill per monthly cycle.",
        min_value=1,
    ),
    ConfigDefinition(
        key="quiz_bank.daily_batch",
        default=10,
        value_type=INT,
        category="quiz_bank",
        description="Maximum questions generated per skill per day (keeps LLM usage within rate limits).",
        min_value=1,
    ),

    # LLM
    ConfigDefinition(
        key="llm.model",
        default=getattr(settings, "GROQ_MODEL", "") or "openai/gpt-oss-20b",
        value_type=STR,
        category="llm",
        description="Groq model used to generate quiz questions.",
    ),
    ConfigDefinition(
        key="llm.max_avoid_in_prompt",
        default=40,
        value_type=INT,
        category="llm",
        description="How many existing questions are sent to the LLM as 'do not repeat' examples.",
        min_value=0,
    ),
    ConfigDefinition(
        key="llm.max_attempts",
        default=3,
        value_type=INT,
        category="llm",
        description="How many times to ask the LLM again when it returns an empty or invalid reply.",
        min_value=1,
        max_value=5,
    ),

    # Meeting reviews
    ConfigDefinition(
        key="reviews.window_hours",
        default=48,
        value_type=INT,
        category="reviews",
        description=(
            "Hours after a meeting ends during which participants can submit a review. "
            "Unrevealed reviews are revealed once the window closes."
        ),
        is_public=True,
        min_value=1,
    ),
]

REGISTRY = {d.key: d for d in DEFINITIONS}
