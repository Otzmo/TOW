# OTZMO-TOW

Spielhilfe für **Warhammer: The Old World** – live unter **https://otzmo.github.io/TOW/**

## Inhalt der Seite

| Bereich | Was es gibt |
| --- | --- |
| **Battle March** | Regeln (Leitfaden) und Armeebau für Battle March |
| **Core Battle** | Regeln, Armeebau und Turnierregeln für Core Battle |
| **Kartenbau** | Gelände-Baukasten für Battle-March- und Core-Battle-Karten |
| **Tools** | Schablonen-, Ansturm- und Zauberrechner, Patzertabelle, Basen-Generator |
| **Termine** | Spieltermine mit Anmeldung, als Kalender abonnierbar |
| **Regelindex** | Alle Regeln von tow.whfb.app zum Nachschlagen, mit Passwort (nur für die Spielgruppe) |

## Aufbau

- `index.html` – die ganze Seite in einer Datei (HTML, CSS, JavaScript), kein Build-Schritt.
- `fonts/` – Schriften lokal (Crimson Pro, IM Fell English SC; SIL Open Font License), keine Google-Anfragen.
- `themes/Alte_Welt.md` – das Design „Tinte auf Pergament“ (Farben, Schriften).
- `regeln/` – der Regelindex. Die Daten in `regeln/daten/` sind verschlüsselt (AES-256-GCM, Schlüssel aus dem Spieler-Passwort).
- `tools/kalender.py` – erzeugt `termine.ics` aus den Terminen in Firebase.
- `tools/regeln/` – lädt die Regeln von tow.whfb.app, bereitet sie auf und verschlüsselt sie.
- `termine.ics`, `termine-2027.ics` – Kalender zum Abonnieren (`termine-2027.ics` für ältere Abos).

## Automatiken (GitHub Actions)

| Workflow | Wann | Was |
| --- | --- | --- |
| `kalender.yml` | alle 15 Minuten | Termine aus Firebase holen, Kalenderdateien bei Änderungen neu schreiben |
| `regeln.yml` | montags früh | Regelindex neu laden und verschlüsseln; braucht das Secret `REGELN_PASSWORT` |

Termine und Anmeldungen liegen in Firebase (Realtime Database, Bereiche `termine` und `anmeldungen`).
GitHub Pages veröffentlicht `main` automatisch.

Die alte Adresse `otzmo.github.io/Battle-March/` leitet über das Repo [Otzmo/Battle-March](https://github.com/Otzmo/Battle-March) hierher weiter.

Nicht mit Games Workshop verbunden.
