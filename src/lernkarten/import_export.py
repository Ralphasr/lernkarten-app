"""CSV exchange and a safe subset of Anki ``.apkg`` imports."""

from __future__ import annotations

import csv
import html
import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lernkarten.exceptions import DeckIOError, ImportDeckError
from lernkarten.grading import expected_answer
from lernkarten.models import (
    Card,
    CardType,
    Deck,
    MultipleChoiceCard,
    QuestionAnswerCard,
    TrueFalseCard,
)

CSV_FIELDS = ("type", "topic", "prompt", "answer", "choices", "tags")
ANKI_FIELD_SEPARATOR = "\x1f"


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Result of a tolerant multi-row import."""

    imported: int
    skipped: int
    errors: tuple[str, ...] = ()


def _card_to_row(card: Card) -> dict[str, str]:
    """Convert a card into the stable CSV exchange schema."""
    choices = ""
    answer = expected_answer(card)
    if isinstance(card, MultipleChoiceCard):
        choices = json.dumps(card.choices, ensure_ascii=False)
    return {
        "type": card.type.value,
        "topic": card.topic,
        "prompt": card.prompt,
        "answer": answer,
        "choices": choices,
        "tags": json.dumps(card.tags, ensure_ascii=False),
    }


def export_csv(deck: Deck, path: Path) -> None:
    """Export every card as UTF-8 CSV usable by spreadsheet applications."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(_card_to_row(card) for card in deck.cards)
    except OSError as error:
        raise DeckIOError(f"CSV-Datei kann nicht geschrieben werden: {error}") from error


def _json_string_list(value: str, *, field_name: str) -> list[str]:
    """Parse a JSON list containing only strings."""
    if not value.strip():
        return []
    parsed: Any = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        msg = f"{field_name} muss eine JSON-Liste aus Texten sein"
        raise ValueError(msg)
    return parsed


def _row_to_card(row: dict[str, str | None]) -> Card:
    """Validate one CSV row and construct its discriminated card variant."""
    card_type = CardType(row.get("type") or "")
    topic = row.get("topic") or ""
    prompt = row.get("prompt") or ""
    answer = row.get("answer") or ""
    tags = _json_string_list(row.get("tags") or "", field_name="tags")
    if card_type is CardType.QUESTION_ANSWER:
        return QuestionAnswerCard(topic=topic, prompt=prompt, answer=answer, tags=tags)
    if card_type is CardType.MULTIPLE_CHOICE:
        choices = _json_string_list(row.get("choices") or "", field_name="choices")
        normalized = [choice.casefold() for choice in choices]
        try:
            correct_index = normalized.index(answer.strip().casefold())
        except ValueError as error:
            raise ValueError(
                "answer muss exakt einer Multiple-Choice-Option entsprechen"
            ) from error
        return MultipleChoiceCard(
            topic=topic,
            prompt=prompt,
            choices=choices,
            correct_index=correct_index,
            tags=tags,
        )
    try:
        boolean_answer = {
            "wahr": True,
            "true": True,
            "1": True,
            "falsch": False,
            "false": False,
            "0": False,
        }[answer.strip().casefold()]
    except KeyError as error:
        raise ValueError("answer muss fuer Wahr/Falsch 'Wahr' oder 'Falsch' sein") from error
    return TrueFalseCard(topic=topic, prompt=prompt, answer=boolean_answer, tags=tags)


def import_csv(deck: Deck, path: Path) -> ImportReport:
    """Import valid CSV rows and report invalid rows instead of aborting everything.

    >>> deck = Deck(name="D")
    >>> report = ImportReport(imported=2, skipped=1, errors=("Zeile 3",))
    >>> (report.imported, report.skipped, len(deck.cards))
    (2, 1, 0)
    """
    imported = 0
    errors: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = set(CSV_FIELDS) - set(reader.fieldnames or [])
            if missing:
                raise ImportDeckError(f"CSV-Spalten fehlen: {', '.join(sorted(missing))}")
            for line_number, row in enumerate(reader, start=2):
                try:
                    card = _row_to_card(row)
                    deck.add_card(card)
                    imported += 1
                except (ValidationError, ValueError) as error:
                    errors.append(f"Zeile {line_number}: {error}")
    except OSError as error:
        raise ImportDeckError(f"CSV-Datei kann nicht gelesen werden: {error}") from error
    return ImportReport(imported=imported, skipped=len(errors), errors=tuple(errors))


