"""Bots: Computer-Spieler, die selbst entscheiden.

Ein Bot ist eine Funktion bot(sicht, zufall) -> (grundaktion, betrag).
- sicht: Dictionary mit allem, was ein Spieler am Tisch sehen darf
  (eigene Karten, Board, Pot, ...), siehe erstelle_sicht. Die Karten der
  Gegner sind NICHT dabei, so kann kein Bot schummeln.
- zufall: Zufallsquelle (random.Random), damit Simulationen mit Seed
  reproduzierbar sind.
- grundaktion: "fold", "check", "call" oder "raise"; betrag nur bei "raise"
  (Gesamteinsatz in dieser Setzrunde, wie im Live-Modus).

Vergleichs-Bots fuer die Forschungsfrage:
- zufalls_bot: waehlt gleich wahrscheinlich unter den erlaubten Aktionen
- equity_bot:  entscheidet nur nach seiner Gewinnchance, ohne Gegnerprofile
"""

from poker.equity import equity_gegen_zufall
from poker.live import (
    darf_erhoehen,
    erlaubte_aktionen,
    mindest_erhoehung,
    pot,
    zu_callen,
)

RAISE_GROESSEN = ["halber_pot", "pot", "allin"]
EQUITY_DURCHLAEUFE = 300  # Genauigkeit des Equity-Bots (ca. +-3 Prozentpunkte)


def erstelle_sicht(zustand, name, handkarten):
    """Was der Spieler `name` gerade sehen darf."""
    gegner = 0
    for anderer in zustand["aktiv"]:
        if anderer != name:
            gegner = gegner + 1
    return {
        "name": name,
        "handkarten": list(handkarten),
        "board": list(zustand["board"]),
        "strasse": zustand["strasse"],
        "pot": pot(zustand),
        "zu_callen": min(zu_callen(zustand, name), zustand["stacks"][name]),
        "hoechster": zustand["hoechster"],
        "einsatz": zustand["einsaetze"][name],
        "stack": zustand["stacks"][name],
        "maximal": zustand["einsaetze"][name] + zustand["stacks"][name],
        "mindest_erhoehung": mindest_erhoehung(zustand),
        "darf_erhoehen": darf_erhoehen(zustand, name),
        "erlaubt": erlaubte_aktionen(zustand, name),
        "gegner": gegner,
        "big_blind": zustand["big_blind"],
    }


def raise_betrag(sicht, groesse):
    """Rechnet eine Raise-Groesse in den Betrag um (Gesamteinsatz dieser Runde).

    - "halber_pot": um einen halben Pot erhoehen
    - "pot":        um einen ganzen Pot erhoehen
    - "allin":      alles
    Pot heisst hier: Pot nachdem man selbst gecallt haette (uebliche Pot-Regel).
    Mindestens die Mindest-Erhoehung, hoechstens der eigene Stack.
    Betraege werden auf ganze Chips gerundet.
    """
    if groesse == "allin":
        return sicht["maximal"]
    if groesse == "halber_pot":
        faktor = 0.5
    elif groesse == "pot":
        faktor = 1.0
    else:
        raise ValueError(f"Unbekannte Raise-Groesse: {groesse}")
    pot_nach_call = sicht["pot"] + sicht["zu_callen"]
    ziel = round(sicht["hoechster"] + faktor * pot_nach_call)
    ziel = max(ziel, sicht["mindest_erhoehung"])
    return min(ziel, sicht["maximal"])


def zufalls_bot(sicht, zufall):
    """Waehlt gleich wahrscheinlich eine der erlaubten Aktionen.

    Bei "raise" wird die Groesse zufaellig aus halber Pot, Pot und All-in gewaehlt.
    """
    aktion = zufall.choice(sicht["erlaubt"])
    if aktion == "raise":
        groesse = zufall.choice(RAISE_GROESSEN)
        return "raise", raise_betrag(sicht, groesse)
    return aktion, None


def pot_odds(sicht):
    """Welche Gewinnchance braucht ein Call mindestens, damit er sich lohnt?

    Beispiel: Pot 10, Call 5 -> 5 / (10 + 5) = 33 %.
    """
    if sicht["zu_callen"] == 0:
        return 0.0
    return sicht["zu_callen"] / (sicht["pot"] + sicht["zu_callen"])


def equity_bot(sicht, zufall):
    """Entscheidet nur nach der eigenen Gewinnchance (Equity), ohne Gegnerprofile.

    Faire Equity = 1 / (Anzahl Spieler in der Hand), z. B. heads-up 50 %.
    - Equity mehr als 20 Prozentpunkte ueber fair: Raise um den Pot
    - Equity mehr als 10 Prozentpunkte ueber fair: Raise um den halben Pot
    - sonst callen, wenn die Equity die Pot Odds schlaegt (oder checken)
    - sonst folden (bzw. checken, wenn nichts zu zahlen ist)
    """
    equity = equity_gegen_zufall(sicht["handkarten"], sicht["board"], sicht["gegner"],
                                 EQUITY_DURCHLAEUFE, zufall)
    fair = 1 / (sicht["gegner"] + 1)
    erlaubt = sicht["erlaubt"]

    if "raise" in erlaubt and equity > fair + 0.20:
        return "raise", raise_betrag(sicht, "pot")
    if "raise" in erlaubt and equity > fair + 0.10:
        return "raise", raise_betrag(sicht, "halber_pot")
    if "check" in erlaubt:
        return "check", None
    if equity >= pot_odds(sicht):
        return "call", None
    return "fold", None


BOT_TYPEN = {
    "zufall": zufalls_bot,
    "equity": equity_bot,
}
