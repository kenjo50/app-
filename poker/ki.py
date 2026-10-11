"""KI: Spielertypen erkennen und eine Gegenstrategie ableiten (regelbasiert).

Teil A - Typ-Erkennung:
  Aus VPIP, PFR und Aggression (Anteil bets/raises an allen aktiven Aktionen
  nach dem Flop) wird der aehnlichste Grundtyp bestimmt. Dazu gehoert eine
  Sicherheit zwischen 0 und 1: Sie waechst mit der Zahl der Haende und sinkt,
  wenn zwei Typen fast gleich gut passen oder keiner richtig passt.

Teil B - KI-Bot:
  - schaetzt fuer jeden Gegner, aus welchem Handbereich seine Karten kommen
    (je nach Typ und nach dem, was er in dieser Hand getan hat),
  - rechnet die Equity gegen diese Bereiche statt gegen Zufallshaende,
  - passt sich an (Bluffs gegen Felsen, keine Bluffs gegen Calling Stations,
    duennere Value-Bets gegen Stations, ...),
  - aber nur so stark, wie die Typ-Erkennung sicher ist. Bei wenigen Haenden
    spielt die KI fast wie der Equity-Bot.
"""

import math

from poker.bots import pot_odds, raise_betrag
from poker.equity import equity_gegen_bereiche, equity_gegen_zufall
from poker.profile import berechne_statistik

MINDEST_HAENDE = 20       # darunter gilt ein Spieler als "unbekannt"
HAENDE_HALBE_SICHERHEIT = 50  # bei so vielen Haenden ist die Datenlage "halb sicher"
KI_DURCHLAEUFE = 300
PROFIL_AKTUALISIEREN = 20  # nach so vielen Entscheidungen werden Profile neu gelesen

# Typische Werte der Grundtypen: (VPIP, PFR, Aggression), gemessen in
# 3 x 1500 simulierten Haenden mit den Typ-Bots (poker/typen.py), 6 Spieler am Tisch.
PROTOTYPEN = {
    "felsen":  (0.10, 0.07, 0.72),
    "station": (0.45, 0.04, 0.19),
    "maniac":  (0.49, 0.32, 0.86),
    "tag":     (0.16, 0.11, 0.78),
}
# Wie stark Unterschiede in den drei Werten zaehlen (Grund-Streuung der Messwerte)
SKALEN = (0.05, 0.04, 0.12)

# Standard-Bereiche (in %), wenn ueber einen Gegner nichts bekannt ist
STANDARD_BEREICH = {"raise": 20, "call": 45, "nichts": 100}
# Wie stark ein Einsatz nach dem Flop den Bereich einengt (Faktor), je nach Typ:
# Passive Spieler setzen nur mit starken Haenden, Maniacs mit fast allem.
EINENGUNG = {"felsen": 0.4, "station": 0.35, "maniac": 0.9, "tag": 0.6,
             "unbekannt": 0.6}


# ---------------- Teil A: Typ-Erkennung ----------------


def aggressions_anteil(statistik):
    """Anteil bets/raises an allen bets/raises/calls nach dem Flop (0 bis 1).

    Anders als der AF wird dieser Wert nicht riesig, wenn jemand nie callt.
    """
    aktiv = statistik["aggressiv"] + statistik["calls"]
    if aktiv == 0:
        return None
    return statistik["aggressiv"] / aktiv


def abstand(werte, prototyp):
    """Abstand zwischen gemessenen Werten und einem Prototyp (0 = genau gleich).

    Jeder Unterschied wird durch eine "erlaubte Abweichung" geteilt. Bei VPIP
    und PFR waechst sie mit dem Wert: 45 % VPIP schwankt mehr als 10 %.
    """
    summe = 0.0
    for i in range(3):
        if werte[i] is None:
            continue  # fehlender Wert (z. B. noch nie nach dem Flop gehandelt)
        erlaubt = SKALEN[i] + (0.2 * prototyp[i] if i < 2 else 0)
        summe = summe + ((werte[i] - prototyp[i]) / erlaubt) ** 2
    return math.sqrt(summe)


def erkenne_typ(statistik):
    """Ordnet einem Spieler einen Grundtyp zu.

    statistik: Ergebnis von berechne_statistik.
    Rueckgabe: {"typ": "felsen"/.../"unbekannt", "sicherheit": 0..1,
                "haende": n, "abstaende": {typ: abstand}}
    """
    haende = statistik["haende"]
    if haende < MINDEST_HAENDE or statistik["vpip"] is None:
        return {"typ": "unbekannt", "sicherheit": 0.0, "haende": haende, "abstaende": {}}

    werte = (statistik["vpip"], statistik["pfr"], aggressions_anteil(statistik))
    abstaende = {}
    for typ, prototyp in PROTOTYPEN.items():
        abstaende[typ] = abstand(werte, prototyp)
    sortiert = sorted(abstaende, key=abstaende.get)
    bester, zweiter = sortiert[0], sortiert[1]

    # 1. Datenlage: 20 Haende -> 0.29, 50 -> 0.5, 200 -> 0.8
    daten = haende / (haende + HAENDE_HALBE_SICHERHEIT)
    # 2. Trennschaerfe: Wie viel besser passt der beste Typ als der zweitbeste?
    trennung = 1 - abstaende[bester] / abstaende[zweiter] if abstaende[zweiter] > 0 else 0
    # 3. Passung: Passt der beste Typ ueberhaupt? (Abstand 3 oder mehr = kaum)
    passung = max(0.0, 1 - abstaende[bester] / 3)

    sicherheit = daten * (0.5 + 0.5 * trennung) * passung
    return {"typ": bester, "sicherheit": round(sicherheit, 3), "haende": haende,
            "abstaende": abstaende}


