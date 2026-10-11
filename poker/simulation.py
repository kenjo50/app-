"""Simulation: Bots spielen gegeneinander, Ergebnis in bb/100.

Die Bots spielen nach genau denselben Regeln wie der Live-Modus
(poker/live.py: Reihenfolge, Mindest-Erhoehung, Side Pots, ...).
Jede Hand wird in einer eigenen Datenbank gespeichert (Standard:
simulation.db), damit die echten Heimrunden-Daten sauber bleiben.
Gespeichert werden auch alle Handkarten - spaeter wertvoll fuer die KI.

Stacks: Jeder Bot startet jede Hand mit demselben Stack (Standard 100 Big
Blinds), wie ein Cash Game mit automatischem Nachkauf.

Duplicate-Modus: Jede Kartenverteilung wird so oft gespielt, wie Bots am
Tisch sitzen - jedes Mal sitzen die Bots einen Platz weiter. So bekommt
jeder Bot einmal die guten und einmal die schlechten Karten; das Kartenglueck
gleicht sich weitgehend aus und die Unsicherheit (+-) wird kleiner.
"""

import math
import random
import statistics

from poker.bots import BOT_TYPEN, erstelle_sicht
from poker.deck import austeilen, erzeuge_deck
from poker.live import (
    NAECHSTE_STRASSE,
    NEUE_BOARD_KARTEN,
    abrechnen,
    beende_hand,
    gewinner_ohne_showdown,
    naechste_strasse,
    rotiere,
    setzrunde_abgeschlossen,
    showdown_gewinner,
    starte_hand,
    verarbeite_aktion,
)
from poker.ki import erstelle_ki_bot
from poker.profile import handkarten_speichern, naechste_hand_id, oeffne_datenbank
from poker.typen import ALLE_TYPEN, erstelle_typ_bot

STANDARD_DATENBANK = "simulation.db"
STARTSTACK_BB = 100


def oeffne_simulationsdatenbank(pfad=STANDARD_DATENBANK):
    """Oeffnet die Simulations-Datenbank im schnellen Modus.

    synchronous = OFF: SQLite wartet nicht nach jedem Speichern auf die
    Festplatte. Viel schneller; bei einem Stromausfall koennten die letzten
    Haende fehlen - fuer Simulationen egal.
    """
    verbindung = oeffne_datenbank(pfad)
    verbindung.execute("PRAGMA synchronous = OFF")
    verbindung.execute("PRAGMA journal_mode = MEMORY")
    return verbindung


MOEGLICHE_BOTS = list(BOT_TYPEN) + list(ALLE_TYPEN) + ["ki"]


def erzeuge_bot(typ, zufall, verbindung=None):
    """Erzeugt einen Bot. Typ-Bots bekommen dabei ihre gestreuten Werte.

    Die KI braucht die Datenbank (fuer die Gegnerprofile); sie wertet nur
    Haende ab der naechsten Handnummer aus, also nur diese Simulation.
    """
    if typ == "ki":
        if verbindung is None:
            raise ValueError("Die KI braucht eine Datenbank")
        return erstelle_ki_bot(verbindung, naechste_hand_id(verbindung))
    if typ in BOT_TYPEN:
        return BOT_TYPEN[typ]
    if typ in ALLE_TYPEN:
        bot, werte = erstelle_typ_bot(typ, zufall)
        return bot
    raise ValueError(f"Unbekannter Bot '{typ}' (moeglich: {', '.join(MOEGLICHE_BOTS)})")


def erstelle_aufstellung(typen, zufall=random, verbindung=None):
    """Macht aus ["zufall", "felsen", "felsen"] die Bots mit Namen.

    Ergebnis: {"Zufall 1": bot, "Felsen 1": bot, "Felsen 2": bot}
    """
    if len(typen) < 2:
        raise ValueError("Es braucht mindestens zwei Bots")
    if len(typen) > 9:
        raise ValueError("Hoechstens neun Bots an einem Tisch")
    aufstellung = {}
    zaehler = {}
    for typ in typen:
        bot = erzeuge_bot(typ, zufall, verbindung)
        zaehler[typ] = zaehler.get(typ, 0) + 1
        aufstellung[f"{typ.capitalize()} {zaehler[typ]}"] = bot
    return aufstellung


def spiele_bot_hand(verbindung, namen, bots, stacks, small_blind, big_blind, zufall,
                    deck=None):
    """Spielt eine komplette Hand. Gibt {name: gewinn_oder_verlust} in Chips zurueck.

    deck: optional ein schon gemischtes Deck (fuer den Duplicate-Modus). Die
          Karten werden nach Sitzplatz verteilt: Platz 0 bekommt immer die
          ersten Karten, egal welcher Bot dort sitzt.
    """
    if deck is None:
        deck = erzeuge_deck()
        zufall.shuffle(deck)
    else:
        deck = list(deck)  # Kopie, damit das Original fuer die naechste Runde bleibt
    handkarten = {}
    for name in namen:
        handkarten[name] = austeilen(deck, 2)

    zustand = starte_hand(verbindung, namen, small_blind, big_blind, stacks)
    for name in namen:
        handkarten_speichern(verbindung, zustand["hand_id"], name, handkarten[name])

    while not zustand["beendet"]:
        if setzrunde_abgeschlossen(zustand):
            # Keiner muss mehr handeln: naechste Karten oder Showdown
            if zustand["strasse"] == "river":
                beende_hand(zustand)
            else:
                neue_strasse = NAECHSTE_STRASSE[zustand["strasse"]]
                neue_karten = austeilen(deck, NEUE_BOARD_KARTEN[neue_strasse])
                naechste_strasse(verbindung, zustand, neue_karten)
            continue
        name = zustand["am_zug"]
        sicht = erstelle_sicht(zustand, name, handkarten[name])
        aktion, betrag = bots[name](sicht, zufall)
        verarbeite_aktion(verbindung, zustand, name, aktion, betrag)

    if len(zustand["aktiv"]) == 1:
        gezeigte = {}
        gewinner_pro_pot = gewinner_ohne_showdown(zustand)
    else:
        # Bots zeigen beim Showdown immer ihre Karten
        gezeigte = {}
        for name in zustand["aktiv"]:
            gezeigte[name] = handkarten[name]
        gewinner_pro_pot = showdown_gewinner(zustand, gezeigte)
    return abrechnen(verbindung, zustand, gewinner_pro_pot, gezeigte)


