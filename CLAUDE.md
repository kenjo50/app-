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
- Speicher: SQLite (`poker/profile.py`). Erfasst wird jede Aktion in jeder
  Strasse mit Betrag (fold/check/call/bet/raise). Blinds stehen in `haende`,
  nicht als Aktion. Karten werden als JSON-Text gespeichert.
- Betraege = Gesamteinsatz des Spielers in der Setzrunde ("raise AUF 6").
  Die App rechnet Call-Betraege selbst aus (`poker/live.py`).
- Reihenfolge: `namen` beginnt mit dem Small Blind. Preflop beginnt Platz 2
  (heads-up Platz 0), ab dem Flop der erste aktive ab Platz 0 (heads-up Platz 1).
  `noch_dran` = wer in der Setzrunde noch handeln muss; bet/raise setzt es
  auf alle anderen aktiven Spieler mit Chips zurueck. `am_zug` ist None, wenn die Runde vorbei ist.
- Stacks: `starte_hand(..., stacks)`; all-in = aktiv mit Stack 0, handelt nicht mehr.
  `berechne_pots` bildet Hauptpot/Side Pots aus den Einsatz-Stufen der aktiven Spieler;
  `showdown_gewinner` und `abrechnen` arbeiten mit einer Gewinnerliste pro Pot.
- Am Ende jeder Hand: Showdown-Karten eingeben -> Gewinner per Handbewertung;
  zeigt keiner, Gewinner direkt angeben. `teilnehmer.investiert/gewonnen`
  ergeben bb/100. Neue Spalten in `NEUE_SPALTEN` eintragen (Nachruesten alter DBs).
- Karten-Eingabe: Rang (2-9, T/10, J/B, Q/D, K, A) + Farbe (s, h, d, c),
  z. B. "As Kh" (`lies_karten` in `poker/deck.py`).

## Turnier-Timer, Clock, Kasse (Web-App)
- Kern: `poker/turnier.py` (Blindstruktur, Timer, Vorlagen), `poker/clock.py`
  (Clock Call), `poker/kasse.py` (Turnier-/Cash-Buy-ins, Bilanz).
- Zeit immer als Parameter `jetzt`; Restzeit = `ende - jetzt` (nie herunterzaehlen).
  `aktualisiere(..., jetzt)` liefert faellige Ansagen {"zeit", "text", "art"}.
- Geld immer in Cent als ganze Zahl. Cash: Buy-in 10 Euro, Chips 10/25/50/100 ct.
  Turnier: Chips 25/100/500/1000, Startstack 3000 (Blinds durch 25 teilbar).
- Der Web-Server haelt Timer/Clock im Speicher und nummeriert Ansagen; die
  Web-App in `web/` fragt alle 250 ms ab. Nur das Geraet mit "Dieses Geraet steuert"
  zeigt Knoepfe und spricht (Web Speech API), Piepton per Web Audio API.

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
3. Spielerprofile & Statistiken (SQLite) + Live-Eingabe (`poker/live.py`) fertig
4. Spiel-Simulation mit Bots (inkl. Zufalls-Bot)
5. KI: Spielertypen erkennen, Gegenstrategie
6. Oberflaeche: erst CLI, spaeter Web-App

## Befehle
- Tests: `python -m pytest`
- Demo: `python cli.py` oder `python cli.py 42` (fester Seed)
- Live-Modus: `python cli.py live` (Datenbank `heimrunde.db`)
- Web-App: `python server.py`, dann auf dem iPhone `http://<IP-des-PCs>:8000`
