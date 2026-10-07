"""
Generate skill quiz questions with Groq (OpenAI-compatible chat API).

Requires GROQ_API_KEY in the environment. Safe to import without a key;
callers should catch QuizGenerationError.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

from system_config.services import get_config


logger = logging.getLogger(__name__)


class QuizGenerationError(Exception):
    pass


class _RetryableError(QuizGenerationError):
    """A bad or empty model reply that is worth asking for again."""


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

DIFFICULTIES = ("easy", "medium", "hard")

DIFFICULTY_GUIDE = """
Difficulty levels:
- easy: core terminology and basic facts a beginner learns first.
- medium: applying concepts to a concrete situation or comparing options.
- hard: advanced details, edge cases, debugging or trade-offs only an
  experienced practitioner would know.
""".strip()


def _extract_questions(text: str | None) -> list[Any]:
    """
    Pull the question list out of the reply. Accepts {"questions": [...]},
    a bare array, or JSON surrounded by stray text / code fences.
    """
    if not text or not text.strip():
        raise _RetryableError("Groq returned an empty reply.")

    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            data, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data = data.get("questions")
        if isinstance(data, list):
            return data

    raise _RetryableError("Groq reply did not contain a JSON list of questions.")


def _clean_item(item: Any) -> dict[str, Any] | None:
    """Normalize one question, or return None if it's unusable."""
    if not isinstance(item, dict):
        return None

    question = {
        "question_text": str(item.get("question_text", "")).strip(),
        "option_a": str(item.get("option_a", "")).strip(),
        "option_b": str(item.get("option_b", "")).strip(),
        "option_c": str(item.get("option_c", "")).strip(),
        "option_d": str(item.get("option_d", "")).strip(),
        "correct_option": str(item.get("correct_option", "")).strip().upper(),
    }
    if question["correct_option"] not in {"A", "B", "C", "D"}:
        return None
    if not all(question.values()):
        return None

    difficulty = str(item.get("difficulty", "")).strip().lower()
    question["difficulty"] = difficulty if difficulty in DIFFICULTIES else "medium"
    return question


def _build_prompt(
    skill_name: str,
    count: int,
    avoid: list[str] | None,
    mix: dict[str, int] | None,
) -> str:
    if mix:
        mix_rule = "Use exactly this difficulty split: " + ", ".join(
            f"{mix.get(level, 0)} {level}" for level in DIFFICULTIES
        ) + "."
    else:
        mix_rule = "Mix difficulty across easy, medium and hard."

    prompt = f"""
Create exactly {count} multiple-choice quiz questions to verify that someone
can teach the skill "{skill_name}".

{DIFFICULTY_GUIDE}

Rules:
- Questions must be specific to "{skill_name}", not generic study tips.
- {mix_rule}
- Each question has exactly 4 options labeled A, B, C, D.
- Exactly one correct answer.
- Return ONLY a JSON object (no markdown, no commentary) with this shape:
{{
  "questions": [
    {{
      "question_text": "...",
      "option_a": "...",
      "option_b": "...",
      "option_c": "...",
      "option_d": "...",
      "correct_option": "A",
      "difficulty": "easy"
    }}
  ]
}}
correct_option must be one of "A", "B", "C", or "D".
difficulty must be one of "easy", "medium", or "hard".
""".strip()

    max_avoid = get_config("llm.max_avoid_in_prompt")
    if avoid and max_avoid:
        recent = "\n".join(f"- {text}" for text in avoid[-max_avoid:])
        prompt += (
            "\n\nDo NOT repeat or closely paraphrase any of these existing "
            f"questions:\n{recent}"
        )
    return prompt


def _request_questions(api_key: str, model: str, prompt: str) -> list[Any]:
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.4,
        "max_completion_tokens": 8192,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a careful quiz author. Respond with valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    if model.startswith("openai/gpt-oss"):
        # Reasoning models can spend the whole token budget thinking and reply empty.
        body["reasoning_effort"] = "low"

    try:
        response = requests.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=90,
        )
    except requests.Timeout as exc:
        raise _RetryableError("Groq timed out.") from exc
    except requests.RequestException as exc:
        raise QuizGenerationError(f"Could not reach Groq: {exc}") from exc

    if response.status_code == 429:
        raise QuizGenerationError(
            "Groq rate limit reached. Please try again in a minute."
        )
    if response.status_code >= 500 or (
        response.status_code == 400 and "json_validate_failed" in response.text
    ):
        raise _RetryableError(f"Groq error ({response.status_code}).")
    if response.status_code >= 400:
        raise QuizGenerationError(
            f"Groq error ({response.status_code}): {response.text[:400]}"
        )

    try:
        content = response.json()["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise _RetryableError("Unexpected Groq response shape.") from exc

    return _extract_questions(content)


def generate_quiz_questions(
    skill_name: str,
    count: int = 10,
    avoid: list[str] | None = None,
    mix: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """
    Ask Groq for `count` MCQs about skill_name.

    Returns a list of dicts ready for SkillQuizQuestion:
    order, question_text, option_a..d, correct_option (A-D), difficulty.
    `avoid` lists existing question texts the model should not repeat.
    `mix` asks for a number of questions per difficulty, e.g. {"easy": 4, ...}.

    Bad replies are retried up to `llm.max_attempts` times; valid questions
    from every attempt are kept, so a partly broken reply isn't wasted.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "") or ""
    if not api_key.strip():
        raise QuizGenerationError(
            "GROQ_API_KEY is not set. Add it to SkillMatch-Backend/.env first."
        )

    model = get_config("llm.model")
    prompt = _build_prompt(skill_name, count, avoid, mix)
    attempts = max(get_config("llm.max_attempts"), 1)

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            raw_items = _request_questions(api_key, model, prompt)
        except _RetryableError as exc:
            last_error = exc
            logger.warning("Quiz generation attempt %s/%s failed: %s", attempt, attempts, exc)
            continue

        for item in raw_items:
            question = _clean_item(item)
            if question is None:
                continue
            key = " ".join(question["question_text"].lower().split())
            if key in seen:
                continue
            seen.add(key)
            collected.append(question)

        if len(collected) >= count:
            break
        last_error = _RetryableError(
            f"Groq returned {len(collected)} usable questions; expected {count}."
        )

    if not collected:
        raise QuizGenerationError(
            f"Could not generate questions after {attempts} attempts: {last_error}"
        )

    questions = collected[:count]
    for i, question in enumerate(questions, start=1):
        question["order"] = i
    return questions
