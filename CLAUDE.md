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
- Statistik zaehlt nur Haende mit `haende.abgeschlossen = 1` (gesetzt in `abrechnen`);
  abgebrochene Haende bleiben gespeichert, werden aber nicht gewertet.
- Mindest-Erhoehung: Bet >= Big Blind, Raise um >= letzte volle Erhoehung, All-in
  immer erlaubt; zu kleines All-in oeffnet nicht wieder (`haben_gehandelt`).
- Karten-Eingabe: Rang (2-9, T/10, J/B, Q/D, K, A) + Farbe (s, h, d, c),
  z. B. "As Kh" (`lies_karten` in `poker/deck.py`).

## Turnier-Timer, Clock, Kasse (Web-App)
- Kern: `poker/turnier.py` (Blindstruktur, Timer, Vorlagen), `poker/clock.py`
  (Clock Call), `poker/kasse.py` (Turnier-/Cash-Buy-ins, Bilanz).
- Zeit immer als Parameter `jetzt`; Restzeit = `ende - jetzt` (nie herunterzaehlen).
  `aktualisiere(..., jetzt)` liefert faellige Ansagen {"zeit", "text", "art"}.
- Geld immer in Cent als ganze Zahl. Cash: Buy-in 10 Euro, Chips 10/25/50/100 ct.
- Cash-Rebuy per Knopf beim Spieler (beliebig oft, Betrag aus dem Buy-in-Feld); Namen
  werden beim Buchen abgeglichen (`_gleicher_name`: "ben " -> "Ben"), auch im Turnier.
- Gemeinsam abrechnen (Reiter "Bilanz"): `kasse.gemeinsamer_ausgleich(abend_ids)` addiert pro
  Spieler die Ergebnisse mehrerer abgeschlossener Abende (Turnier + Cash) und rechnet daraus
  `ausgleichszahlungen`; Endpunkt `POST /api/ausgleich`. Vorschlag: alle Abende vom neuesten Datum.
  Turnier: Chips 25/100/500/1000, Startstack 3000 (Blinds durch 25 teilbar).
- Turnier-Plaetze: Ausscheiden = Anzahl noch im Spiel; spaetes Buy-in schiebt alle schon
  Ausgeschiedenen einen Platz nach hinten (nach dem Sieger kein Buy-in mehr);
  `turnier_abschliessen` prueft mit `pruefe_plaetze`, dass 1..N je genau einmal vergeben sind.
- Der Web-Server haelt Timer/Clock im Speicher und nummeriert Ansagen; die
  Web-App in `web/` fragt alle 250 ms ab. Nur das Geraet mit "Dieses Geraet steuert"
  zeigt Knoepfe und spricht (Web Speech API), Piepton per Web Audio API.

## Live-Abend in der Web-App (Reiter "Hand")
- `poker/tisch.py` verwaltet den Abend um `live.py` herum (live.py bleibt unveraendert):
  Spieler/Sitzordnung, Stacks, Blinds, Aussetzer, Button wandert nach jeder Hand.
- Betraege in Cent (ganze Zahlen); der Server rechnet Euro-Eingaben um.
- Rueckgaengig: vor jeder Aktion/Board-Karte wird der Zustand kopiert
  (`zwischenstaende`); `rueckgaengig` stellt ihn her und loescht die letzte
  Aktion in der DB (`letzte_aktion_loeschen`) bzw. setzt das Board zurueck.
- Abend wird in `tisch_zustand` gespeichert; eine laufende Hand geht bei Neustart
  verloren (abgeschlossen = 0, zaehlt nicht).
- Web: `web/live.js` (nach `app.js` geladen), Endpunkte unter `/api/abend/...`.
  Bestaetigungen per zweitem Tippen (`bestaetigt`), kein `confirm()`.

## KI-Berater (Live-Tisch)
- `poker/berater.py`: `empfehlung(verbindung, abend)` fuer den Helden (`abend["held"]`,
  Karten in `abend["hand"]["held_karten"]`), wenn er dran ist. Nutzt `ki_bewertung`
  (Entscheidung + Equity + Pot Odds + Begruendung) mit Gegnerprofilen aus der DB.
