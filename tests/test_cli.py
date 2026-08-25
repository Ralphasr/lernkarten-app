"""Black-box style tests for non-interactive command dispatch."""

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from lernkarten.cli import (
    _card_table,
    _interactive,
    _print_statistics,
    _run_study,
    _show_study_card,
    main,
)
from lernkarten.models import (
    Deck,
    MultipleChoiceCard,
    QuestionAnswerCard,
    StudyOrder,
    StudyProfile,
)
from lernkarten.storage import DeckRepository


@pytest.mark.parametrize("text", ["[/red]", "[bold]", "normal [text]"])
def test_user_controlled_card_text_is_rendered_literally(text: str) -> None:
    """Rich markup in card fields remains literal and never breaks rendering."""
    card = MultipleChoiceCard(
        topic=text,
        prompt=text,
        choices=[text, "plain"],
        correct_index=1,
        tags=[text],
    )
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, width=100)

    console.print(_card_table([card]))
    _show_study_card(console, card, 1, 1)

    assert text in stream.getvalue()


def test_deck_profile_topic_and_answer_markup_is_rendered_literally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other persisted user fields remain literal across study and summary views."""
    deck_name = "Deck [/red]"
    profile_name = "Profil [bold]"
    topic = "Thema [mit Klammern]"
    answer = "Antwort [/red]"
    card = QuestionAnswerCard(
        topic=topic,
        prompt="Frage [bold]",
        answer=answer,
        tags=["Tag [/red]"],
    )
    deck = Deck(
        name=deck_name,
        cards=[card],
        profiles={profile_name: StudyProfile(name=profile_name)},
        active_profile=profile_name,
    )
    repository = DeckRepository(tmp_path / "deck.json")
    repository.save(deck)
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    def answer_prompt(*args: object, **kwargs: object) -> str:
        return answer

    monkeypatch.setattr("lernkarten.cli.Prompt.ask", answer_prompt)
    _run_study(console, repository, deck, order=StudyOrder.FIXED)
    _print_statistics(console, deck)

    def exit_prompt(*args: object, **kwargs: object) -> str:
        return "0"

    monkeypatch.setattr("lernkarten.cli.Prompt.ask", exit_prompt)
    _interactive(console, repository)

    output = stream.getvalue()
    assert deck_name in output
    assert profile_name in output
    assert topic in output
    assert answer in output
    assert card.tags == ["Tag [/red]"]


def test_demo_list_stats_and_export_commands(tmp_path: Path) -> None:
    """The installed entry point supports a complete scriptable happy path."""
    deck_path = tmp_path / "deck.json"
    csv_path = tmp_path / "deck.csv"

    assert main(["--file", str(deck_path), "demo"]) == 0
    assert main(["--file", str(deck_path), "list", "--topic", "Syntax"]) == 0
    assert main(["--file", str(deck_path), "stats"]) == 0
    assert main(["--file", str(deck_path), "export-csv", str(csv_path)]) == 0
    assert csv_path.exists()


def test_invalid_file_returns_controlled_exit_code(tmp_path: Path) -> None:
    """Expected user errors do not leak a traceback from main."""
    assert main(["--file", str(tmp_path / "missing.json"), "list"]) == 2


def test_demo_protects_existing_data_without_force(tmp_path: Path) -> None:
    """Creating demo data twice requires an explicit overwrite flag."""
    deck_path = tmp_path / "deck.json"
    assert main(["--file", str(deck_path), "demo"]) == 0
    assert main(["--file", str(deck_path), "demo"]) == 2
    assert main(["--file", str(deck_path), "demo", "--force"]) == 0
