"""Small built-in deck for an immediate, reproducible first run."""

from lernkarten.models import Deck, MultipleChoiceCard, QuestionAnswerCard, TrueFalseCard


def create_demo_deck() -> Deck:
    """Return a balanced example deck containing every card type."""
    return Deck(
        name="Python-Grundlagen",
        description="Beispieldaten fuer den direkten Test aller Kartentypen.",
        cards=[
            QuestionAnswerCard(
                topic="Syntax",
                prompt="Welches Schluesselwort definiert eine Funktion?",
                answer="def",
                tags=["Funktionen"],
            ),
            QuestionAnswerCard(
                topic="Datentypen",
                prompt="Wie heisst der unveraenderliche Sequenztyp?",
                answer="tuple",
                tags=["Sequenzen"],
            ),
            MultipleChoiceCard(
                topic="Datentypen",
                prompt="Welcher Typ speichert eindeutige Werte ohne feste Reihenfolge?",
                choices=["list", "set", "tuple", "str"],
                correct_index=1,
                tags=["Collections"],
            ),
            MultipleChoiceCard(
                topic="Werkzeuge",
                prompt="Welches Werkzeug prueft Typannotationen statisch?",
                choices=["ruff", "pytest", "mypy", "rich"],
                correct_index=2,
                tags=["Qualitaet"],
            ),
            TrueFalseCard(
                topic="Datentypen",
                prompt="Python-Listen sind veraenderlich.",
                answer=True,
                explanation="Elemente koennen hinzugefuegt, ersetzt und entfernt werden.",
            ),
            TrueFalseCard(
                topic="Syntax",
                prompt="Ein Python-Block wird durch geschweifte Klammern begrenzt.",
                answer=False,
                explanation="Python verwendet Einrueckung zur Blockbildung.",
            ),
        ],
    )