- Fester Zufalls-Startwert pro Situation (Hand, Verlauf, Board) -> gleiche Empfehlung;
  2000 Equity-Durchlaeufe; Raise auf zahlbare Chips (Small Blind) gerundet.
- Web: Knopf "KI" zwischen den Haenden, Kartenraster fuer die Heldenkarten,
  Empfehlungs-Kasten mit "Uebernehmen" (traegt die Aktion normal ein).
- Protokoll: `berater.empfehlung` merkt sich die Empfehlung samt Situation
  (`situation_von`); handelt der Held in genau dieser Situation, schreibt
  `tisch.aktion` eine Zeile in `empfehlungen` (befolgt ja/nein); Rueckgaengig loescht sie.
- `profile.showdown_statistik`: WTSD, W$SD, Bluff-Anteil (River-Einsatz beim Showdown
  mit nur "hoechster Karte" oder verloren ohne gezeigte Karten; Untergrenze).

## Sicherung und Aufraeumen (Reiter "Daten")
- `poker/wartung.py`: Sicherung per SQLite-backup in `sicherungen/` neben der DB
  (beim Serverstart und vor jedem Loeschen, die letzten 30 bleiben).
- Spieler loeschen entfernt alle Haende, in denen er spielte (komplett, auch fuer
  Mitspieler); steht er in einem Turnier/Cash Game, muss erst der Abend weg;
  Spieler am laufenden Live-Abend sind geschuetzt. Abende und abgebrochene Haende
  (ausser der laufenden) lassen sich ebenfalls loeschen.

## Analyse-Modus (Reiter "Analyse")
- `poker/analyse.py`: Verlauf pro Abend (Datum), Gewinnkurve (aufsummierte BB),
  KI-Auswertung (Hand "befolgt", wenn jede protokollierte Entscheidung befolgt),
  Fehlentscheidungen (teuerste zuerst), teuerste Haende, Gegner mit Typ + `ANPASSUNG`-Tipps.
- Nur abgeschlossene Haende mit Ergebnis, alles in Big Blinds. Endpunkt `/api/analyse/{name}`,
  Web: `web/analyse.js` (nach `live.js` geladen), Gewinnkurve als SVG mit Antipp-Anzeige.

## Hand-Analyse und Odds-Tisch (Reiter "Analyse": Spieler | Haende | Tisch)
- `poker/handanalyse.py`: `analysiere_hand` rechnet eine gespeicherte Hand Strasse fuer
  Strasse nach (Pot/zu callen aus den Aktionen, Blinds Platz 0/1): Equity "wirklich"
  (gegen echte Karten, nur wenn alle aktiven Gegner bekannt; ab Flop exakt ausgezaehlt),
  "zufall" und "bereich" (`schaetze_bereich`), Outs, Pot Odds + Urteil bei jeder Entscheidung.
- Fester Startwert pro Hand -> reproduzierbar. `hand_liste` = abgeschlossene Haende mit
  bekannten Karten; `odds_rechner` fuer freie Eingabe (1 Hand -> gegen Zufall).
- Endpunkte `/api/haende/{heimrunde|lerntisch}[/{hand_id}]`, `/api/odds`;
  Web: `web/handanalyse.js` (nach `lerntisch.js`, ersetzt `ladeAnalyse` durch den Umschalter).
- Ansicht "Tisch" (`web/tischrechner.js`): 9 Plaetze um einen Tisch, antippen = dabei, Leiste mit
  Kartenraster; Plaetze ohne Karten = unbekannte Hand. `odds_verlauf(haende, board, zufalls_gegner)`
  liefert Equity Preflop/Flop/Turn/River (`equity_gemischt`: bekannte + zufaellige Haende),
  Endpunkt `POST /api/odds/verlauf`. Knoepfe am Tisch mit CSS `translate` positionieren
  (nicht `transform`, das ueberschreibt `button:active { transform: scale() }`).

## Lerntisch (Reiter "Lernen")
- `poker/lerntisch.py`: ueben mit Spielgeld gegen Bots (Blinds 10/10 ct, 10 Euro, pleite ->
  neue 10 Euro). Echte Spieler ab 20 Haenden werden nachgeahmt (`nachahmer_werte`: Typ-Bot-Werte,
  VPIP/PFR/Aggression auf ihre Statistik umgerechnet), sonst naechster Grundtyp; dazu Typ-Bots.
