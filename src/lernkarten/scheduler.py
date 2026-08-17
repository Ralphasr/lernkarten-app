"""Deterministic scheduling and card-order strategies.

The scheduler uses a deliberately small SM-2-inspired algorithm. Its calculations
are pure functions, which makes them easy to test and explain in the report.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timedelta

from lernkarten.models import (
    Card,
    CardProgress,
    StudyOrder,
    StudyProfile,
    utc_now,
)


def update_progress(
    progress: CardProgress,
    *,
    correct: bool,
    reviewed_at: datetime | None = None,
) -> CardProgress:
    """Return new progress after one answer using an SM-2-inspired interval.

    A wrong answer resets the repetition streak and is due the next day. Correct
    answers use intervals of 1, 3 and then roughly ``interval * ease_factor`` days.

    >>> first = update_progress(CardProgress(), correct=True)
    >>> (first.attempts, first.correct, first.interval_days)
    (1, 1, 1)
    >>> update_progress(first, correct=False).lapses
    1
    """
    timestamp = reviewed_at or utc_now()
    attempts = progress.attempts + 1
    correct_count = progress.correct + int(correct)
    if correct:
        repetitions = progress.repetitions + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 3
        else:
            interval = max(1, round(progress.interval_days * progress.ease_factor))
        ease = min(3.0, progress.ease_factor + 0.05)
        lapses = progress.lapses
    else:
        repetitions = 0
        interval = 1
        ease = max(1.3, progress.ease_factor - 0.2)
        lapses = progress.lapses + 1
    return CardProgress(
        attempts=attempts,
        correct=correct_count,
        repetitions=repetitions,
        lapses=lapses,
        interval_days=interval,
        ease_factor=ease,
        due_at=timestamp + timedelta(days=interval),
        last_reviewed_at=timestamp,
    )


def adaptive_priority(card: Card, profile: StudyProfile, *, now: datetime) -> tuple[float, str]:
    """Return a sortable priority: weak and overdue cards come first.

    The UUID string is a stable tie breaker, making the result reproducible.
    """
    progress = profile.progress_for(card.id)
    overdue_days = max(0.0, (now - progress.due_at).total_seconds() / 86_400)
    error_rate = 1.0 - progress.correct / progress.attempts if progress.attempts else 1.0
    unseen_bonus = 4.0 if progress.attempts == 0 else 0.0
    priority = unseen_bonus + error_rate * 3.0 + min(overdue_days, 30.0) / 10.0
    return (-priority, str(card.id))


def order_cards(
    cards: Sequence[Card],
    profile: StudyProfile,
    order: StudyOrder,
    *,
    seed: int | None = None,
    now: datetime | None = None,
) -> list[Card]:
    """Return a new card list in fixed, random or adaptive order.

    >>> from lernkarten.models import QuestionAnswerCard
    >>> cards = [QuestionAnswerCard(topic="T", prompt=str(i), answer=str(i)) for i in range(3)]
    >>> profile = StudyProfile(name="Ada")
    >>> [card.prompt for card in order_cards(cards, profile, StudyOrder.FIXED)]
    ['0', '1', '2']
    """
    result = list(cards)
    if order is StudyOrder.RANDOM:
        random.Random(seed).shuffle(result)
    elif order is StudyOrder.ADAPTIVE:
        timestamp = now or utc_now()
        result.sort(key=lambda card: adaptive_priority(card, profile, now=timestamp))
    return result