# ---------------- Teil B: Gegnerbereiche ----------------


def _mische(sicher, unsicher, sicherheit):
    """Zwischenwert: bei Sicherheit 1 ganz `sicher`, bei 0 ganz `unsicher`."""
    return sicherheit * sicher + (1 - sicherheit) * unsicher


def schaetze_bereich(erkennung, verlauf, gegner, strasse):
    """Schaetzt, aus den besten wie viel % der Starthaende die Karten des Gegners kommen.

    Grundlage ist seine Preflop-Aktion in dieser Hand (erhoeht, gecallt oder
    nichts Freiwilliges) und sein Typ. Hat er in der aktuellen Setzrunde nach
    dem Flop gesetzt, wird der Bereich je nach Typ enger.
    Bei unsicherer Erkennung wird mit Standardwerten gemischt.
    """
    preflop = [e["aktion"] for e in verlauf if e["name"] == gegner and e["strasse"] == "preflop"]
    if "raise" in preflop or "bet" in preflop:
        art = "raise"
    elif "call" in preflop:
        art = "call"
    else:
        art = "nichts"

    typ = erkennung["typ"]
    sicherheit = erkennung["sicherheit"]
    standard = STANDARD_BEREICH[art]
    if typ in PROTOTYPEN and art != "nichts":
        vpip, pfr, aggression = PROTOTYPEN[typ]
        typ_bereich = pfr * 100 if art == "raise" else vpip * 100
        prozent = _mische(typ_bereich, standard, sicherheit)
    else:
        prozent = standard

    if strasse != "preflop":
        hat_gesetzt = any(e["name"] == gegner and e["strasse"] == strasse
                          and e["aktion"] in ["bet", "raise"] for e in verlauf)
        if hat_gesetzt:
            faktor = _mische(EINENGUNG.get(typ, EINENGUNG["unbekannt"]),
                             EINENGUNG["unbekannt"], sicherheit)
            prozent = prozent * faktor
    # Auf eine Nachkommastelle runden: weniger verschiedene Bereiche -> Zwischenspeicher wirkt
    return max(1.0, round(prozent, 1))


# ---------------- Teil B: der KI-Bot ----------------


def erstelle_ki_bot(verbindung, ab_hand_id=0):
    """Erzeugt den KI-Bot. Er liest die Gegnerprofile aus der Datenbank.

    ab_hand_id: nur Haende ab dieser Nummer auswerten (in der Simulation die
    aktuelle Runde, damit alte Simulationen nicht mitzaehlen).
    """
    profile = {}
    zaehler = {"entscheidungen": 0}

    def erkennung_fuer(name):
        # Profile nicht bei jeder Entscheidung neu lesen (Datenbank-Abfragen kosten Zeit)
        if name not in profile or zaehler["entscheidungen"] % PROFIL_AKTUALISIEREN == 0:
            try:
                statistik = berechne_statistik(verbindung, name, ab_hand_id)
                profile[name] = erkenne_typ(statistik)
            except ValueError:
                profile[name] = {"typ": "unbekannt", "sicherheit": 0.0, "haende": 0,
                                 "abstaende": {}}
        return profile[name]

    def bot(sicht, zufall):
        zaehler["entscheidungen"] += 1
        gegner = sicht["aktive_gegner"]
        erkennungen = [erkennung_fuer(name) for name in gegner]
        return ki_entscheidung(sicht, erkennungen, zufall)

    bot.profile = profile  # damit man nach der Simulation nachsehen kann
    return bot


TYP_NAMEN = {"felsen": "Felsen", "station": "Calling Station", "maniac": "Maniac",
             "tag": "TAG", "unbekannt": "unbekannt"}


def ki_entscheidung(sicht, erkennungen, zufall):
    """Die eigentliche Entscheidung. erkennungen: eine Typ-Erkennung pro aktivem Gegner.

    Gibt (aktion, betrag) zurueck - die Begruendung liefert ki_bewertung.
    """
    bewertung = ki_bewertung(sicht, erkennungen, zufall)
    return bewertung["aktion"], bewertung["betrag"]


