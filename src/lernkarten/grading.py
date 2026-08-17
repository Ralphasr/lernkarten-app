"""Answer normalization and grading for every supported card type."""

from __future__ import annotations

import re
import unicodedata

from lernkarten.exceptions import InvalidAnswerError
from lernkarten.models import Card, MultipleChoiceCard, QuestionAnswerCard, TrueFalseCard


def normalize_text(value: str) -> str:
    """Normalize Unicode, case and whitespace for forgiving text comparison.

    >>> normalize_text("  Guido   VAN Rossum ")
    'guido van rossum'
    """
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def parse_boolean(value: str) -> bool:
    """Interpret common German and English boolean answers.

    >>> parse_boolean("wahr")
    True
    >>> parse_boolean("Nein")
    False
    """
    normalized = normalize_text(value)
    truthy = {"w", "wahr", "ja", "j", "true", "t", "1"}
    falsy = {"f", "falsch", "nein", "n", "false", "0"}
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise InvalidAnswerError("Bitte 'wahr' oder 'falsch' eingeben.")


def multiple_choice_index(card: MultipleChoiceCard, value: str) -> int:
    """Convert an option number, letter or exact option text into an index.

    >>> card = MultipleChoiceCard(topic="T", prompt="?", choices=["A", "B"], correct_index=1)
    >>> multiple_choice_index(card, "2")
    1
    """
    normalized = normalize_text(value)
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(card.choices):
            return index
    if len(normalized) == 1 and "a" <= normalized <= "z":
        index = ord(normalized) - ord("a")
        if 0 <= index < len(card.choices):
            return index
    for index, choice in enumerate(card.choices):
        if normalized == normalize_text(choice):
            return index
    raise InvalidAnswerError("Bitte Nummer, Buchstabe oder Text einer vorhandenen Option eingeben.")


def check_answer(card: Card, value: str) -> bool:
    """Grade a textual user response according to the concrete card type.

    >>> check_answer(QuestionAnswerCard(topic="T", prompt="2+2?", answer="4"), " 4 ")
    True
    """
    if isinstance(card, QuestionAnswerCard):
        if not value.strip():
            raise InvalidAnswerError("Die Antwort darf nicht leer sein.")
        return normalize_text(value) == normalize_text(card.answer)
    if isinstance(card, MultipleChoiceCard):
        return multiple_choice_index(card, value) == card.correct_index
    if isinstance(card, TrueFalseCard):
        return parse_boolean(value) is card.answer
    raise TypeError(f"Unbekannter Kartentyp: {type(card).__name__}")


def expected_answer(card: Card) -> str:
    """Return a human-readable expected answer for feedback."""
    if isinstance(card, QuestionAnswerCard):
        return card.answer
    if isinstance(card, MultipleChoiceCard):
        return card.choices[card.correct_index]
    if isinstance(card, TrueFalseCard):
        return "Wahr" if card.answer else "Falsch"
    raise TypeError(f"Unbekannter Kartentyp: {type(card).__name__}")
