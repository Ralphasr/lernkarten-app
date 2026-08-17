"""Progress aggregation and text-based charts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from lernkarten.models import CardType, Deck, utc_now


@dataclass(frozen=True, slots=True)
class DeckStatistics:
    """Computed snapshot of the active profile's learning progress."""

    cards: int
    attempts: int
    correct: int
    success_rate: float
    due_cards: int
    completed_sessions: int
    by_type: dict[CardType, int]
    by_topic: dict[str, int]


def calculate_statistics(deck: Deck) -> DeckStatistics:
    """Aggregate counts without mutating the deck.

    >>> calculate_statistics(Deck(name="Leer")).success_rate
    0.0
    """
    attempts = sum(progress.attempts for progress in deck.profile.progress.values())
    correct = sum(progress.correct for progress in deck.profile.progress.values())
    rate = round(correct / attempts * 100, 1) if attempts else 0.0
    now = utc_now()
    due = sum(deck.profile.progress_for(card.id).due_at <= now for card in deck.cards)
    return DeckStatistics(
        cards=len(deck.cards),
        attempts=attempts,
        correct=correct,
        success_rate=rate,
        due_cards=due,
        completed_sessions=len(deck.session_history),
        by_type=dict(Counter(card.type for card in deck.cards)),
        by_topic=dict(Counter(card.topic for card in deck.cards)),
    )


def activity_by_day(deck: Deck, *, days: int = 7, end: date | None = None) -> dict[date, int]:
    """Count answers per calendar day for the active profile's session history."""
    if days < 1:
        msg = "days muss mindestens 1 sein"
        raise ValueError(msg)
    last_day = end or utc_now().date()
    first_day = last_day - timedelta(days=days - 1)
    counts = {first_day + timedelta(days=offset): 0 for offset in range(days)}
    for session in deck.session_history:
        if session.profile_name != deck.active_profile:
            continue
        for record in session.records:
            record_day = record.answered_at.date()
            if record_day in counts:
                counts[record_day] += 1
    return counts


def text_bar_chart(values: dict[str, int], *, width: int = 24) -> list[str]:
    """Render a proportional, zero-safe terminal bar chart.

    >>> text_bar_chart({'A': 2, 'B': 1}, width=4)
    ['A | #### 2', 'B | ##   1']
    """
    if width < 1:
        msg = "width muss mindestens 1 sein"
        raise ValueError(msg)
    maximum = max(values.values(), default=0)
    label_width = max((len(label) for label in values), default=0)
    lines: list[str] = []
    for label, value in values.items():
        length = round(value / maximum * width) if maximum else 0
        bar = "#" * length
        lines.append(f"{label:<{label_width}} | {bar:<{width}} {value}")
    return lines