def _plain_anki_text(value: str) -> str:
    """Convert common Anki HTML field content into readable plain text."""
    with_breaks = re.sub(r"(?i)<br\s*/?>|</div>|</p>", "\n", value)
    without_tags = re.sub(r"<[^>]+>", "", with_breaks)
    return html.unescape(without_tags).strip()


def _cloze_pair(front: str, back: str) -> tuple[str, str]:
    """Turn Anki cloze markers into a question and visible answer."""
    marker = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
    answers = [match.group(1) for match in marker.finditer(front)]
    question = marker.sub(lambda match: f"[{match.group(2) or '...'}]", front)
    answer = "; ".join(answers) or back
    return question, answer


def _extract_anki_database(archive: zipfile.ZipFile, target: Path) -> Path:
    """Extract only a recognized SQLite collection member, preventing zip slip."""
    supported = ("collection.anki21", "collection.anki2")
    for name in supported:
        if name in archive.namelist():
            output = target / name
            output.write_bytes(archive.read(name))
            return output
    if "collection.anki21b" in archive.namelist():
        raise ImportDeckError(
            "Komprimierte Anki-2.1.50+-Sammlung erkannt. Bitte in Anki als "
            "unkomprimiertes .apkg oder als CSV exportieren."
        )
    raise ImportDeckError("Das APKG enthaelt keine unterstuetzte Anki-Sammlung.")


def import_anki_package(deck: Deck, path: Path, *, topic: str | None = None) -> ImportReport:
    """Import basic and cloze Anki notes from an uncompressed ``.apkg`` archive.

    Media are intentionally ignored because this terminal project stores text cards.
    Malformed notes are skipped and disclosed in the returned report.
    """
    imported = 0
    errors: list[str] = []
    deck_topic = (topic or path.stem).strip()
    if not deck_topic:
        raise ImportDeckError("Fuer den Anki-Import wird ein Thema benoetigt.")
    try:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as directory:
            database_path = _extract_anki_database(archive, Path(directory))
            connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT id, flds, tags FROM notes ORDER BY id").fetchall()
            finally:
                connection.close()
    except (OSError, zipfile.BadZipFile, sqlite3.Error) as error:
        raise ImportDeckError(f"Anki-Paket kann nicht gelesen werden: {error}") from error

    existing = {
        (card.topic.casefold(), card.prompt.casefold(), expected_answer(card).casefold())
        for card in deck.cards
    }
    for note_id, fields, raw_tags in rows:
        try:
            parts = str(fields).split(ANKI_FIELD_SEPARATOR)
            if len(parts) < 2:
                raise ValueError("weniger als zwei Felder")
            front = _plain_anki_text(parts[0])
            back = _plain_anki_text(parts[1])
            if "{{c" in front:
                front, back = _cloze_pair(front, back)
            tags = [tag for tag in str(raw_tags).strip().split() if tag]
            card = QuestionAnswerCard(topic=deck_topic, prompt=front, answer=back, tags=tags)
            key = (card.topic.casefold(), card.prompt.casefold(), card.answer.casefold())
            if key in existing:
                errors.append(f"Anki-Notiz {note_id}: Duplikat uebersprungen")
                continue
            deck.add_card(card)
            existing.add(key)
            imported += 1
        except (ValidationError, ValueError) as error:
            errors.append(f"Anki-Notiz {note_id}: {error}")
    return ImportReport(imported=imported, skipped=len(errors), errors=tuple(errors))
