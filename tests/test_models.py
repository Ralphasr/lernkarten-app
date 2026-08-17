"""Unit tests for validated domain models and deck operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lernkarten.exceptions import CardNotFoundError
from lernkarten.models import (
    Card,
    CardProgress,
    CardType,
    Deck,
    MultipleChoiceCard,
    QuestionAnswerCard,
    TrueFalseCard,
)


def test_all_card_types_validate_and_filter() -> None:
    """A deck can combine and filter every discriminated card variant."""
    cards: list[Card] = [
        QuestionAnswerCard(topic="Syntax", prompt="Keyword?", answer="def", tags=[" Python "]),
        MultipleChoiceCard(
            topic="Typen",
            prompt="Mutable?",
            choices=["tuple", "list"],
            correct_index=1,
        ),
        TrueFalseCard(topic="Syntax", prompt="Einrueckung zaehlt.", answer=True),
    ]
    deck = Deck(name=" Test ", cards=cards)

    assert deck.name == "Test"
    assert deck.topics() == ["Syntax", "Typen"]
    assert deck.search("python") == [cards[0]]
    assert deck.search(card_type=CardType.TRUE_FALSE) == [cards[2]]


@pytest.mark.parametrize(
    ("choices", "correct_index"),
    [(["A", "A"], 0), (["A", "B"], 2), (["", "B"], 1)],
)
def test_multiple_choice_rejects_invalid_options(choices: list[str], correct_index: int) -> None:
    """Duplicate, empty and out-of-range choices violate model invariants."""
    with pytest.raises(ValidationError):
        MultipleChoiceCard(topic="T", prompt="?", choices=choices, correct_index=correct_index)


def test_progress_rejects_impossible_counter() -> None:
    """Correct answers cannot exceed all attempts."""
    with pytest.raises(ValidationError):
        CardProgress(attempts=1, correct=2)


def test_profiles_are_independent_and_card_removal_cleans_progress() -> None:
    """Each profile owns progress and removal prevents stale entries."""
    card = QuestionAnswerCard(topic="T", prompt="?", answer="!")
    deck = Deck(name="D", cards=[card])
    deck.profile.progress_for(card.id).attempts = 3
    deck.add_profile("Ada")

    assert deck.profile.progress_for(card.id).attempts == 0
    removed = deck.remove_card(card.id)
    assert removed.id == card.id
    assert all(str(card.id) not in profile.progress for profile in deck.profiles.values())


def test_missing_card_uses_domain_exception() -> None:
    """Lookup failures expose a stable domain-level exception."""
    with pytest.raises(CardNotFoundError):
        Deck(name="D").get_card(uuid4())


def test_due_filter_uses_active_profile() -> None:
    """Due selection compares timezone-aware dates from the active profile."""
    now = datetime(2026, 8, 17, tzinfo=UTC)
    due = QuestionAnswerCard(topic="T", prompt="due", answer="yes")
    later = QuestionAnswerCard(topic="T", prompt="later", answer="no")
    deck = Deck(name="D", cards=[due, later])
    deck.profile.progress_for(due.id).due_at = now - timedelta(minutes=1)
    deck.profile.progress_for(later.id).due_at = now + timedelta(days=1)

    assert deck.search(due_only=True, now=now) == [due]
