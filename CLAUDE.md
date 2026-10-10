# Poker-KI fuer unsere Heimrunde

Texas Hold'em (No-Limit). Die App analysiert das Spielverhalten der Mitspieler
(offenes Experiment, alle wissen davon) und leitet eine Gegenstrategie ab.
Forschungsfrage: Spielt eine KI mit Spielerprofilen profitabel gegen die Runde
und schlaegt sie einen Zufalls-Bot? Messung in bb/100 ueber viele Haende.

## Zusammenarbeit
- Nutzer ist Programmier-Anfaenger. Claude schreibt den Code und erklaert nach
  jeder Aenderung kurz auf Deutsch in einfachen Worten, was und warum.
- Bei Entscheidungen (Architektur, Bibliothek, Datenformat) kurz nachfragen.
- Antworten auf Deutsch. Kommentare, Docstrings, Variablennamen auf Deutsch,
  ohne Umlaute (`raenge`, `hoehen`).
- Kleine Schritte: eine Sache fertig und getestet statt fuenf halbe.

## Architektur (verbindlich)
- Python-Kern im Paket `poker/` (deck, bewertung, equity, profile, simulation, ki),
  jeder Baustein eine eigene Datei.
- Logik und Oberflaeche strikt trennen: Kern-Funktionen geben Ergebnisse mit
  `return` zurueck. Kein `print()`/`input()` im Kern, nur in `cli.py`
  (spaeter FastAPI-Server + Web-App/PWA fuers iPhone).
- Startbare Dateien nutzen `if __name__ == "__main__":`.
- Speicher: SQLite (ab Baustein 3).

## Kartendarstellung (verbindlich)
Karte = Tupel `(rang, farbe)`, `rang` 2..14 (11 Bube, 12 Dame, 13 Koenig, 14 Ass),
`farbe` in `"Karo"`, `"Herz"`, `"Pik"`, `"Kreuz"`.

- `erzeuge_deck()` mischt nicht, gemischt wird beim Aufrufer (`random.shuffle`).
- `austeilen()` entfernt Karten mit `pop()` aus dem Deck.
- `random.seed(...)` muss fuer reproduzierbare Experimente nutzbar bleiben.

## Handbewertung
`bewerte_hand(karten)` (5-7 Karten) liefert ein Tupel `(handart, raenge...)`;
bessere Hand = groesserer Wert. Einfache Variante: alle Fuenfer-Kombinationen
(`itertools.combinations`). Optimieren erst bei Bedarf, dann gegen die einfache
Variante testen.

## Fahrplan
1. Karten, Deck, Handbewertung (erledigt)
2. Equity per Monte-Carlo, Standard 10000 Durchlaeufe (erledigt; Referenz AA vs KK ca. 82 %)
3. Spielerprofile & Statistiken (SQLite)
4. Spiel-Simulation mit Bots (inkl. Zufalls-Bot)
5. KI: Spielertypen erkennen, Gegenstrategie
6. Oberflaeche: erst CLI, spaeter Web-App

## Befehle
- Tests: `python -m pytest`
- Demo: `python cli.py` oder `python cli.py 42` (fester Seed)
