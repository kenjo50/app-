"""Typ-Bots: Bots, die typische Spielstile nachahmen (Trainings-Modus).

Jeder Spielertyp ist durch wenige Werte beschrieben:
- vpip:        mit wie viel % der Starthaende er freiwillig mitspielt
- pfr:         mit wie viel % der Starthaende er vor dem Flop erhoeht
- gegen_raise: welcher Anteil seiner Haende gegen eine Erhoehung weiterspielt
- wert:        ab wie viel Equity ueber "fair" er nach dem Flop setzt
- call:        ab wie viel Equity ueber "fair" er einen Einsatz callt
               (negativ = callt auch mit schlechten Haenden)
- aggression:  wie oft er bei einer guten Hand wirklich setzt (sonst checkt/callt er)
- bluff:       wie oft er ohne gute Hand setzt

Streuung: Jeder Bot bekommt beim Erzeugen leicht veraenderte Werte, damit
nicht alle Felsen exakt gleich spielen (wie echte Menschen auch).

Der Mischtyp gehoert zu keinem der vier Grundtypen. Gegen ihn wird die KI
nicht abgestimmt - er prueft, ob ihre Erkennung verallgemeinert.
"""

from poker.bereiche import ist_im_bereich
from poker.bots import raise_betrag
from poker.equity import equity_gegen_zufall

TYP_DURCHLAEUFE = 150  # Equity-Genauigkeit der Typ-Bots nach dem Flop

GRUNDTYPEN = {
    # Felsen: spielt sehr wenige Haende, setzt nur mit starken Haenden
    "felsen":  {"vpip": 10, "pfr": 7, "gegen_raise": 0.5, "wert": 0.15, "call": 0.08,
                "aggression": 0.6, "bluff": 0.02},
    # Calling Station: spielt viele Haende, callt fast alles, setzt selten
    "station": {"vpip": 55, "pfr": 5, "gegen_raise": 0.9, "wert": 0.15, "call": -0.35,
                "aggression": 0.25, "bluff": 0.02},
    # Maniac: spielt viele Haende und erhoeht staendig, blufft oft
    "maniac":  {"vpip": 60, "pfr": 45, "gegen_raise": 0.8, "wert": 0.0, "call": -0.15,
                "aggression": 0.9, "bluff": 0.35},
    # TAG (tight-aggressiv): wenige Haende, die aber aggressiv
    "tag":     {"vpip": 20, "pfr": 16, "gegen_raise": 0.5, "wert": 0.08, "call": 0.0,
                "aggression": 0.8, "bluff": 0.08},
}

# Mischtyp: vor dem Flop aggressiv wie ein TAG/LAG, danach passiv wie eine Station
MISCHTYP = {"vpip": 35, "pfr": 28, "gegen_raise": 0.7, "wert": 0.12, "call": -0.2,
            "aggression": 0.3, "bluff": 0.05}

ALLE_TYPEN = dict(GRUNDTYPEN)
ALLE_TYPEN["misch"] = MISCHTYP

TYP_NAMEN = {"felsen": "Felsen", "station": "Calling Station", "maniac": "Maniac",
             "tag": "TAG", "misch": "Mischtyp"}


def _begrenze(wert, minimum, maximum):
    return max(minimum, min(maximum, wert))


def streue_werte(grundwerte, zufall, staerke=1.0):
    """Gibt leicht veraenderte Werte zurueck (Normalverteilung um die Grundwerte).

    staerke=0 ergibt genau die Grundwerte (fuer Tests).
    """
    werte = {}
    werte["vpip"] = _begrenze(zufall.gauss(grundwerte["vpip"], grundwerte["vpip"] * 0.15 * staerke), 3, 95)
    werte["pfr"] = _begrenze(zufall.gauss(grundwerte["pfr"], grundwerte["pfr"] * 0.15 * staerke),
                             1, werte["vpip"])
    for name in ["gegen_raise", "aggression", "bluff"]:
        werte[name] = _begrenze(zufall.gauss(grundwerte[name], 0.05 * staerke), 0, 1)
    for name in ["wert", "call"]:
        werte[name] = zufall.gauss(grundwerte[name], 0.03 * staerke)
    return werte


def _wurde_erhoeht(sicht):
    """Hat vor dem Flop schon jemand ueber den Big Blind hinaus erhoeht?"""
    return sicht["hoechster"] > sicht["big_blind"]


def _preflop(werte, sicht, zufall):
    hand = sicht["handkarten"]
    erlaubt = sicht["erlaubt"]
    passiv = "check" if "check" in erlaubt else "fold"

    if _wurde_erhoeht(sicht):
        # Gegen eine Erhoehung: mit den allerbesten Haenden zurueck-erhoehen,
        # mit einem Teil des Bereichs callen, sonst aufgeben.
        if "raise" in erlaubt and ist_im_bereich(hand, werte["pfr"] * 0.3):
            return "raise", raise_betrag(sicht, "pot")
        if ist_im_bereich(hand, werte["vpip"] * werte["gegen_raise"]):
            return ("call", None) if "call" in erlaubt else ("check", None)
        return passiv, None

    if "raise" in erlaubt and ist_im_bereich(hand, werte["pfr"]):
        return "raise", raise_betrag(sicht, "pot")
    if ist_im_bereich(hand, werte["vpip"]):
        return ("call", None) if "call" in erlaubt else ("check", None)
    return passiv, None


def _nach_dem_flop(werte, sicht, zufall):
    erlaubt = sicht["erlaubt"]
    equity = equity_gegen_zufall(sicht["handkarten"], sicht["board"], sicht["gegner"],
                                 TYP_DURCHLAEUFE, zufall)
    vorteil = equity - 1 / (sicht["gegner"] + 1)  # ueber oder unter "fair"

    gute_hand = vorteil > werte["wert"]
    if "raise" in erlaubt:
        if gute_hand and zufall.random() < werte["aggression"]:
            groesse = "pot" if vorteil > werte["wert"] + 0.15 else "halber_pot"
            return "raise", raise_betrag(sicht, groesse)
        if not gute_hand and zufall.random() < werte["bluff"]:
            return "raise", raise_betrag(sicht, zufall.choice(["halber_pot", "pot"]))
    if "check" in erlaubt:
        return "check", None
    if vorteil > werte["call"]:
        return "call", None
    return "fold", None


def erstelle_typ_bot(typ, zufall, streuung=1.0):
    """Erzeugt einen Bot vom Typ "felsen", "station", "maniac", "tag" oder "misch".

    Gibt (bot, werte) zurueck; werte sind die gestreuten Eigenschaften.
    """
    if typ not in ALLE_TYPEN:
        raise ValueError(f"Unbekannter Spielertyp: {typ}")
    werte = streue_werte(ALLE_TYPEN[typ], zufall, streuung)
    return bot_aus_werten(werte), werte


def bot_aus_werten(werte):
    """Bot mit fest vorgegebenen Werten (z. B. nachgeahmt von einem echten Spieler)."""
    def bot(sicht, zufall):
        if sicht["strasse"] == "preflop":
            return _preflop(werte, sicht, zufall)
        return _nach_dem_flop(werte, sicht, zufall)

    return bot