- Eigene Datenbank `<name>_lerntisch.db` neben der echten; Spiel nur im Speicher des Servers.
- `schritt` = eine Bot-Aktion / neue Karten / Abrechnung (Web fragt alle 600 ms);
  `held_aktion` berechnet vorher den KI-Tipp (`berater.bewerte_situation`), zeigt ihn erst
  danach und protokolliert in `empfehlungen`. Die KI kennt echte Spieler aus der Heimrunde-DB.
- Web: `web/lerntisch.js` (nach `analyse.js` geladen), Endpunkte unter `/api/lerntisch/...`.

## Simulation und Bots
- Bot = Funktion `bot(sicht, zufall) -> (grundaktion, betrag)`; die Sicht
  (`erstelle_sicht` in `poker/bots.py`) enthaelt nur, was ein Spieler sehen darf.
- `poker/simulation.py` spielt mit den Regeln aus `live.py`, speichert in
  `simulation.db` (inkl. aller Handkarten), Stacks jede Hand 100 BB.
- Zufalls-Bot: gleichverteilt ueber `erlaubte_aktionen`, Raise halber Pot/Pot/All-in.
  Equity-Bot: nur Equity gegen zufaellige Gegnerhaende, keine Profile.
- `bewerte_hand` ist die schnelle Version; `bewerte_hand_einfach` bleibt als
  Referenz und wird in den Tests an Zufallshaenden verglichen.

## KI (Baustein 5)
- `poker/bereiche.py`: Starthaende nach Chen-Formel geordnet, Bereich "beste X %".
- `poker/typen.py`: Typ-Bots felsen/station/maniac/tag mit Streuung, `misch` als
  Pruefung (nicht in den KI-Prototypen).
- `poker/ki.py`: Erkennung = naechster Prototyp (VPIP, PFR, Aggressionsanteil),
  Sicherheit = Datenlage x Trennschaerfe x Passung, unter 20 Haenden "unbekannt".
  Gegnerbereiche aus Typ + Aktionen, gemischt mit Standard je nach Sicherheit;
  Equity gegen Bereiche; Anpassungen immer mit der Sicherheit gewichtet.
- Prototypen je Tischgroesse 2-9 gemessen (`poker/messung.py`, `PROTOTYPEN_NACH_GROESSE`);
  `berechne_statistik` liefert `tischgroessen` {spieler: haende}, `prototypen_fuer` mischt
  die Prototypen danach gewichtet. Aendern sich die Typ-Bots: `python cli.py messen`.
- `abstand` erlaubt mehr Abweichung, je weniger Haende/Aktionen hinter einem Wert stehen
  (Zufallsschwankung p(1-p)/n), sonst kippen Felsen mit 3 Flop-Aktionen zum TAG.
- Duplicate-Modus: gleiche Karten, rotierte Plaetze; Unsicherheit ueber Verteilungen.

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
4. Spiel-Simulation mit Bots (erledigt: Zufalls-Bot, Equity-Bot, `simulation.db`)
5. KI: Spielertypen erkennen, Gegenstrategie (regelbasiert erledigt, ML spaeter)
6. Oberflaeche: CLI und Web-App (Timer, Clock, Kasse, Live-Abend)

## Befehle
- Tests: `python -m pytest`
- Demo: `python cli.py` oder `python cli.py 42` (fester Seed)
- Live-Modus: `python cli.py live` (Datenbank `heimrunde.db`)
- Simulation: `python cli.py sim 1000 zufall,equity,equity 42` (Haende, Bots, Seed),
  `--duplicate` fuer den Duplicate-Modus; Bots: zufall, equity, felsen, station,
  maniac, tag, misch, ki
- Prototypen neu messen: `python cli.py messen [haende] [seed]` (Ausgabe in `poker/ki.py` einfuegen)
- Web-App: `python server.py`, dann auf dem iPhone `http://<IP-des-PCs>:8000`
- Entwicklungsmodus: `python server.py test.db --entwicklung` (Server startet bei
  .py-Aenderungen neu, Browser laedt bei Aenderungen in web/ selbst neu; braucht `watchfiles`)
