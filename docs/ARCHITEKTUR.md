# Architektur- und Datenentscheidungen

## Verantwortlichkeiten

| Modul | Verantwortung                                      |
|---|----------------------------------------------------|
| `models.py` | Pydantic-Modelle, Typvarianten und Invarianten     |
| `grading.py` | Normalisierung und Auswertung von Antworten        |
| `scheduler.py` | Wiederholungsintervalle und Kartenreihenfolge      |
| `service.py` | Start, Fortsetzung und Abschluss von Lernsitzungen |
| `storage.py` | atomare JSON-Persistenz und Fehlerübersetzung      |
| `import_export.py` | CSV-Austausch und APKG-Adapter                     |
| `statistics.py` | reine Zusammenfassungen und Textdiagramme          |
| `cli.py` | Rich-Darstellung, Eingabedialog und Argumentparser |

## Invarianten

1. Jede Karte hat eine eindeutige UUID.
2. Pflichttexte enthalten nach dem Trimmen mindestens ein Zeichen.
3. Multiple-Choice-Optionen sind nicht leer und unabhängig von Groß-/Kleinschreibung eindeutig.
4. Der Index der richtigen Multiple-Choice-Antwort liegt innerhalb der Optionsliste.
5. Die Zahl richtiger Antworten überschreitet nie die Zahl aller Versuche.
6. Ein aktives Profil existiert im Profilverzeichnis des Decks.
7. Ein Sitzungsindex liegt zwischen null und der Zahl ausgewählter Karten.

## Teststrategie

- Unit Tests prüfen lokale Regeln und Fehlerfälle.
- Integrationstests prüfen JSON-, CSV- und SQLite/APKG-Grenzen.
- Doctests halten kurze Verwendungsbeispiele ausführbar.
- Hypothesis prüft Eigenschaften über viele automatisch erzeugte Texte und Fortschrittszähler.
- CLI-Tests rufen den echten Einstiegspunkt mit temporären Dateien auf.

Der interaktive Dialog selbst wird bewusst nicht vollständig simuliert. Die darin aufgerufene
Logik liegt in separat getesteten Diensten; Black-Box-Tests decken die skriptbaren CLI-Pfade ab.

