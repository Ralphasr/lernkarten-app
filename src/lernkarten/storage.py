"""Atomic JSON persistence with explicit error translation."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lernkarten.exceptions import DeckIOError, InvalidDeckFileError
from lernkarten.models import Deck


class DeckRepository:
    """Read and atomically write a deck JSON file."""

    def __init__(self, path: Path) -> None:
        """Store a normalized file path without touching the filesystem."""
        self.path = path.expanduser().resolve()

    def load(self) -> Deck:
        """Load and validate a deck while preserving useful error context.

        >>> import tempfile
        >>> path = Path(tempfile.gettempdir()) / "missing-lernkarten-deck.json"
        >>> try:
        ...     DeckRepository(path).load()
        ... except DeckIOError as error:
        ...     "nicht gefunden" in str(error)
        True
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise DeckIOError(f"Deck-Datei nicht gefunden: {self.path}") from error
        except OSError as error:
            raise DeckIOError(f"Deck-Datei kann nicht gelesen werden: {error}") from error
        try:
            payload: Any = json.loads(raw)
            return Deck.model_validate(payload)
        except json.JSONDecodeError as error:
            raise InvalidDeckFileError(
                f"Ungueltiges JSON in Zeile {error.lineno}, Spalte {error.colno}."
            ) from error
        except ValidationError as error:
            raise InvalidDeckFileError(f"Ungueltige Deck-Daten: {error}") from error

    def save(self, deck: Deck) -> None:
        """Validate and atomically replace the target file.

        The temporary file lives beside the target, so ``os.replace`` stays on the
        same filesystem and never exposes a half-written deck.
        """
        validated = Deck.model_validate(deck.model_dump(mode="python"))
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                validated.model_dump_json(indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError as error:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise DeckIOError(f"Deck-Datei kann nicht gespeichert werden: {error}") from error

    def load_or_create(self, name: str = "Meine Lernkarten") -> Deck:
        """Load an existing deck or create and save a named empty deck."""
        if self.path.exists():
            return self.load()
        deck = Deck(name=name)
        self.save(deck)
        return deck
