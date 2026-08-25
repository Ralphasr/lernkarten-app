"""Validierte Datenmodelle fuer Karten, Decks und Lernfortschritt.

Pydantic stellt sicher, dass auch Daten aus JSON- oder Importdateien dieselben
Invarianten einhalten wie interaktiv erstellte Karten.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from lernkarten.exceptions import CardNotFoundError


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


class CardType(StrEnum):
    """Supported card variants."""

    QUESTION_ANSWER = "question_answer"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"


class StudyOrder(StrEnum):
    """Available order strategies in a study session."""

    FIXED = "fixed"
    RANDOM = "random"
    ADAPTIVE = "adaptive"


class AppModel(BaseModel):
    """Strict base configuration shared by persistent application models."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CardProgress(AppModel):
    """Per-profile learning state for one card.

    >>> progress = CardProgress(attempts=2, correct=1)
    >>> progress.success_rate
    50.0
    """

    attempts: int = Field(default=0, ge=0)
    correct: int = Field(default=0, ge=0)
    repetitions: int = Field(default=0, ge=0)
    lapses: int = Field(default=0, ge=0)
    interval_days: int = Field(default=0, ge=0)
    ease_factor: float = Field(default=2.5, ge=1.3, le=3.0)
    due_at: datetime = Field(default_factory=utc_now)
    last_reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def correct_does_not_exceed_attempts(self) -> CardProgress:
        """Reject inconsistent counters.

        >>> CardProgress(attempts=1, correct=1).correct
        1
        """
        if self.correct > self.attempts:
            msg = "correct darf attempts nicht ueberschreiten"
            raise ValueError(msg)
        return self

    @property
    def success_rate(self) -> float:
        """Return correct answers as a percentage, or zero without attempts."""
        if self.attempts == 0:
            return 0.0
        return round(self.correct / self.attempts * 100, 1)


class StudyProfile(AppModel):
    """Independent learning state for a named user profile."""

    name: str = Field(min_length=1, max_length=80)
    progress: dict[str, CardProgress] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        """Strip profile names and reject whitespace-only input."""
        cleaned = value.strip()
        if not cleaned:
            msg = "Profilname darf nicht leer sein"
            raise ValueError(msg)
        return cleaned

    def progress_for(self, card_id: UUID) -> CardProgress:
        """Return an existing card progress object or create it.

        >>> profile = StudyProfile(name="Ada")
        >>> profile.progress_for(UUID(int=1)).attempts
        0
        """
        key = str(card_id)
        if key not in self.progress:
            self.progress[key] = CardProgress()
        return self.progress[key]


class BaseCard(AppModel):
    """Fields and validation shared by all card variants."""

    id: UUID = Field(default_factory=uuid4)
    topic: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=2_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("topic", "prompt")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        """Strip required text fields and reject whitespace-only values."""
        cleaned = value.strip()
        if not cleaned:
            msg = "Textfeld darf nicht leer sein"
            raise ValueError(msg)
        return cleaned

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        """Normalize, de-duplicate and sort tags.

        >>> BaseCard.clean_tags([" Python ", "python", "Pruefung"])
        ['Pruefung', 'python']
        """
        by_key = {tag.strip().casefold(): tag.strip() for tag in values if tag.strip()}
        return sorted(by_key.values(), key=str.casefold)


class QuestionAnswerCard(BaseCard):
    """A free-text question-and-answer card."""

    type: Literal[CardType.QUESTION_ANSWER] = CardType.QUESTION_ANSWER
    answer: str = Field(min_length=1, max_length=4_000)

    @field_validator("answer")
    @classmethod
    def clean_answer(cls, value: str) -> str:
        """Strip and validate the expected answer."""
        cleaned = value.strip()
        if not cleaned:
            msg = "Antwort darf nicht leer sein"
            raise ValueError(msg)
        return cleaned


class MultipleChoiceCard(BaseCard):
    """A multiple-choice card with exactly one correct option."""

    type: Literal[CardType.MULTIPLE_CHOICE] = CardType.MULTIPLE_CHOICE
    choices: list[str] = Field(min_length=2, max_length=10)
    correct_index: int = Field(ge=0)

    @field_validator("choices")
    @classmethod
    def clean_choices(cls, values: list[str]) -> list[str]:
        """Strip choices and require unique, non-empty options."""
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            msg = "Auswahlmoeglichkeiten duerfen nicht leer sein"
            raise ValueError(msg)
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            msg = "Auswahlmoeglichkeiten muessen eindeutig sein"
            raise ValueError(msg)
        return cleaned

    @model_validator(mode="after")
    def correct_index_exists(self) -> MultipleChoiceCard:
        """Ensure the correct index addresses an existing choice."""
        if self.correct_index >= len(self.choices):
            msg = "correct_index liegt ausserhalb der Auswahl"
            raise ValueError(msg)
        return self


class TrueFalseCard(BaseCard):
    """A card whose expected answer is true or false."""

    type: Literal[CardType.TRUE_FALSE] = CardType.TRUE_FALSE
    answer: bool
    explanation: str = Field(default="", max_length=2_000)


Card = Annotated[
    QuestionAnswerCard | MultipleChoiceCard | TrueFalseCard,
    Field(discriminator="type"),
]
CARD_ADAPTER: TypeAdapter[Card] = TypeAdapter(Card)


