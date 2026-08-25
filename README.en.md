# Flashcard App

[Deutsch](README.md) | **English**

A complete Python application for creating, storing, and studying digital
flashcards. The terminal interface is built with `rich`; persistent data is
validated with `pydantic` and stored atomically as JSON.

This project was developed as a term paper for the **Introduction to Python**
course at Heinrich Heine University Düsseldorf.

## Features

- three card types: question and answer, multiple choice, and true or false
- create, edit, delete, search, and filter cards by topic or type
- fixed, random (with an optional seed), and adaptive study order
- SM-2-inspired review intervals and due-date management
- success rates, session statistics, and terminal charts
- multiple independent user profiles
- safely resume interrupted study sessions after every answer
- validated and atomic JSON storage
- CSV import and export
- import of basic and cloze-based Anki decks (`.apkg`)
- clear error handling for invalid input and files
- unit tests, doctests, and generative property-based tests

## Quick Start with uv

Python 3.11 or newer is required. The project exclusively uses the external
dependencies declared in `pyproject.toml`. The modules `json`, `pathlib`,
`random`, `sqlite3`, and `zipfile` are part of the Python standard library and
are therefore not listed as packages.

```bash
git clone https://github.com/Ralphasr/lernkarten-app
cd lernkarten-app
uv sync --extra dev
uv run lernkarten --file data/my_deck.json demo
uv run lernkarten --file data/my_deck.json interactive
```

Alternatively, use `venv` and `pip`:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
lernkarten --file data/my_deck.json demo
lernkarten --file data/my_deck.json interactive
```

The `demo` command protects existing files. Only `demo --force` replaces an
existing deck file.

## Usage

Without a subcommand, the complete Rich terminal interface is started:

```bash
lernkarten --file data/my_deck.json
```

The most important scriptable commands are:

```bash
# Create an empty deck
lernkarten --file data/my_deck.json init --name "Python Deck"

# Search and filter
lernkarten --file data/my_deck.json list --query "function" --topic Syntax
lernkarten --file data/my_deck.json list --type multiple_choice --due

# Study; :pause saves and ends the current session
lernkarten --file data/my_deck.json study --order adaptive --limit 10
lernkarten --file data/my_deck.json study --order random --seed 42

# Statistics and charts
lernkarten --file data/my_deck.json stats

# Exchange formats
lernkarten --file data/my_deck.json export-csv export/cards.csv
lernkarten --file data/my_deck.json import-csv import/cards.csv
lernkarten --file data/my_deck.json import-anki import/my_deck.apkg --topic Biology
```

The interactive menu additionally provides editing, deletion, profile
selection, import, and export functions. Incorrect answers count as study
attempts. Inputs that cannot be interpreted, such as `maybe` for a true-or-false
question, are requested again instead of terminating the program.

## Anki Import and Prior Art

[Anki](https://apps.ankiweb.net/) is an established flashcard system and the
most relevant prior-art reference for this project. This application does not
attempt to recreate Anki in its entirety. It adopts the useful concept of
scheduled reviews while implementing it as a small and understandable Python
application.

The importer reads text from `collection.anki2` and `collection.anki21`
databases contained in an `.apkg` archive. Basic front-and-back notes and cloze
deletions are converted into question-and-answer cards.

Media files and compressed `collection.anki21b` databases are intentionally not
processed. For these decks, the application displays an explanation and
recommends exporting an uncompressed APKG or CSV file from Anki. Malformed
individual notes are skipped and listed in the import report.

## Architecture

```text
Rich CLI (cli.py)
       |
       v
Application service (service.py) ---> Answer grading (grading.py)
       |                            -> Scheduling (scheduler.py)
       v
Domain models (models.py) <--------> JSON repository (storage.py)
       |
       +---------------------------> CSV/Anki adapters (import_export.py)
       +---------------------------> Statistics (statistics.py)
```

This separation prevents the tests from depending on terminal input or direct
file access. The `Deck` is the central aggregate root validated by Pydantic. A
discriminated union ensures that JSON data is converted back into the correct
card type when loaded.

Design by Contract is implemented without an additional runtime library:

- Pydantic validators enforce invariants, including unique card IDs and valid
  multiple-choice indices.
- Public operations check their preconditions, including the requirement of at
  least one card per study session and a positive chart width.
- Specific exceptions represent expected errors.

The repository first writes to a temporary file in the target directory and
then atomically replaces the previous file. As a result, a crash during writing
does not leave behind a partially written JSON file.

## Study Algorithm

The adaptive order prioritizes unseen, error-prone, and overdue cards. Each card
receives a priority score consisting of three understandable components:

```text
priority = unseen bonus + 3 * error rate + min(days overdue, 30) / 10
```

After a correct answer, the intervals are one day, three days, and then
approximately `previous interval * ease_factor` days. An incorrect answer resets
the current streak, lowers the ease factor without allowing it to fall below
1.3, and schedules the card for the following day.

This is an intentionally simplified heuristic inspired by SM-2. It is not
compatible with Anki's scheduling algorithm.

## Quality Assurance

Run all commands from the project directory:

```bash
uv run pytest
uv run mypy --strict src tests
uv run ruff check src tests
uv run ruff format --check src tests
uv run interrogate src
```

Status of the included version:

| Check |                            Result |
|---|----------------------------------:|
| pytest including doctests |                         53 passed |
| Hypothesis |    2 generative properties tested |
| Test coverage | 75% including the interactive CLI |
| mypy `--strict` |                          0 errors |
| ruff check |                        0 warnings |
| ruff format `--check` |                        no changes |
| interrogate |                              100% |

The test suite covers all card types, invalid models, searching and filtering,
answer grading, scheduling, profiles, session resumption, JSON errors, CSV
round trips, a real SQLite-based APKG test, and the most important CLI commands.

## Project Structure

```text
lernkarten-app/
├── data/
│   └── mein_deck.json
├── docs/
│   └── ARCHITEKTUR.md
├── src/lernkarten/
├── tests/
├── pyproject.toml
├── README.md
├── README.en.md
└── LICENSE
```

## Limitations and Possible Extensions

- Media files from Anki are not imported.
- Free-text answers are normalized, but semantically equivalent wording is not
  recognized.
- The adaptive algorithm is understandable and tested, but has not been
  empirically optimized.
- A future Streamlit interface could reuse the same application service.

## License

MIT, see [LICENSE](LICENSE).