def ki_bewertung(sicht, erkennungen, zufall, durchlaeufe=KI_DURCHLAEUFE):
    """Entscheidung der KI mit allen Zwischenwerten und einer Begruendung in Worten.

    Rueckgabe: {"aktion", "betrag", "equity", "fair", "pot_odds",
                "gegner": [{"name", "typ", "sicherheit", "bereich"}], "gruende": [...]}
    """
    erlaubt = sicht["erlaubt"]
    bereiche = []
    gegner = []
    for name, erkennung in zip(sicht["aktive_gegner"], erkennungen):
        bereich = schaetze_bereich(erkennung, sicht["verlauf"], name, sicht["strasse"])
        bereiche.append(bereich)
        gegner.append({"name": name, "typ": erkennung["typ"],
                       "sicherheit": erkennung["sicherheit"], "bereich": bereich})
    try:
        equity = equity_gegen_bereiche(sicht["handkarten"], sicht["board"], bereiche,
                                       durchlaeufe, zufall)
    except ValueError:
        equity = equity_gegen_zufall(sicht["handkarten"], sicht["board"], sicht["gegner"],
                                     durchlaeufe, zufall)
    fair = 1 / (sicht["gegner"] + 1)
    odds = pot_odds(sicht)

    gruende = [f"Gewinnchance {equity:.0%} gegen die geschaetzten Haende "
               f"(fairer Anteil bei {sicht['gegner'] + 1} Spielern: {fair:.0%})"]
    for g in gegner:
        if g["typ"] == "unbekannt":
            gruende.append(f"{g['name']}: noch unbekannt -> Standardbereich {g['bereich']:g} %")
        else:
            gruende.append(f"{g['name']}: {TYP_NAMEN[g['typ']]} ({g['sicherheit']:.0%} sicher) "
                           f"-> vermutlich die besten {g['bereich']:g} % der Haende")

    def ergebnis(aktion, betrag, grund):
        gruende.append(grund)
        return {"aktion": aktion, "betrag": betrag, "equity": equity, "fair": fair,
                "pot_odds": odds, "gegner": gegner, "gruende": gruende}

    # Wie sicher und wie "bluff-anfaellig" sind die Gegner?
    typen = [e["typ"] for e in erkennungen]
    sicherheiten = [e["sicherheit"] for e in erkennungen]
    min_sicherheit = min(sicherheiten) if sicherheiten else 0
    alle_tight = all(t in ["felsen", "tag"] for t in typen)
    station_dabei = max([s for t, s in zip(typen, sicherheiten) if t == "station"], default=0)
    maniac_dabei = max([s for t, s in zip(typen, sicherheiten) if t == "maniac"], default=0)
    if station_dabei > 0.3:
        gruende.append("Calling Station dabei: duenner auf Wert setzen, nicht bluffen")
    if maniac_dabei > 0.3:
        gruende.append("Maniac dabei: nur mit sehr starker Hand erhoehen, ihn bluffen lassen")

    # Schwellen wie beim Equity-Bot, angepasst je nach Gegner (gewichtet mit Sicherheit):
    # gegen Stations duenner auf Wert setzen, gegen Maniacs nur sehr stark erhoehen
    wert_schwelle = 0.10 - 0.06 * station_dabei + 0.10 * maniac_dabei
    stark_schwelle = 0.20 - 0.05 * station_dabei + 0.10 * maniac_dabei

    if "raise" in erlaubt and equity > fair + stark_schwelle:
        return ergebnis("raise", raise_betrag(sicht, "pot"),
                        "Deutlich vorne -> um den Pot erhoehen")
    if "raise" in erlaubt and equity > fair + wert_schwelle:
        return ergebnis("raise", raise_betrag(sicht, "halber_pot"),
                        "Vorne -> um den halben Pot erhoehen (auf Wert)")

    # Bluff / Steal: nur gegen sicher erkannte, enge Spieler und wenn nichts zu zahlen ist
    if "raise" in erlaubt and "check" in erlaubt and alle_tight and typen:
        if zufall.random() < 0.35 * min_sicherheit:
            return ergebnis("raise", raise_betrag(sicht, "halber_pot"),
                            "Nur enge Gegner -> Bluff, sie geben oft auf")
    # Preflop-Steal gegen enge Spieler, wenn noch keiner erhoeht hat
    if (sicht["strasse"] == "preflop" and "raise" in erlaubt and alle_tight and typen
            and sicht["hoechster"] <= sicht["big_blind"]
            and zufall.random() < 0.4 * min_sicherheit):
        return ergebnis("raise", raise_betrag(sicht, "pot"),
                        "Enge Gegner und keiner hat erhoeht -> Blinds stehlen")

    if "check" in erlaubt:
        return ergebnis("check", None, "Nicht stark genug zum Setzen, Check kostet nichts")
    if equity >= odds:
        return ergebnis("call", None, f"Pot Odds: Du brauchst {odds:.0%}, hast {equity:.0%} -> Call lohnt sich")
    return ergebnis("fold", None, f"Pot Odds: Du brauchst {odds:.0%}, hast nur {equity:.0%} -> Fold")
