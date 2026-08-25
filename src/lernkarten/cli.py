"""Rich terminal interface and scriptable command-line entry point."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from lernkarten.demo import create_demo_deck
from lernkarten.exceptions import InvalidAnswerError, LernkartenError
from lernkarten.grading import expected_answer, parse_boolean
from lernkarten.import_export import ImportReport, export_csv, import_anki_package, import_csv
from lernkarten.models import (
    Card,
    CardType,
    Deck,
    MultipleChoiceCard,
    QuestionAnswerCard,
    StudyOrder,
    TrueFalseCard,
    utc_now,
)
from lernkarten.service import StudyService
from lernkarten.statistics import activity_by_day, calculate_statistics, text_bar_chart
from lernkarten.storage import DeckRepository

DEFAULT_FILE = Path("data/lernkarten.json")
TYPE_LABELS = {
    CardType.QUESTION_ANSWER: "Frage-Antwort",
    CardType.MULTIPLE_CHOICE: "Multiple Choice",
    CardType.TRUE_FALSE: "Wahr/Falsch",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line contract."""
    parser = argparse.ArgumentParser(
        prog="lernkarten",
        description="Digitale Lernkarten erstellen, importieren und adaptiv lernen.",
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="Pfad zur Deck-JSON-Datei")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Leeres Deck anlegen")
    init_parser.add_argument("--name", default="Meine Lernkarten")

    demo_parser = subparsers.add_parser("demo", help="Beispieldeck mit allen Typen anlegen")
    demo_parser.add_argument("--force", action="store_true", help="Vorhandene Datei ersetzen")

    list_parser = subparsers.add_parser("list", help="Karten suchen und filtern")
    list_parser.add_argument("--query", default="")
    list_parser.add_argument("--topic")
    list_parser.add_argument("--type", choices=[item.value for item in CardType])
    list_parser.add_argument("--due", action="store_true")

    study_parser = subparsers.add_parser("study", help="Lernsitzung starten oder fortsetzen")
    study_parser.add_argument(
        "--order", choices=[item.value for item in StudyOrder], default="adaptive"
    )
    study_parser.add_argument("--topic")
    study_parser.add_argument("--type", choices=[item.value for item in CardType])
    study_parser.add_argument("--due", action="store_true")
    study_parser.add_argument("--limit", type=int)
    study_parser.add_argument("--seed", type=int)

    subparsers.add_parser("stats", help="Fortschritt und Diagramm anzeigen")

    import_csv_parser = subparsers.add_parser("import-csv", help="CSV-Karten importieren")
    import_csv_parser.add_argument("path", type=Path)

    export_csv_parser = subparsers.add_parser("export-csv", help="Karten als CSV exportieren")
    export_csv_parser.add_argument("path", type=Path)

    anki_parser = subparsers.add_parser("import-anki", help="Unkomprimiertes Anki-APKG importieren")
    anki_parser.add_argument("path", type=Path)
    anki_parser.add_argument("--topic")

    subparsers.add_parser("interactive", help="Interaktives Rich-Hauptmenue")
    return parser


def _card_type(value: str | None) -> CardType | None:
    """Convert an optional CLI value into its enum."""
    return CardType(value) if value is not None else None


def _card_table(cards: Sequence[Card]) -> Table:
    """Build a compact card overview table."""
    table = Table(title=f"Karten ({len(cards)})", header_style="bold cyan")
    table.add_column("Nr.", justify="right")
    table.add_column("Thema")
    table.add_column("Typ")
    table.add_column("Vorderseite", overflow="fold")
    for index, card in enumerate(cards, start=1):
        table.add_row(
            str(index),
            escape(card.topic),
            TYPE_LABELS[card.type],
            escape(card.prompt),
        )
    return table


def _print_cards(console: Console, cards: Sequence[Card]) -> None:
    """Print either a card table or a clear empty-result message."""
    if cards:
        console.print(_card_table(cards))
    else:
        console.print("[yellow]Keine passenden Karten gefunden.[/yellow]")


def _print_import_report(console: Console, report: ImportReport) -> None:
    """Display import totals and bounded per-row diagnostics."""
    console.print(f"[green]{report.imported} importiert[/green], {report.skipped} uebersprungen.")
    for error in report.errors[:10]:
        console.print(f"[yellow]- {escape(error)}[/yellow]")
    if len(report.errors) > 10:
        console.print(f"[yellow]... und {len(report.errors) - 10} weitere Hinweise.[/yellow]")


