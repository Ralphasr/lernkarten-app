# Lernkarten-App

**Deutsch** | [English](README.en.md)

Eine vollständige Python-Anwendung zum Erstellen, Speichern und Lernen digitaler
Karteikarten. Die Terminaloberfläche basiert auf `rich`; persistente Daten werden durch
`pydantic` validiert und atomar als JSON gespeichert.

Das Projekt entstand als Hausarbeit im Modul **Einführung in Python** an der
Heinrich-Heine-Universität Düsseldorf.

## Funktionsumfang

- drei Kartentypen: Frage-Antwort, Multiple Choice und Wahr/Falsch
- Karten erstellen, bearbeiten, löschen, suchen und nach Thema oder Typ filtern
- feste, zufällige (mit optionalem Seed) und adaptive Lernreihenfolge
- SM-2-inspirierte Wiederholungsintervalle und Fälligkeitsverwaltung
- Erfolgsquote, Sitzungsstatistik und Terminaldiagramme
- mehrere unabhängige Benutzerprofile
- unterbrochene Sitzungen nach jeder Antwort sicher fortsetzen
- validierte, atomare JSON-Speicherung
- CSV-Import und -Export
- Import einfacher und Cloze-basierter Anki-Decks (`.apkg`)
- verständliche Fehlerbehandlung für Eingaben und Dateien
- Unit Tests, Doctests und generative Property-Tests

## Schnellstart mit uv

Voraussetzung ist Python 3.11 oder neuer. Das Projekt verwendet ausschließlich die in
`pyproject.toml` erfassten externen Abhängigkeiten. `json`, `pathlib`, `random`, `sqlite3` und
`zipfile` gehören zur Python-Standardbibliothek und werden deshalb nicht als Pakete aufgeführt.

```bash
git clone https://github.com/Ralphasr/lernkarten-app
cd lernkarten-app
uv sync --extra dev
uv run lernkarten --file data/mein_deck.json demo
uv run lernkarten --file data/mein_deck.json interactive
```

Alternativ mit `venv` und `pip`:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
lernkarten --file data/mein_deck.json demo
lernkarten --file data/mein_deck.json interactive
```

`demo` schützt vorhandene Dateien. Nur `demo --force` ersetzt eine existierende Deck-Datei.

## Bedienung

Ohne Unterbefehl startet die vollständige rich Oberfläche:

```bash
lernkarten --file data/mein_deck.json
```

Die wichtigsten skriptbaren Befehle:

```bash
# Leeres Deck erstellen
lernkarten --file data/mein_deck.json init --name "Python-Deck"

# Suchen und filtern
lernkarten --file data/mein_deck.json list --query "Funktion" --topic Syntax
lernkarten --file data/mein_deck.json list --type multiple_choice --due

# Lernen; :pause speichert und beendet eine Sitzung
lernkarten --file data/mein_deck.json study --order adaptive --limit 10
lernkarten --file data/mein_deck.json study --order random --seed 42

# Statistik und Diagramme
lernkarten --file data/mein_deck.json stats

# Austauschformate
lernkarten --file data/mein_deck.json export-csv export/karten.csv
lernkarten --file data/mein_deck.json import-csv import/karten.csv
lernkarten --file data/mein_deck.json import-anki import/mein_deck.apkg --topic Biologie
```

Im interaktiven Menü sind zusätzlich Bearbeiten, Löschen, Profilauswahl sowie Import und Export
verfügbar. Falsche Antworten zählen als Lernversuch; nicht interpretierbare Eingaben (zum
Beispiel `vielleicht` bei Wahr/Falsch) werden erneut abgefragt und beenden das Programm nicht.

## Anki-Import und Prior Art

[Anki](https://apps.ankiweb.net/) ist ein etabliertes Lernkartensystem und damit die wichtigste
Prior-Art-Referenz. Diese Anwendung versucht nicht, Anki vollständig nachzubauen. Sie übernimmt
die sinnvolle Idee der Wiederholungen, setzt sie aber in einer kleinen,
nachvollziehbaren Python-Anwendung um.

Der Import liest Text aus `collection.anki2` und `collection.anki21` innerhalb eines `.apkg`.
Einfache Vorder-/Rückseiten und Cloze-Markierungen werden zu Frage-Antwort-Karten. Medien und
komprimierte `collection.anki21b`-Datenbanken werden bewusst nicht verarbeitet. Für solche Decks
zeigt die App eine Erklärung und empfiehlt einen nicht-komprimierten APKG- oder CSV-Export aus Anki.
Fehlerhafte Einzelnotizen werden übersprungen und im Importbericht genannt.

## Architektur

```text
Rich-CLI (cli.py)
       |
       v
