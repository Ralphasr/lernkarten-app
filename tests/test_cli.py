"""Black-box style tests for non-interactive command dispatch."""

from pathlib import Path

from lernkarten.cli import main


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