class ReviewRecord(AppModel):
    """Immutable-looking audit record for a single answered card."""

    card_id: UUID
    correct: bool
    given_answer: str
    answered_at: datetime = Field(default_factory=utc_now)
    duration_seconds: float = Field(default=0.0, ge=0.0)


class StudySession(AppModel):
    """Serializable state that lets a user resume an interrupted session."""

    id: UUID = Field(default_factory=uuid4)
    profile_name: str
    card_ids: list[UUID] = Field(min_length=1)
    order: StudyOrder
    current_index: int = Field(default=0, ge=0)
    records: list[ReviewRecord] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def index_is_in_session(self) -> StudySession:
        """Reject impossible resume positions."""
        if self.current_index > len(self.card_ids):
            msg = "current_index liegt ausserhalb der Sitzung"
            raise ValueError(msg)
        return self

    @property
    def is_complete(self) -> bool:
        """Return whether every selected card has been answered."""
        return self.current_index >= len(self.card_ids)

    @property
    def correct_count(self) -> int:
        """Count correct answers recorded in this session."""
        return sum(record.correct for record in self.records)

    @property
    def success_rate(self) -> float:
        """Return the session success percentage.

        >>> session = StudySession(profile_name="Ada", card_ids=[UUID(int=1)], order="fixed")
        >>> session.success_rate
        0.0
        """
        if not self.records:
            return 0.0
        return round(self.correct_count / len(self.records) * 100, 1)


class Deck(AppModel):
    """Aggregate root containing cards, profiles and an optional live session."""

    schema_version: int = Field(default=1, ge=1)
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    cards: list[Card] = Field(default_factory=list)
    profiles: dict[str, StudyProfile] = Field(
        default_factory=lambda: {"Standard": StudyProfile(name="Standard")}
    )
    active_profile: str = "Standard"
    active_session: StudySession | None = None
    session_history: list[StudySession] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_deck_name(cls, value: str) -> str:
        """Strip the deck name and reject whitespace-only names."""
        cleaned = value.strip()
        if not cleaned:
            msg = "Deckname darf nicht leer sein"
            raise ValueError(msg)
        return cleaned

    @model_validator(mode="after")
    def deck_invariants(self) -> Deck:
        """Validate unique cards and a valid active profile."""
        ids = [card.id for card in self.cards]
        if len(ids) != len(set(ids)):
            msg = "Karten-IDs muessen eindeutig sein"
            raise ValueError(msg)
        if self.active_profile not in self.profiles:
            msg = "Aktives Profil existiert nicht"
            raise ValueError(msg)
        return self

    @property
    def profile(self) -> StudyProfile:
        """Return the currently active profile."""
        return self.profiles[self.active_profile]

    def add_profile(self, name: str) -> StudyProfile:
        """Create and activate a profile, rejecting duplicate names."""
        profile = StudyProfile(name=name)
        if profile.name in self.profiles:
            msg = f"Profil '{profile.name}' existiert bereits"
            raise ValueError(msg)
        self.profiles[profile.name] = profile
        self.active_profile = profile.name
        return profile

    def add_card(self, card: Card) -> None:
        """Add a card while preserving the unique-ID invariant.

        >>> deck = Deck(name="Python")
        >>> deck.add_card(QuestionAnswerCard(topic="Syntax", prompt="2+2?", answer="4"))
        >>> len(deck.cards)
        1
        """
        if any(existing.id == card.id for existing in self.cards):
            msg = f"Karte {card.id} existiert bereits"
            raise ValueError(msg)
        self.cards.append(card)

    def get_card(self, card_id: UUID) -> Card:
        """Return a card by ID or raise a domain-specific error."""
        for card in self.cards:
            if card.id == card_id:
                return card
        raise CardNotFoundError(f"Karte {card_id} wurde nicht gefunden")

    def replace_card(self, card: Card) -> None:
        """Replace an existing card with an identically identified version."""
        for index, existing in enumerate(self.cards):
            if existing.id == card.id:
                self.cards[index] = card
                return
        raise CardNotFoundError(f"Karte {card.id} wurde nicht gefunden")

    def remove_card(self, card_id: UUID) -> Card:
        """Remove and return a card, cleaning profile progress as well."""
        card = self.get_card(card_id)
        self.cards.remove(card)
        for profile in self.profiles.values():
            profile.progress.pop(str(card_id), None)
        return card

    def search(
        self,
        query: str = "",
        *,
        topic: str | None = None,
        card_type: CardType | None = None,
        due_only: bool = False,
        now: datetime | None = None,
    ) -> list[Card]:
        """Filter cards by text, topic, type and due status.

        >>> card = QuestionAnswerCard(topic="Python", prompt="PEP?", answer="8")
        >>> deck = Deck(name="D", cards=[card])
        >>> len(deck.search("pep", topic="python"))
        1
        """
        needle = query.strip().casefold()
        selected: list[Card] = []
        comparison_time = now or utc_now()
        for card in self.cards:
            haystack = " ".join([card.topic, card.prompt, *card.tags]).casefold()
            if needle and needle not in haystack:
                continue
            if topic is not None and card.topic.casefold() != topic.strip().casefold():
                continue
            if card_type is not None and card.type != card_type:
                continue
            if due_only:
                progress = self.profile.progress.get(str(card.id))
                if progress is not None and progress.due_at > comparison_time:
                    continue
            selected.append(card)
        return selected

    def topics(self) -> list[str]:
        """Return distinct topics in case-insensitive sorted order."""
        return sorted({card.topic for card in self.cards}, key=str.casefold)
