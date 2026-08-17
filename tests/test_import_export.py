"""Round-trip, tolerance and Anki-compatibility tests."""

import sqlite3
import zipfile
from pathlib import Path

from lernkarten.import_export import export_csv, import_anki_package, import_csv
from lernkarten.models import Deck, MultipleChoiceCard, QuestionAnswerCard, TrueFalseCard


def test_csv_round_trip_all_types(tmp_path: Path) -> None:
    """The exchange format retains all essential data for every card type."""
    source = Deck(
        name="D",
        cards=[
            QuestionAnswerCard(topic="Q", prompt="?", answer="!", tags=["x"]),
            MultipleChoiceCard(topic="M", prompt="?", choices=["A", "B"], correct_index=1),
            TrueFalseCard(topic="W", prompt="?", answer=True),
        ],
    )
    path = tmp_path / "cards.csv"
    export_csv(source, path)

    target = Deck(name="Target")
    report = import_csv(target, path)

    assert report.imported == 3
    assert report.skipped == 0
    assert [card.type for card in target.cards] == [card.type for card in source.cards]


def test_csv_import_skips_only_bad_rows(tmp_path: Path) -> None:
    """One malformed row does not discard valid neighboring rows."""
    path = tmp_path / "mixed.csv"
    path.write_text(
        "type,topic,prompt,answer,choices,tags\n"
        'question_answer,T,Good,Yes,,"[]"\n'
        'multiple_choice,T,Bad,C,"[\\"A\\", \\"B\\"]","[]"\n',
        encoding="utf-8",
    )
    deck = Deck(name="D")

    report = import_csv(deck, path)

    assert report.imported == 1
    assert report.skipped == 1
    assert len(report.errors) == 1


def _create_anki_package(path: Path) -> None:
    """Create a minimal legitimate SQLite-backed Anki archive fixture."""
    database = path.with_suffix(".anki2")
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT)")
        connection.executemany(
            "INSERT INTO notes VALUES (?, ?, ?)",
            [
                (1, "Capital of France?\x1fParis", " geography "),
                (2, "{{c1::list}} is mutable.\x1f", " python "),
                (3, "Only one field", " broken "),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(database, "collection.anki2")


def test_anki_apkg_imports_basic_and_cloze_notes(tmp_path: Path) -> None:
    """The APKG adapter reads real SQLite notes and reports malformed entries."""
    path = tmp_path / "sample.apkg"
    _create_anki_package(path)
    deck = Deck(name="D")

    report = import_anki_package(deck, path, topic="Anki")

    assert report.imported == 2
    assert report.skipped == 1
    assert all(isinstance(card, QuestionAnswerCard) for card in deck.cards)
    second_card = deck.cards[1]
    assert isinstance(second_card, QuestionAnswerCard)
    assert second_card.prompt == "[...] is mutable."
    assert "list" in second_card.answer
