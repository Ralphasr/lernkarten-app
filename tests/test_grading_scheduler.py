"""Examples and properties for answer grading and adaptive scheduling."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lernkarten.exceptions import InvalidAnswerError
from lernkarten.grading import check_answer, multiple_choice_index, normalize_text, parse_boolean
from lernkarten.models import (
    CardProgress,
    MultipleChoiceCard,
    QuestionAnswerCard,
    StudyOrder,
    StudyProfile,
    TrueFalseCard,
)
from lernkarten.scheduler import order_cards, update_progress


@given(st.text())
def test_normalization_is_idempotent(value: str) -> None:
    """Normalizing already-normalized Unicode text changes nothing further."""
    assert normalize_text(normalize_text(value)) == normalize_text(value)


@given(st.booleans(), st.integers(min_value=0, max_value=200))
def test_scheduler_preserves_counter_invariants(correct: bool, attempts: int) -> None:
    """Property test: each review adds one attempt and remains Pydantic-valid."""
    previous = CardProgress(attempts=attempts, correct=attempts // 2)
    updated = update_progress(previous, correct=correct)

    assert updated.attempts == attempts + 1
    assert updated.correct <= updated.attempts
    assert 1.3 <= updated.ease_factor <= 3.0
    assert updated.interval_days >= 1


def test_all_card_types_are_graded() -> None:
    """Free text, option indices and localized booleans use their own grading rules."""
    question = QuestionAnswerCard(topic="T", prompt="Name?", answer="Guido van Rossum")
    choice = MultipleChoiceCard(topic="T", prompt="?", choices=["A", "B"], correct_index=1)
    boolean = TrueFalseCard(topic="T", prompt="?", answer=False)

    assert check_answer(question, "  GUIDO   van rossum ")
    assert check_answer(choice, "b")
    assert check_answer(choice, "2")
    assert check_answer(boolean, "nein")
    assert multiple_choice_index(choice, "B") == 1
    assert parse_boolean("ja") is True


@pytest.mark.parametrize("value", ["", "vielleicht", "3"])
def test_invalid_answers_are_actionable(value: str) -> None:
    """Uninterpretable input raises a catchable application exception."""
    card = TrueFalseCard(topic="T", prompt="?", answer=True)
    with pytest.raises(InvalidAnswerError):
        check_answer(card, value)


def test_random_order_is_seeded_and_non_mutating() -> None:
    """A seed yields reproducible shuffling without changing the source list."""
    cards = [QuestionAnswerCard(topic="T", prompt=str(i), answer=str(i)) for i in range(8)]
    original = list(cards)
    profile = StudyProfile(name="Ada")

    first = order_cards(cards, profile, StudyOrder.RANDOM, seed=42)
    second = order_cards(cards, profile, StudyOrder.RANDOM, seed=42)

    assert first == second
    assert first != original
    assert cards == original


def test_adaptive_order_prioritizes_weak_over_mastered() -> None:
    """An unseen card precedes a mastered card that is not overdue."""
    now = datetime(2026, 8, 17, tzinfo=UTC)
    mastered = QuestionAnswerCard(topic="T", prompt="mastered", answer="yes")
    unseen = QuestionAnswerCard(topic="T", prompt="unseen", answer="yes")
    profile = StudyProfile(name="Ada")
    profile.progress[str(mastered.id)] = CardProgress(
        attempts=10,
        correct=10,
        due_at=now + timedelta(days=10),
    )

    ordered = order_cards([mastered, unseen], profile, StudyOrder.ADAPTIVE, now=now)

    assert ordered[0] == unseen
