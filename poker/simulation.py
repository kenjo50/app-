"""Simulation: Bots spielen gegeneinander, Ergebnis in bb/100.

Die Bots spielen nach genau denselben Regeln wie der Live-Modus
(poker/live.py: Reihenfolge, Mindest-Erhoehung, Side Pots, ...).
Jede Hand wird in einer eigenen Datenbank gespeichert (Standard:
simulation.db), damit die echten Heimrunden-Daten sauber bleiben.
Gespeichert werden auch alle Handkarten - spaeter wertvoll fuer die KI.

Stacks: Jeder Bot startet jede Hand mit demselben Stack (Standard 100 Big
Blinds), wie ein Cash Game mit automatischem Nachkauf.
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
from poker.profile import handkarten_speichern, oeffne_datenbank

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


def erstelle_aufstellung(typen):
    """Macht aus ["zufall", "equity", "equity"] die Bots mit Namen.

    Ergebnis: {"Zufall 1": zufalls_bot, "Equity 1": equity_bot, "Equity 2": equity_bot}
    """
    if len(typen) < 2:
        raise ValueError("Es braucht mindestens zwei Bots")
    if len(typen) > 9:
        raise ValueError("Hoechstens neun Bots an einem Tisch")
    aufstellung = {}
    zaehler = {}
    for typ in typen:
        if typ not in BOT_TYPEN:
            raise ValueError(f"Unbekannter Bot '{typ}' (moeglich: {', '.join(BOT_TYPEN)})")
        zaehler[typ] = zaehler.get(typ, 0) + 1
        aufstellung[f"{typ.capitalize()} {zaehler[typ]}"] = BOT_TYPEN[typ]
    return aufstellung


def spiele_bot_hand(verbindung, namen, bots, stacks, small_blind, big_blind, zufall):
    """Spielt eine komplette Hand. Gibt {name: gewinn_oder_verlust} in Chips zurueck."""
    deck = erzeuge_deck()
    zufall.shuffle(deck)
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
              startstack_bb=STARTSTACK_BB, seed=None, fortschritt=None):
    """Laesst Bots `anzahl_haende` Haende gegeneinander spielen.

    typen: z. B. ["zufall", "equity", "equity"]
    seed: fuer reproduzierbare Ergebnisse; ohne Seed wird das random-Modul
          benutzt (dann wirkt auch random.seed(...)).
    fortschritt: optionale Funktion fortschritt(fertig, gesamt), die nach
          jeder Hand aufgerufen wird (die Oberflaeche kann damit anzeigen).
    Rueckgabe: Auswertung pro Bot, siehe werte_aus.
    """
    if anzahl_haende < 1:
        raise ValueError("Es braucht mindestens eine Hand")
    zufall = random.Random(seed) if seed is not None else random
    bots = erstelle_aufstellung(typen)
    namen = list(bots.keys())
    ergebnisse_bb = {}
    for name in namen:
        ergebnisse_bb[name] = []

    for nummer in range(anzahl_haende):
        stacks = {}
        for name in namen:
            stacks[name] = startstack_bb * big_blind
        ergebnis = spiele_bot_hand(verbindung, namen, bots, stacks,
                                   small_blind, big_blind, zufall)
        for name in namen:
            ergebnisse_bb[name].append(ergebnis[name] / big_blind)
        namen = rotiere(namen)  # der Button wandert
        if fortschritt is not None:
            fortschritt(nummer + 1, anzahl_haende)
    return werte_aus(ergebnisse_bb)


def werte_aus(ergebnisse_bb):
    """Wertet die Ergebnisse pro Hand (in Big Blinds) aus.

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
        fehler = None
        if anzahl >= 2:
            fehler = 1.96 * statistics.stdev(werte) / math.sqrt(anzahl) * 100
        auswertung[name] = {
            "haende": anzahl,
            "gesamt_bb": sum(werte),
            "bb_pro_100": mittel * 100,
            "fehler_95": fehler,
        }
    return auswertung
