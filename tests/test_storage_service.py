"""Integration tests for persistence and resumable learning sessions."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lernkarten.cli import main
from lernkarten.exceptions import DeckIOError, EmptySelectionError, InvalidDeckFileError
from lernkarten.models import Card, Deck, QuestionAnswerCard, StudyOrder
from lernkarten.service import StudyService
from lernkarten.statistics import activity_by_day, calculate_statistics, text_bar_chart
from lernkarten.storage import DeckRepository


def test_repository_round_trip_preserves_discriminated_models(tmp_path: Path) -> None:
    """Saved cards load back as the same concrete Pydantic variant."""
    path = tmp_path / "nested" / "deck.json"
    repository = DeckRepository(path)
    deck = Deck(name="D", cards=[QuestionAnswerCard(topic="T", prompt="2+2?", answer="4")])

    repository.save(deck)
    loaded = repository.load()

    assert loaded == deck
    assert isinstance(loaded.cards[0], QuestionAnswerCard)
    assert not (path.parent / ".deck.json.tmp").exists()


def test_repository_reports_missing_invalid_json_and_invalid_schema(tmp_path: Path) -> None:
    """Three common file errors become meaningful non-raw exceptions."""
    missing = DeckRepository(tmp_path / "missing.json")
    with pytest.raises(DeckIOError, match="nicht gefunden"):
        missing.load()

    invalid_json = tmp_path / "syntax.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(InvalidDeckFileError, match="Zeile"):
        DeckRepository(invalid_json).load()

    invalid_schema = tmp_path / "schema.json"
    invalid_schema.write_text(json.dumps({"name": ""}), encoding="utf-8")
    with pytest.raises(InvalidDeckFileError, match="Deck-Daten"):
        DeckRepository(invalid_schema).load()


def test_repository_normalizes_all_naive_datetimes_to_utc(tmp_path: Path) -> None:
    """Naive timestamps from JSON become UTC across every persistent datetime field."""
    path = tmp_path / "naive-datetimes.json"
    card_id = "00000000-0000-0000-0000-000000000001"
    timestamp = "2026-08-17T12:00:00"
    session = {
        "profile_name": "Standard",
        "card_ids": [card_id],
        "order": "fixed",
        "current_index": 1,
        "records": [
            {
                "card_id": card_id,
                "correct": True,
                "given_answer": "yes",
                "answered_at": timestamp,
            }
        ],
        "started_at": timestamp,
        "completed_at": timestamp,
    }
    path.write_text(
        json.dumps(
            {
                "name": "D",
                "cards": [
                    {
                        "id": card_id,
                        "type": "question_answer",
                        "topic": "T",
                        "prompt": "Ready?",
                        "answer": "yes",
                        "created_at": timestamp,
                    }
                ],
                "profiles": {
                    "Standard": {
                        "name": "Standard",
                        "progress": {
                            card_id: {
                                "due_at": timestamp,
                                "last_reviewed_at": timestamp,
                            }
                        },
                    }
                },
                "active_profile": "Standard",
                "active_session": session,
                "session_history": [session],
            }
        ),
        encoding="utf-8",
    )

    assert main(["--file", str(path), "stats"]) == 0
    deck = DeckRepository(path).load()
    progress = deck.profile.progress[card_id]
    assert deck.active_session is not None
    timestamps = [
        deck.cards[0].created_at,
        progress.due_at,
        progress.last_reviewed_at,
        deck.active_session.started_at,
        deck.active_session.completed_at,
        deck.active_session.records[0].answered_at,
        deck.session_history[0].started_at,
        deck.session_history[0].completed_at,
        deck.session_history[0].records[0].answered_at,
    ]
    assert all(value is not None and value.tzinfo is UTC for value in timestamps)


def test_session_can_resume_and_updates_statistics(tmp_path: Path) -> None:
    """A saved half-session resumes at the same card and finishes with correct totals."""
    cards: list[Card] = [
        QuestionAnswerCard(topic="T", prompt="1+1?", answer="2"),
        QuestionAnswerCard(topic="T", prompt="2+2?", answer="4"),
    ]
    path = tmp_path / "deck.json"
    repository = DeckRepository(path)
    deck = Deck(name="D", cards=cards)
    service = StudyService(deck)
    service.start_session(order=StudyOrder.FIXED)
    assert service.submit_answer("2", answered_at=datetime(2026, 8, 17, tzinfo=UTC))
    repository.save(deck)

    resumed = repository.load()
    resumed_service = StudyService(resumed)
    assert resumed_service.current_card().prompt == "2+2?"
    assert not resumed_service.submit_answer("5", answered_at=datetime(2026, 8, 17, tzinfo=UTC))

    stats = calculate_statistics(resumed)
    assert (stats.attempts, stats.correct, stats.success_rate) == (2, 1, 50.0)
    assert stats.completed_sessions == 1
    assert activity_by_day(resumed, days=1, end=datetime(2026, 8, 17).date()).popitem()[1] == 2


def test_completed_sessions_are_counted_for_active_profile_only() -> None:
    """A completed session contributes only to the profile that studied it."""
    card = QuestionAnswerCard(topic="T", prompt="2+2?", answer="4")
    deck = Deck(name="D", cards=[card])
    deck.add_profile("A")
    deck.add_profile("B")
    service = StudyService(deck)
    service.start_session(order=StudyOrder.FIXED)
    assert service.submit_answer("4", answered_at=datetime(2026, 8, 17, tzinfo=UTC))

    deck.active_profile = "A"
    profile_a = calculate_statistics(deck)
    assert (
        profile_a.completed_sessions,
        profile_a.attempts,
        profile_a.correct,
        profile_a.success_rate,
    ) == (0, 0, 0, 0.0)

    deck.active_profile = "B"
    profile_b = calculate_statistics(deck)
    assert (
        profile_b.completed_sessions,
        profile_b.attempts,
        profile_b.correct,
        profile_b.success_rate,
    ) == (1, 1, 1, 100.0)


def test_empty_session_selection_and_invalid_chart_arguments() -> None:
    """Preconditions reject meaningless operations early."""
    service = StudyService(Deck(name="D"))
    with pytest.raises(EmptySelectionError):
        service.start_session()
    with pytest.raises(EmptySelectionError):
        service.require_session()
    with pytest.raises(ValueError):
        text_bar_chart({"A": 1}, width=0)
    with pytest.raises(ValueError):
        activity_by_day(Deck(name="D"), days=0)


def test_text_chart_is_zero_safe() -> None:
    """All-zero data still produces aligned chart lines."""
    assert text_bar_chart({"A": 0, "Long": 0}, width=3) == [
        "A    |     0",
        "Long |     0",
    ]