def _print_statistics(console: Console, deck: Deck) -> None:
    """Display summary metrics and a seven-day activity chart."""
    stats = calculate_statistics(deck)
    table = Table(
        title=f"Fortschritt - Profil {escape(deck.active_profile)}",
        header_style="bold green",
    )
    table.add_column("Kennzahl")
    table.add_column("Wert", justify="right")
    table.add_row("Karten", str(stats.cards))
    table.add_row("Faellige Karten", str(stats.due_cards))
    table.add_row("Antworten", str(stats.attempts))
    table.add_row("Richtig", str(stats.correct))
    table.add_row("Erfolgsquote", f"{stats.success_rate:.1f} %")
    table.add_row("Abgeschlossene Sitzungen", str(stats.completed_sessions))
    console.print(table)
    topic_values = {
        escape(topic): count
        for topic, count in sorted(stats.by_topic.items(), key=lambda pair: pair[0].casefold())
    }
    if topic_values:
        console.print(Panel("\n".join(text_bar_chart(topic_values)), title="Karten nach Thema"))
    activity = activity_by_day(deck)
    chart_values = {day.strftime("%d.%m."): count for day, count in activity.items()}
    console.print(Panel("\n".join(text_bar_chart(chart_values)), title="Antworten - letzte 7 Tage"))


def _show_study_card(console: Console, card: Card, position: int, total: int) -> None:
    """Render one study prompt with type-specific answer choices."""
    body = f"[bold]{escape(card.prompt)}[/bold]"
    if isinstance(card, MultipleChoiceCard):
        options = "\n".join(
            f"  {index}. {escape(choice)}" for index, choice in enumerate(card.choices, 1)
        )
        body = f"{body}\n\n{options}"
    console.print(Panel(body, title=f"{escape(card.topic)} - Karte {position}/{total}"))


def _run_study(
    console: Console,
    repository: DeckRepository,
    deck: Deck,
    *,
    order: StudyOrder,
    topic: str | None = None,
    card_type: CardType | None = None,
    due_only: bool = False,
    limit: int | None = None,
    seed: int | None = None,
) -> None:
    """Run or resume a session and persist after every accepted answer."""
    service = StudyService(deck)
    session = deck.active_session
    if session is None or session.is_complete or session.profile_name != deck.active_profile:
        session = service.start_session(
            order=order,
            topic=topic,
            card_type=card_type,
            due_only=due_only,
            limit=limit,
            seed=seed,
        )
        repository.save(deck)
    else:
        console.print("[cyan]Unterbrochene Sitzung wird fortgesetzt.[/cyan]")
    while not session.is_complete:
        card = service.current_card()
        _show_study_card(console, card, session.current_index + 1, len(session.card_ids))
        started = time.monotonic()
        answer = Prompt.ask("Antwort (oder :pause)")
        if answer.strip().casefold() == ":pause":
            repository.save(deck)
            console.print("[cyan]Sitzung gespeichert. Spaeter mit 'study' fortsetzen.[/cyan]")
            return
        try:
            correct = service.submit_answer(
                answer,
                duration_seconds=time.monotonic() - started,
            )
        except InvalidAnswerError as error:
            console.print(f"[yellow]{escape(str(error))}[/yellow]")
            continue
        repository.save(deck)
        style = "green" if correct else "red"
        verdict = "Richtig" if correct else "Leider falsch"
        console.print(f"[{style}]{verdict}.[/{style}] Loesung: {escape(expected_answer(card))}")
        if isinstance(card, TrueFalseCard) and card.explanation:
            console.print(f"[dim]{escape(card.explanation)}[/dim]")
    console.print(
        Panel(
            f"Richtig: {session.correct_count}/{len(session.records)}\n"
            f"Erfolgsquote: {session.success_rate:.1f} %",
            title="Sitzung abgeschlossen",
            border_style="green",
        )
    )


def _select_card(console: Console, deck: Deck) -> Card | None:
    """Let the user select a card by displayed index."""
    if not deck.cards:
        console.print("[yellow]Das Deck enthaelt noch keine Karten.[/yellow]")
        return None
    _print_cards(console, deck.cards)
    index = IntPrompt.ask("Kartennummer", default=1)
    if not 1 <= index <= len(deck.cards):
        console.print("[yellow]Diese Kartennummer existiert nicht.[/yellow]")
        return None
    return deck.cards[index - 1]


