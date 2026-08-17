"""Application service coordinating grading, scheduling and resumable sessions."""

from __future__ import annotations

from datetime import datetime

from lernkarten.exceptions import EmptySelectionError
from lernkarten.grading import check_answer
from lernkarten.models import (
    Card,
    CardType,
    Deck,
    ReviewRecord,
    StudyOrder,
    StudySession,
    utc_now,
)
from lernkarten.scheduler import order_cards, update_progress


class StudyService:
    """State-changing operations for one deck."""

    def __init__(self, deck: Deck) -> None:
        """Bind the service to a validated deck."""
        self.deck = deck

    def start_session(
        self,
        *,
        order: StudyOrder = StudyOrder.ADAPTIVE,
        topic: str | None = None,
        card_type: CardType | None = None,
        due_only: bool = False,
        limit: int | None = None,
        seed: int | None = None,
        now: datetime | None = None,
    ) -> StudySession:
        """Select, order and persist a new session.

        >>> from lernkarten.models import QuestionAnswerCard
        >>> deck = Deck(name="D", cards=[QuestionAnswerCard(topic="T", prompt="?", answer="!")])
        >>> StudyService(deck).start_session(order=StudyOrder.FIXED).current_index
        0
        """
        timestamp = now or utc_now()
        cards = self.deck.search(
            topic=topic,
            card_type=card_type,
            due_only=due_only,
            now=timestamp,
        )
        if not cards:
            raise EmptySelectionError("Fuer diese Auswahl gibt es keine passenden Karten.")
        ordered = order_cards(
            cards,
            self.deck.profile,
            order,
            seed=seed,
            now=timestamp,
        )
        if limit is not None:
            if limit < 1:
                msg = "limit muss mindestens 1 sein"
                raise ValueError(msg)
            ordered = ordered[:limit]
        session = StudySession(
            profile_name=self.deck.active_profile,
            card_ids=[card.id for card in ordered],
            order=order,
            started_at=timestamp,
        )
        self.deck.active_session = session
        return session

    def current_card(self) -> Card:
        """Return the current card of the active incomplete session."""
        session = self.require_session()
        if session.is_complete:
            raise EmptySelectionError("Die aktuelle Sitzung ist bereits abgeschlossen.")
        return self.deck.get_card(session.card_ids[session.current_index])

    def submit_answer(
        self,
        value: str,
        *,
        duration_seconds: float = 0.0,
        answered_at: datetime | None = None,
    ) -> bool:
        """Grade the current card, update progress and advance the session.

        >>> from lernkarten.models import QuestionAnswerCard
        >>> deck = Deck(name="D", cards=[QuestionAnswerCard(topic="T", prompt="2+2?", answer="4")])
        >>> service = StudyService(deck)
        >>> _ = service.start_session(order=StudyOrder.FIXED)
        >>> service.submit_answer("4")
        True
        """
        timestamp = answered_at or utc_now()
        session = self.require_session()
        card = self.current_card()
        correct = check_answer(card, value)
        progress = self.deck.profile.progress_for(card.id)
        self.deck.profile.progress[str(card.id)] = update_progress(
            progress,
            correct=correct,
            reviewed_at=timestamp,
        )
        session.records.append(
            ReviewRecord(
                card_id=card.id,
                correct=correct,
                given_answer=value,
                answered_at=timestamp,
                duration_seconds=duration_seconds,
            )
        )
        session.current_index += 1
        if session.is_complete:
            session.completed_at = timestamp
            if all(stored.id != session.id for stored in self.deck.session_history):
                self.deck.session_history.append(session.model_copy(deep=True))
        return correct

    def require_session(self) -> StudySession:
        """Return active session or raise an actionable domain error."""
        session = self.deck.active_session
        if session is None:
            raise EmptySelectionError("Es gibt keine aktive Lernsitzung.")
        if session.profile_name != self.deck.active_profile:
            raise EmptySelectionError("Die aktive Sitzung gehoert zu einem anderen Profil.")
        return session