Anwendungsdienst (service.py) ---> Bewertung (grading.py)
       |                         -> Terminplanung (scheduler.py)
       v
Domänenmodelle (models.py) <----> JSON-Repository (storage.py)
       |
       +------------------------> CSV-/Anki-Adapter (import_export.py)
       +------------------------> Statistik (statistics.py)
```

Die Trennung verhindert, dass Tests von Terminaleingaben oder Dateizugriffen abhängen. Das
`Deck` ist die zentrale, von Pydantic validierte Aggregatwurzel. Eine diskriminierte Union sorgt
dafür, dass JSON beim Laden wieder den richtigen Kartentyp erhält.

Design-by-Contract wird ohne zusätzliche Laufzeitbibliothek umgesetzt:

- Pydantic-Validatoren sichern Invarianten (zum Beispiel eindeutige Karten-IDs und gültige
  Multiple-Choice-Indizes).
- öffentliche Operationen prüfen Vorbedingungen (zum Beispiel mindestens eine Karte pro
  Lernsitzung und positive Diagrammbreite).
- spezifische Exceptions bilden erwartbare Fehler ab.

Das Repository schreibt zunächst eine temporäre Datei im Zielordner und ersetzt danach die alte
Datei atomar. Ein Absturz während des Schreibens hinterlässt dadurch keine halbe JSON-Datei.

## Lernalgorithmus

Die adaptive Reihenfolge bevorzugt ungesehene, fehleranfällige und überfällige Karten. Für jede
Karte wird eine Priorität aus drei erklärbaren Anteilen berechnet:

```text
Priorität = Ungesehen-Bonus + 3 * Fehlerquote + min(Überfälligkeit, 30) / 10
```

Nach einer richtigen Antwort folgen Intervalle von einem, drei und anschließend ungefähr
`vorheriges Intervall * ease_factor` Tagen. Eine falsche Antwort setzt die Erfolgsserie zurück,
senkt den Ease-Faktor (nicht unter 1,3) und plant die Karte für den Folgetag. Es handelt sich um
eine bewusst vereinfachte, SM-2-inspirierte Faustregel, nicht um eine kompatible Anki-Planung.

## Qualitätssicherung

Alle Befehle werden aus dem Projektverzeichnis ausgeführt:

```bash
uv run pytest
uv run mypy --strict src tests
uv run ruff check src tests
uv run ruff format --check src tests
uv run interrogate src
```

Stand der mitgelieferten Version:

| Prüfung | Ergebnis |
|---|---:|
| pytest inkl. Doctests | 46 bestanden |
| Hypothesis | 2 generative Eigenschaften geprüft |
| Testabdeckung | 70 % (inkl. interaktiver CLI) |
| mypy `--strict` | 0 Fehler |
| ruff check | 0 Hinweise |
| ruff format --check | keine Änderungen |
| interrogate | 100 % |

Die Tests umfassen alle Kartentypen, ungültige Modelle, Suche/Filter, Antwortauswertung,
Terminplanung, Profile, Sitzungsfortsetzung, JSON-Fehler, CSV-Roundtrip, einen echten
SQLite-basierten APKG-Test und die wichtigsten CLI-Befehle.

## Projektstruktur

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

## Grenzen und mögliche Erweiterungen

- Medien aus Anki werden nicht importiert.
- Freitextantworten werden normalisiert, aber semantisch ähnliche Formulierungen nicht erkannt.
- Der adaptive Algorithmus ist erklärbar und getestet, aber nicht empirisch optimiert.
- Eine spätere Streamlit-Oberfläche könnte denselben Anwendungsdienst wiederverwenden.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