def _ask_text(label: str, default: str | None = None) -> str:
    """Ask for required text without leaking Rich's optional default type."""
    return Prompt.ask(label) if default is None else Prompt.ask(label, default=default)


def _prompt_card(existing: Card | None = None) -> Card:
    """Collect and validate all fields for a new or edited card."""
    default_type = existing.type.value if existing is not None else CardType.QUESTION_ANSWER.value
    selected_type = CardType(
        Prompt.ask(
            "Typ",
            choices=[item.value for item in CardType],
            default=default_type,
        )
    )
    topic = Prompt.ask("Thema", default=existing.topic if existing is not None else "Allgemein")
    prompt = _ask_text("Vorderseite", existing.prompt if existing is not None else None)
    default_tags = ", ".join(existing.tags) if existing is not None else ""
    tags = [
        tag.strip() for tag in Prompt.ask("Tags (Komma-getrennt)", default=default_tags).split(",")
    ]
    card_id = existing.id if existing is not None else uuid4()
    created_at = existing.created_at if existing is not None else utc_now()
    if selected_type is CardType.QUESTION_ANSWER:
        default_answer = existing.answer if isinstance(existing, QuestionAnswerCard) else None
        answer = _ask_text("Antwort", default_answer)
        return QuestionAnswerCard(
            id=card_id,
            topic=topic,
            prompt=prompt,
            tags=tags,
            created_at=created_at,
            answer=answer,
        )
    if selected_type is CardType.MULTIPLE_CHOICE:
        default_choices = (
            " | ".join(existing.choices) if isinstance(existing, MultipleChoiceCard) else ""
        )
        choices = [
            choice.strip()
            for choice in Prompt.ask("Optionen (mit | trennen)", default=default_choices).split("|")
        ]
        default_index = (
            existing.correct_index + 1 if isinstance(existing, MultipleChoiceCard) else 1
        )
        correct_index = IntPrompt.ask("Nummer der richtigen Option", default=default_index) - 1
        return MultipleChoiceCard(
            id=card_id,
            topic=topic,
            prompt=prompt,
            tags=tags,
            created_at=created_at,
            choices=choices,
            correct_index=correct_index,
        )
    default_boolean = (
        "wahr" if isinstance(existing, TrueFalseCard) and existing.answer else "falsch"
    )
    answer_bool = parse_boolean(
        Prompt.ask("Loesung", choices=["wahr", "falsch"], default=default_boolean)
    )
    default_explanation = existing.explanation if isinstance(existing, TrueFalseCard) else ""
    explanation = Prompt.ask("Erklaerung", default=default_explanation)
    return TrueFalseCard(
        id=card_id,
        topic=topic,
        prompt=prompt,
        tags=tags,
        created_at=created_at,
        answer=answer_bool,
        explanation=explanation,
    )


def _manage_profiles(console: Console, repository: DeckRepository, deck: Deck) -> None:
    """List, create or switch independent user profiles."""
    console.print(
        f"Profile: {escape(', '.join(deck.profiles))} (aktiv: {escape(deck.active_profile)})"
    )
    action = Prompt.ask("Aktion", choices=["wechseln", "neu", "zurueck"], default="zurueck")
    if action == "wechseln":
        name = Prompt.ask("Profil", choices=list(deck.profiles), default=deck.active_profile)
        deck.active_profile = name
        repository.save(deck)
    elif action == "neu":
        deck.add_profile(Prompt.ask("Neuer Profilname"))
        repository.save(deck)


def _manage_exchange(console: Console, repository: DeckRepository, deck: Deck) -> None:
    """Run interactive CSV or Anki import/export operations."""
    action = Prompt.ask(
        "Aktion",
        choices=["csv-import", "csv-export", "anki-import", "zurueck"],
        default="zurueck",
    )
    if action == "zurueck":
        return
    path = Path(Prompt.ask("Dateipfad"))
    if action == "csv-export":
        export_csv(deck, path)
        console.print(f"[green]CSV geschrieben: {escape(str(path))}[/green]")
        return
    report = import_csv(deck, path) if action == "csv-import" else import_anki_package(deck, path)
    repository.save(deck)
    _print_import_report(console, report)


