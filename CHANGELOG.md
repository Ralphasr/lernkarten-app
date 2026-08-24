# Changelog

Alle wesentlichen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Unreleased]

Derzeit sind keine weiteren Änderungen geplant.

## [1.0.0] - 2026-08-24

### Funktionen

- drei validierte Kartentypen: Frage-Antwort, Multiple Choice und Wahr/Falsch
- Erstellen, Bearbeiten, Löschen, Suchen und Filtern von Karten
- thematische Filterung und Filterung nach Kartentyp
- fester, zufälliger und adaptiver Lernmodus
- SM-2-inspirierte Wiederholungsintervalle und Fälligkeitsverwaltung
- fortsetzbare Lernsitzungen und mehrere Benutzerprofile
- Lernstatistiken, Erfolgsquoten und Terminaldiagramme
- CSV-Import und -Export
- textbasierter Import einfacher und Cloze-basierter Anki-APKG-Dateien
- validierte und atomare JSON-Speicherung
- Behandlung ungültiger Nutzereingaben und beschädigter Dateien

### Qualitätssicherung

- vollständige Typisierung mit erfolgreicher Prüfung durch `mypy --strict`
- Unit Tests und Doctests mit `pytest`
- generative Property-Tests mit Hypothesis
- Testabdeckung mit `pytest-cov`
- Codeformatierung und statische Prüfung mit Ruff
- Prüfung der Dokumentationsabdeckung mit Interrogate
- Entwicklungsabhängigkeiten und Werkzeugkonfiguration in `pyproject.toml`
- reproduzierbare Abhängigkeitsauflösung durch `uv.lock`

### Dokumentation und Projektdateien

- ausführliche deutschsprachige Projektbeschreibung in `README.md`
- englische Projektdokumentation in `README.en.md`
- Installations- und Bedienungsanleitung für `uv`, `venv` und `pip`
- Beschreibung der Projektarchitektur in `docs/ARCHITEKTUR.md`
- dokumentierte Abgrenzung zu Anki als Prior Art
- Beispielkartenstapel in `data/mein_deck.json`
- MIT-Lizenz in `LICENSE`
- Projektänderungen in `CHANGELOG.md` dokumentiert