def simuliere(verbindung, typen, anzahl_haende, small_blind=1, big_blind=2,
              startstack_bb=STARTSTACK_BB, seed=None, fortschritt=None, duplicate=False):
    """Laesst Bots `anzahl_haende` Haende gegeneinander spielen.

    typen: z. B. ["zufall", "felsen", "station"]
    seed: fuer reproduzierbare Ergebnisse; ohne Seed wird das random-Modul
          benutzt (dann wirkt auch random.seed(...)).
    fortschritt: optionale Funktion fortschritt(fertig, gesamt), die nach
          jeder Hand aufgerufen wird (die Oberflaeche kann damit anzeigen).
    duplicate: Duplicate-Modus (siehe oben); die Handzahl wird dann auf ein
          Vielfaches der Spielerzahl aufgerundet.
    Rueckgabe: Auswertung pro Bot, siehe werte_aus.
    """
    zufall = random.Random(seed) if seed is not None else random
    bots = erstelle_aufstellung(typen, zufall, verbindung)
    return simuliere_bots(verbindung, bots, anzahl_haende, small_blind, big_blind,
                          startstack_bb, zufall, fortschritt, duplicate)


def simuliere_bots(verbindung, bots, anzahl_haende, small_blind=1, big_blind=2,
                   startstack_bb=STARTSTACK_BB, zufall=random, fortschritt=None,
                   duplicate=False):
    """Wie simuliere, aber mit fertigen Bots {name: bot} (z. B. fuer Tests)."""
    if anzahl_haende < 1:
        raise ValueError("Es braucht mindestens eine Hand")
    namen = list(bots.keys())
    ergebnisse_bb = {}
    for name in namen:
        ergebnisse_bb[name] = []

    def spiele(sitzordnung, deck):
        stacks = {}
        for name in sitzordnung:
            stacks[name] = startstack_bb * big_blind
        ergebnis = spiele_bot_hand(verbindung, sitzordnung, bots, stacks,
                                   small_blind, big_blind, zufall, deck)
        for name in sitzordnung:
            ergebnisse_bb[name].append(ergebnis[name] / big_blind)
        if fortschritt is not None:
            fortschritt(len(ergebnisse_bb[namen[0]]), gesamt)

    if not duplicate:
        gesamt = anzahl_haende
        for nummer in range(anzahl_haende):
            spiele(namen, None)
            namen = rotiere(namen)  # der Button wandert
        return werte_aus(ergebnisse_bb)

    # Duplicate: eigene Zufallsquelle nur fuers Mischen, damit die Entscheidungen
    # der Bots die Kartenreihenfolge nicht beeinflussen.
    deck_zufall = random.Random(zufall.random())
    verteilungen = math.ceil(anzahl_haende / len(namen))
    gesamt = verteilungen * len(namen)
    for nummer in range(verteilungen):
        deck = erzeuge_deck()
        deck_zufall.shuffle(deck)
        sitzordnung = list(namen)
        for runde in range(len(namen)):
            spiele(sitzordnung, deck)
            sitzordnung = rotiere(sitzordnung)
    # Unabhaengig sind nur die Verteilungen, nicht die einzelnen Haende darin
    return werte_aus(ergebnisse_bb, gruppe=len(namen))


def werte_aus(ergebnisse_bb, gruppe=1):
    """Wertet die Ergebnisse pro Hand (in Big Blinds) aus.

    gruppe: Im Duplicate-Modus gehoeren immer `gruppe` Haende zusammen (dieselben
    Karten). Fuer die Unsicherheit wird dann pro Gruppe gemittelt, weil nur die
    Gruppen voneinander unabhaengig sind.

    Pro Bot:
    - "haende":      Anzahl Haende
    - "gesamt_bb":   Gewinn/Verlust insgesamt in Big Blinds
    - "bb_pro_100":  Gewinn pro 100 Haende
    - "fehler_95":   Unsicherheit: Der wahre Wert liegt mit 95 % Wahrscheinlichkeit
                     in bb_pro_100 +- fehler_95. (1,96 x Standardfehler)
    """
    auswertung = {}
    for name, werte in ergebnisse_bb.items():
        anzahl = len(werte)
        mittel = sum(werte) / anzahl
        # Mittelwert pro Gruppe (bei gruppe=1 einfach die Werte selbst)
        gruppen_mittel = []
        for start in range(0, anzahl, gruppe):
            block = werte[start:start + gruppe]
            gruppen_mittel.append(sum(block) / len(block))
        fehler = None
        if len(gruppen_mittel) >= 2:
            fehler = (1.96 * statistics.stdev(gruppen_mittel)
                      / math.sqrt(len(gruppen_mittel)) * 100)
        auswertung[name] = {
            "haende": anzahl,
            "gesamt_bb": sum(werte),
            "bb_pro_100": mittel * 100,
            "fehler_95": fehler,
        }
    return auswertung