def _interactive(console: Console, repository: DeckRepository) -> None:
    """Run the complete menu-driven Rich interface."""
    deck = repository.load_or_create()
    console.print(
        Panel.fit(f"[bold cyan]{escape(deck.name)}[/bold cyan]", subtitle="Lernkarten-App")
    )
    while True:
        console.print(
            "\n[bold]1[/bold] Karten  [bold]2[/bold] Hinzufuegen  [bold]3[/bold] Bearbeiten  "
            "[bold]4[/bold] Loeschen  [bold]5[/bold] Lernen  [bold]6[/bold] Suchen  "
            "[bold]7[/bold] Statistik  [bold]8[/bold] Profile  [bold]9[/bold] Import/Export  "
            "[bold]0[/bold] Beenden"
        )
        choice = Prompt.ask("Auswahl", choices=[str(number) for number in range(10)], default="1")
        if choice == "0":
            repository.save(deck)
            return
        if choice == "1":
            _print_cards(console, deck.cards)
        elif choice == "2":
            deck.add_card(_prompt_card())
            repository.save(deck)
        elif choice == "3":
            card = _select_card(console, deck)
            if card is not None:
                deck.replace_card(_prompt_card(card))
                repository.save(deck)
        elif choice == "4":
            card = _select_card(console, deck)
            if card is not None and Confirm.ask(
                f"'{escape(card.prompt)}' wirklich loeschen?", default=False
            ):
                deck.remove_card(card.id)
                repository.save(deck)
        elif choice == "5":
            order = StudyOrder(
                Prompt.ask(
                    "Reihenfolge", choices=[item.value for item in StudyOrder], default="adaptive"
                )
            )
            _run_study(console, repository, deck, order=order)
        elif choice == "6":
            query = Prompt.ask("Suchtext", default="")
            topic = Prompt.ask("Thema (leer = alle)", default="") or None
            _print_cards(console, deck.search(query, topic=topic))
        elif choice == "7":
            _print_statistics(console, deck)
        elif choice == "8":
            _manage_profiles(console, repository, deck)
        elif choice == "9":
            _manage_exchange(console, repository, deck)


def _require_absent(path: Path, *, force: bool = False) -> None:
    """Protect user data from accidental overwrite."""
    if path.exists() and not force:
        from lernkarten.exceptions import DeckIOError

        raise DeckIOError(f"Datei existiert bereits: {path}. Fuer Demo --force verwenden.")


def _dispatch(args: argparse.Namespace, console: Console) -> None:
    """Execute one parsed command."""
    repository = DeckRepository(args.file)
    command = args.command or "interactive"
    if command == "interactive":
        _interactive(console, repository)
        return
    if command == "init":
        _require_absent(repository.path)
        repository.save(Deck(name=args.name))
        console.print(f"[green]Deck angelegt: {escape(str(repository.path))}[/green]")
        return
    if command == "demo":
        _require_absent(repository.path, force=args.force)
        repository.save(create_demo_deck())
        console.print(f"[green]Beispieldeck geschrieben: {escape(str(repository.path))}[/green]")
        return
    deck = repository.load()
    if command == "list":
        cards = deck.search(
            args.query,
            topic=args.topic,
            card_type=_card_type(args.type),
            due_only=args.due,
        )
        _print_cards(console, cards)
    elif command == "study":
        _run_study(
            console,
            repository,
            deck,
            order=StudyOrder(args.order),
            topic=args.topic,
            card_type=_card_type(args.type),
            due_only=args.due,
            limit=args.limit,
            seed=args.seed,
        )
    elif command == "stats":
        _print_statistics(console, deck)
    elif command == "import-csv":
        report = import_csv(deck, args.path)
        repository.save(deck)
        _print_import_report(console, report)
    elif command == "export-csv":
        export_csv(deck, args.path)
        console.print(f"[green]CSV geschrieben: {escape(str(args.path))}[/green]")
    elif command == "import-anki":
        report = import_anki_package(deck, args.path, topic=args.topic)
        repository.save(deck)
        _print_import_report(console, report)
    else:
        _unreachable(command)


def _unreachable(command: str) -> NoReturn:
    """Help static analysis detect an impossible parser state."""
    raise RuntimeError(f"Unbekannter interner Befehl: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and convert expected failures into a non-crashing exit code."""
    console = Console()
    try:
        args = build_parser().parse_args(argv)
        _dispatch(args, console)
        return 0
    except (LernkartenError, ValidationError, ValueError) as error:
        console.print(f"[bold red]Fehler:[/bold red] {escape(str(error))}")
        return 2
    except (KeyboardInterrupt, EOFError):
        console.print(
            "\n[yellow]Abgebrochen. Bereits bestaetigte Aenderungen bleiben gespeichert.[/yellow]"
        )
        return 130
