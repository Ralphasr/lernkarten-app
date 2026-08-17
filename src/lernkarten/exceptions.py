"""Anwendungsspezifische, gut behandelbare Ausnahmen."""


class LernkartenError(Exception):
    """Basisklasse fuer erwartbare Fehler der Anwendung."""


class DeckIOError(LernkartenError):
    """Eine Deck-Datei konnte nicht gelesen oder geschrieben werden."""


class InvalidDeckFileError(DeckIOError):
    """Eine Datei ist syntaktisch oder inhaltlich kein gueltiges Deck."""


class CardNotFoundError(LernkartenError):
    """Die angeforderte Karte existiert nicht im Deck."""


class InvalidAnswerError(LernkartenError):
    """Eine Antwort kann fuer den Kartentyp nicht interpretiert werden."""


class EmptySelectionError(LernkartenError):
    """Ein Lernmodus wurde ohne passende Karten gestartet."""


class ImportDeckError(LernkartenError):
    """Eine externe Datei kann nicht als Lernkarten importiert werden."""
