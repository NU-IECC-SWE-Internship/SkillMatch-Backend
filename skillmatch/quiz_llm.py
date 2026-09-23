"""
Generate skill quiz questions with Groq (OpenAI-compatible chat API).

Requires GROQ_API_KEY in the environment. Safe to import without a key;
callers should catch QuizGenerationError.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from django.conf import settings


class QuizGenerationError(Exception):
    pass


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise QuizGenerationError("LLM response was not a JSON array.")
    return data


def generate_quiz_questions(skill_name: str, count: int = 10) -> list[dict[str, Any]]:
    """
    Ask Groq for `count` MCQs about skill_name.

    Returns a list of dicts ready for SkillQuizQuestion:
    order, question_text, option_a..d, correct_option (A-D).
    """
    api_key = getattr(settings, "GROQ_API_KEY", "") or ""
    if not api_key.strip():
        raise QuizGenerationError(
            "GROQ_API_KEY is not set. Add it to SkillMatch-Backend/.env first."
        )

    model = getattr(settings, "GROQ_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL

    prompt = f"""
Create exactly {count} multiple-choice quiz questions to verify that someone
can teach the skill "{skill_name}".

Rules:
- Questions must be specific to "{skill_name}", not generic study tips.
- Mix difficulty: some basics, some intermediate.
- Each question has exactly 4 options labeled A, B, C, D.
- Exactly one correct answer.
- Return ONLY a JSON array (no markdown, no commentary) with this shape:
[
  {{
    "order": 1,
    "question_text": "...",
    "option_a": "...",
    "option_b": "...",
    "option_c": "...",
    "option_d": "...",
    "correct_option": "A"
  }}
]
correct_option must be one of "A", "B", "C", or "D".
orders must be 1 through {count}.
""".strip()

    try:
        response = requests.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.4,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a careful quiz author. "
                            "Respond with valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        raise QuizGenerationError(f"Could not reach Groq: {exc}") from exc

    if response.status_code >= 400:
        raise QuizGenerationError(
            f"Groq error ({response.status_code}): {response.text[:400]}"
        )

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise QuizGenerationError("Unexpected Groq response shape.") from exc

    try:
        raw_items = _extract_json_array(content)
    except (json.JSONDecodeError, QuizGenerationError) as exc:
        raise QuizGenerationError(f"Could not parse Groq JSON: {exc}") from exc

    cleaned: list[dict[str, Any]] = []
    for i, item in enumerate(raw_items[:count], start=1):
        if not isinstance(item, dict):
            continue
        correct = str(item.get("correct_option", "")).strip().upper()
        if correct not in {"A", "B", "C", "D"}:
            raise QuizGenerationError(
                f"Invalid correct_option on question {i}: {correct!r}"
            )
        cleaned.append(
            {
                "order": int(item.get("order") or i),
                "question_text": str(item.get("question_text", "")).strip(),
                "option_a": str(item.get("option_a", "")).strip(),
                "option_b": str(item.get("option_b", "")).strip(),
                "option_c": str(item.get("option_c", "")).strip(),
                "option_d": str(item.get("option_d", "")).strip(),
                "correct_option": correct,
            }
        )
        if not cleaned[-1]["question_text"]:
            raise QuizGenerationError(f"Empty question_text on item {i}.")

    if len(cleaned) < count:
        raise QuizGenerationError(
            f"Groq returned {len(cleaned)} questions; expected {count}."
        )

    # Normalize order 1..count
    for i, item in enumerate(cleaned, start=1):
        item["order"] = i

    return cleaned
