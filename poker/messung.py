"""Prototypen messen: Welche VPIP/PFR/Aggression zeigt jeder Typ-Bot bei
welcher Tischgroesse?

Am vollen Tisch spielt man anders als heads-up (z. B. muss man oefter gegen
Erhoehungen entscheiden, nach dem Flop gibt es weniger Gegner). Damit die
Typ-Erkennung fair vergleicht, wird fuer jede Tischgroesse getrennt gemessen.

Ablauf pro Tischgroesse: viele Runden mit zufaellig zusammengesetzten Tischen
aus den vier Grundtypen (jedes Mal neu gestreute Bots), die Werte jedes Typs
werden ueber alle seine Haende zusammengezaehlt.

Das Ergebnis wird in poker/ki.py (PROTOTYPEN_NACH_GROESSE) eingetragen.
Neu messen, wenn sich die Typ-Bots aendern: python cli.py messen
"""

import random

from poker.profile import berechne_statistik, naechste_hand_id
from poker.simulation import erzeuge_bot, oeffne_simulationsdatenbank, simuliere_bots
from poker.typen import GRUNDTYPEN

HAENDE_PRO_RUNDE = 100


def miss_tischgroesse(spieler_anzahl, haende, seed=None, fortschritt=None):
    """Misst die Prototypen aller Grundtypen bei `spieler_anzahl` Spielern.

    haende: Gesamtzahl simulierter Haende (in Runden zu je 100 Haenden).
    fortschritt: optionale Funktion fortschritt(fertig, gesamt) nach jeder Runde.
    Rueckgabe: {typ: (vpip, pfr, aggression)}, auf zwei Stellen gerundet.
    """
    if not 2 <= spieler_anzahl <= 9:
        raise ValueError("Gemessen wird fuer 2 bis 9 Spieler")
    zufall = random.Random(seed)
    verbindung = oeffne_simulationsdatenbank(":memory:")
    typen = list(GRUNDTYPEN)
    # Zaehler pro Typ: Haende, VPIP-Haende, PFR-Haende, aggressive Aktionen, Calls
    summen = {typ: [0, 0.0, 0.0, 0, 0] for typ in typen}

    runden = max(1, haende // HAENDE_PRO_RUNDE)
    for runde in range(runden):
        # Tisch zusammenstellen: ein Typ der Reihe nach (so kommt jeder gleich oft
        # dran), die anderen Plaetze zufaellig - so trifft jeder Typ auf jeden
        plaetze = [typen[runde % len(typen)]]
        while len(plaetze) < spieler_anzahl:
            plaetze.append(zufall.choice(typen))
        zufall.shuffle(plaetze)

        bots = {}
        typ_von = {}
        for nummer, typ in enumerate(plaetze):
            name = f"{typ} {nummer}"
            bots[name] = erzeuge_bot(typ, zufall)
            typ_von[name] = typ
        ab_hand = naechste_hand_id(verbindung)
        simuliere_bots(verbindung, bots, HAENDE_PRO_RUNDE, zufall=zufall)

        for name, typ in typ_von.items():
            s = berechne_statistik(verbindung, name, ab_hand)
            summe = summen[typ]
            summe[0] += s["haende"]
            summe[1] += s["vpip"] * s["haende"]
            summe[2] += s["pfr"] * s["haende"]
            summe[3] += s["aggressiv"]
            summe[4] += s["calls"]
        # Die Namen wiederholen sich in jeder Runde - alte Haende wegwerfen
        verbindung.execute("DELETE FROM aktionen")
        verbindung.execute("DELETE FROM teilnehmer")
        if fortschritt is not None:
            fortschritt(runde + 1, runden)
    verbindung.close()

    ergebnis = {}
    for typ, (anzahl, vpip, pfr, aggressiv, calls) in summen.items():
        if anzahl == 0:
            continue
        aggression = aggressiv / (aggressiv + calls) if aggressiv + calls else 0.0
        ergebnis[typ] = (round(vpip / anzahl, 2), round(pfr / anzahl, 2), round(aggression, 2))
    return ergebnis


def als_python(messungen):
    """Formatiert {spieler_anzahl: {typ: werte}} zum Einfuegen in poker/ki.py."""
    zeilen = ["PROTOTYPEN_NACH_GROESSE = {"]
    for anzahl in sorted(messungen):
        zeilen.append(f"    {anzahl}: {{")
        for typ, werte in messungen[anzahl].items():
            zeilen.append(f'        "{typ}": ({werte[0]:.2f}, {werte[1]:.2f}, {werte[2]:.2f}),')
        zeilen.append("    },")
    zeilen.append("}")
    return "\n".join(zeilen)
