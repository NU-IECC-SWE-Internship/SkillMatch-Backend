"""
Per-skill question bank.

- Each skill gets up to `quiz_bank.size` questions per monthly cycle ("YYYY-MM").
- The bank grows by at most `quiz_bank.daily_batch` questions per skill per day so we
  stay within Groq rate limits (run `python manage.py fill_question_bank` daily).
- A new month starts a new cycle. Until the new cycle is full, quizzes draw
  from the current and previous cycles together; older cycles are deleted.
- Questions are tagged easy / medium / hard. `quiz.difficulty_mix` controls the
  share of each level in generated batches and in quizzes, which are presented
  from easy to hard.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from django.utils import timezone

from system_config.services import get_config

from .models import Skill, SkillQuizQuestion
from .quiz_llm import QuizGenerationError, generate_quiz_questions


def bank_size() -> int:
    return get_config("quiz_bank.size")


def daily_batch() -> int:
    return get_config("quiz_bank.daily_batch")

QUESTION_FIELDS = [
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_option",
]

LEVELS = SkillQuizQuestion.DIFFICULTY_ORDER


def level_of(question: SkillQuizQuestion) -> str:
    return question.difficulty if question.difficulty in LEVELS else SkillQuizQuestion.MEDIUM


def difficulty_weights() -> dict[str, float]:
    raw = get_config("quiz.difficulty_mix")
    weights = {}
    if isinstance(raw, dict):
        for level in LEVELS:
            try:
                weights[level] = max(float(raw.get(level, 0)), 0.0)
            except (TypeError, ValueError):
                weights[level] = 0.0
    if sum(weights.values()) <= 0:
        weights = {level: 1.0 for level in LEVELS}
    return weights


def split_by_difficulty(total: int, weights: dict[str, float] | None = None) -> dict[str, int]:
    """Divide `total` across levels proportionally (largest remainder method)."""
    weights = weights or difficulty_weights()
    weight_sum = sum(weights.values()) or 1
    exact = {level: total * weights.get(level, 0) / weight_sum for level in LEVELS}
    counts = {level: int(exact[level]) for level in LEVELS}
    remainder = total - sum(counts.values())
    by_fraction = sorted(LEVELS, key=lambda level: exact[level] - counts[level], reverse=True)
    for level in by_fraction[:remainder]:
        counts[level] += 1
    return counts


def batch_mix(skill: Skill, count: int) -> dict[str, int]:
    """Difficulty split for the next generated batch, favouring levels the bank lacks."""
    target = split_by_difficulty(bank_size())
    existing = {level: 0 for level in LEVELS}
    for question in SkillQuizQuestion.objects.filter(skill=skill, cycle=current_cycle()):
        existing[level_of(question)] += 1
    missing = {level: max(target[level] - existing[level], 0) for level in LEVELS}
    if sum(missing.values()) <= 0:
        return split_by_difficulty(count)
    return split_by_difficulty(count, missing)


def current_cycle(today: date | None = None) -> str:
    today = today or timezone.localdate()
    return today.strftime("%Y-%m")


def previous_cycle(today: date | None = None) -> str:
    today = today or timezone.localdate()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    return last_month_end.strftime("%Y-%m")


def prune_old_cycles(skill: Skill) -> int:
    keep = {current_cycle(), previous_cycle()}
    deleted, _ = (
        SkillQuizQuestion.objects
        .filter(skill=skill)
        .exclude(cycle__in=keep)
        .delete()
    )
    return deleted


def generated_today(skill: Skill) -> bool:
    return SkillQuizQuestion.objects.filter(
        skill=skill,
        cycle=current_cycle(),
        created_at__date=timezone.localdate(),
    ).exists()


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def save_generated(skill: Skill, generated: list[dict]) -> list[SkillQuizQuestion]:
    """Store new questions in the current cycle, skipping duplicates."""
    existing = {
        _normalize(text)
        for text in SkillQuizQuestion.objects
        .filter(skill=skill)
        .values_list("question_text", flat=True)
    }
    cycle = current_cycle()
    room = bank_size() - SkillQuizQuestion.objects.filter(skill=skill, cycle=cycle).count()

    to_create = []
    for item in generated:
        if len(to_create) >= room:
            break
        key = _normalize(item["question_text"])
        if key in existing:
            continue
        existing.add(key)
        to_create.append(
            SkillQuizQuestion(
                skill=skill,
                cycle=cycle,
                difficulty=item.get("difficulty", SkillQuizQuestion.MEDIUM),
                **{field: item[field] for field in QUESTION_FIELDS},
            )
        )
    return SkillQuizQuestion.objects.bulk_create(to_create)


def top_up_skill(skill: Skill, *, force: bool = False) -> int:
    """
    Add one daily batch to the skill's current cycle.
    Returns how many questions were saved (0 if full or already done today).
    Raises QuizGenerationError if Groq fails.
    """
    prune_old_cycles(skill)

    size = bank_size()
    count = SkillQuizQuestion.objects.filter(skill=skill, cycle=current_cycle()).count()
    if count >= size:
        return 0
    if not force and generated_today(skill):
        return 0

    avoid = list(
        SkillQuizQuestion.objects
        .filter(skill=skill)
        .order_by("-created_at")
        .values_list("question_text", flat=True)
    )
    batch = min(daily_batch(), size - count)
    generated = generate_quiz_questions(
        skill.name,
        count=batch,
        avoid=avoid,
        mix=batch_mix(skill, batch),
    )
    return len(save_generated(skill, generated))


def bank_pool(skill: Skill):
    """Questions eligible for quizzes right now."""
    cycle = current_cycle()
    current = SkillQuizQuestion.objects.filter(skill=skill, cycle=cycle)
    if current.count() >= bank_size():
        return current
    return SkillQuizQuestion.objects.filter(
        skill=skill,
        cycle__in=[cycle, previous_cycle()],
    )


def draw_quiz(skill: Skill, count: int) -> list[dict]:
    """
    Pick `count` random questions from the bank following the difficulty mix,
    ordered easy -> medium -> hard. Generates a batch first if the bank is too
    small. Returns dicts in PendingSkillQuiz format.
    """
    pool = list(bank_pool(skill))
    if len(pool) < count:
        top_up_skill(skill, force=True)
        pool = list(bank_pool(skill))
    if len(pool) < count:
        raise QuizGenerationError(
            f"Question bank for {skill.name} has only {len(pool)} questions."
        )

    by_level = {level: [] for level in LEVELS}
    for question in pool:
        by_level[level_of(question)].append(question)

    wanted = split_by_difficulty(count)
    picked = {}
    leftovers = []
    for level in LEVELS:
        random.shuffle(by_level[level])
        picked[level] = by_level[level][:wanted[level]]
        leftovers.extend(by_level[level][wanted[level]:])

    # A level with too few questions is topped up from the other levels.
    shortfall = count - sum(len(questions) for questions in picked.values())
    for question in random.sample(leftovers, shortfall):
        picked[level_of(question)].append(question)

    ordered = [question for level in LEVELS for question in picked[level]]
    return [
        {
            "order": i,
            "bank_id": q.id,
            "difficulty": level_of(q),
            **{field: getattr(q, field) for field in QUESTION_FIELDS},
        }
        for i, q in enumerate(ordered, start=1)
    ]
