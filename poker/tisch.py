"""Tisch: ein ganzer Live-Abend fuer die Web-App.

live.py kennt nur eine einzelne Hand. Diese Datei verwaltet den Abend drumherum:
- Spieler in Sitzreihenfolge, Stacks, Blinds, wer gerade aussetzt
- startet Hand fuer Hand (der Button wandert danach weiter)
- merkt sich vor jeder Aktion einen Zwischenstand -> "Rueckgaengig"
- liefert alles, was die Oberflaeche anzeigen muss (wer ist dran, erlaubte
  Aktionen, Raise-Vorschlaege, benutzte Karten, ...)
- speichert den Abend in der Datenbank, damit er einen Server-Neustart
  uebersteht (eine dabei laufende Hand wird verworfen und zaehlt nicht)

Alle Betraege sind ganze Cent (10 Euro = 1000), damit live.py ohne
Rundungsfehler rechnen kann. Die Oberflaeche rechnet in Euro um.

Der Abend ist ein Dictionary:
    {"spieler": [...], "stacks": {name: cent}, "small_blind": 10, "big_blind": 20,
     "aussetzer": [...], "hand": None oder {"zustand": ..., "zwischenstaende": [...]}}
"""

import copy
import json

from poker import live
from poker.bewertung import bewerte_hand, handart_name
from poker.ki import erkenne_typ
from poker.profile import (
    berechne_statistik,
    board_speichern,
    letzte_aktion_loeschen,
    spieler_id,
)

# ---------------- Abend ----------------


def neuer_abend(verbindung, spieler, stacks, small_blind, big_blind):
    """Startet einen Abend. spieler in Sitzreihenfolge; der erste ist der erste Small Blind.

    stacks: {name: cent}. Unbekannte Namen werden als Spieler angelegt.
    """
    if len(spieler) < 2:
        raise ValueError("Es braucht mindestens zwei Spieler")
    if len(set(spieler)) != len(spieler):
        raise ValueError("Ein Spieler ist doppelt eingetragen")
    if not 0 < small_blind <= big_blind:
        raise ValueError("Small Blind muss groesser 0 und hoechstens so gross wie der Big Blind sein")
    for name in spieler:
        if name.strip() == "":
            raise ValueError("Ein Spieler hat keinen Namen")
        if stacks.get(name, 0) <= 0:
            raise ValueError(f"{name} braucht einen Startstack")
        spieler_id(verbindung, name)  # im Spielerprofil anlegen, falls neu
    abend = {
        "spieler": list(spieler),
        "stacks": {name: int(stacks[name]) for name in spieler},
        "small_blind": int(small_blind),
        "big_blind": int(big_blind),
        "aussetzer": [],
        "hand": None,
    }
    speichere_abend(verbindung, abend)
    return abend


def speichere_abend(verbindung, abend):
    """Speichert den Abend (ohne laufende Hand) in der Datenbank."""
    daten = dict(abend)
    daten["hand"] = None
    verbindung.execute("INSERT OR REPLACE INTO tisch_zustand (id, daten) VALUES (1, ?)",
                       (json.dumps(daten),))
    verbindung.commit()


def lade_abend(verbindung):
    """Laedt den gespeicherten Abend oder None. Eine laufende Hand gab es dann nicht mehr."""
    zeile = verbindung.execute("SELECT daten FROM tisch_zustand WHERE id = 1").fetchone()
    if zeile is None:
        return None
    return json.loads(zeile[0])


def beende_abend(verbindung):
    """Loescht den gespeicherten Abend (die gespielten Haende bleiben natuerlich)."""
    verbindung.execute("DELETE FROM tisch_zustand WHERE id = 1")
    verbindung.commit()


def _keine_laufende_hand(abend):
    if abend["hand"] is not None:
        raise ValueError("Das geht nur zwischen zwei Haenden")


def nachkauf(verbindung, abend, name, betrag):
    """Spieler kauft Chips nach (nur zwischen zwei Haenden)."""
    _keine_laufende_hand(abend)
    if name not in abend["spieler"]:
        raise ValueError(f"{name} sitzt nicht am Tisch")
    abend["stacks"] = live.rebuy(abend["stacks"], name, int(betrag))
    speichere_abend(verbindung, abend)


def setze_aus(verbindung, abend, name, aussetzen=True):
    """Spieler setzt aus (bleibt am Tisch, bekommt aber keine Karten) oder ist wieder dabei."""
    _keine_laufende_hand(abend)
    if name not in abend["spieler"]:
        raise ValueError(f"{name} sitzt nicht am Tisch")
    if aussetzen and name not in abend["aussetzer"]:
        abend["aussetzer"].append(name)
    if not aussetzen and name in abend["aussetzer"]:
        abend["aussetzer"].remove(name)
    speichere_abend(verbindung, abend)


def spieler_dazu(verbindung, abend, name, stack):
    """Neuer Spieler setzt sich dazu (bekommt den letzten Platz vor dem Small Blind)."""
    _keine_laufende_hand(abend)
    name = name.strip()
    if name == "":
        raise ValueError("Bitte einen Namen eingeben")
    if name in abend["spieler"]:
        raise ValueError(f"{name} sitzt schon am Tisch")
    if stack <= 0:
        raise ValueError("Der Startstack muss groesser als 0 sein")
    spieler_id(verbindung, name)
    abend["spieler"].append(name)
    abend["stacks"][name] = int(stack)
    speichere_abend(verbindung, abend)


def mitspieler(abend):
    """Wer bekommt in der naechsten Hand Karten? (in Sitzreihenfolge, ab Small Blind)"""
    namen = []
    for name in abend["spieler"]:
        if name not in abend["aussetzer"] and abend["stacks"][name] > 0:
            namen.append(name)
    return namen


# ---------------- Hand ----------------


def _zustand(abend):
    if abend["hand"] is None:
        raise ValueError("Es laeuft gerade keine Hand")
    return abend["hand"]["zustand"]


def starte_naechste_hand(verbindung, abend):
    """Teilt die naechste Hand aus (Blinds werden automatisch gesetzt)."""
    _keine_laufende_hand(abend)
    namen = mitspieler(abend)
    if len(namen) < 2:
        raise ValueError("Es braucht mindestens zwei Spieler mit Chips")
    stacks = {name: abend["stacks"][name] for name in namen}
    zustand = live.starte_hand(verbindung, namen, abend["small_blind"],
                               abend["big_blind"], stacks)
    abend["hand"] = {"zustand": zustand, "zwischenstaende": []}
    return zustand


def _merke(abend, art):
    """Zwischenstand vor einer Aenderung merken (fuer Rueckgaengig)."""
    abend["hand"]["zwischenstaende"].append(
        {"art": art, "zustand": copy.deepcopy(abend["hand"]["zustand"])})


def aktion(verbindung, abend, grundaktion, betrag=None):
    """Aktion des Spielers, der dran ist: "fold", "check", "call", "raise" oder "allin".

    betrag (nur bei raise): Gesamteinsatz in dieser Setzrunde, in Cent.
    """
    zustand = _zustand(abend)
    name = zustand["am_zug"]
    if name is None:
        raise ValueError("Gerade ist niemand dran")
    _merke(abend, "aktion")
    try:
        return live.verarbeite_aktion(verbindung, zustand, name, grundaktion,
                                      None if betrag is None else int(betrag))
    except ValueError:
        abend["hand"]["zwischenstaende"].pop()  # nichts passiert -> nichts merken
        raise


def board_karten(verbindung, abend, karten):
    """Legt die naechsten Board-Karten hin (Flop 3, Turn 1, River 1)."""
    zustand = _zustand(abend)
    _merke(abend, "karten")
    try:
        return live.naechste_strasse(verbindung, zustand, karten)
    except ValueError:
        abend["hand"]["zwischenstaende"].pop()
        raise


def rueckgaengig(verbindung, abend):
    """Nimmt die letzte Aktion oder die letzten Board-Karten zurueck."""
    zustand = _zustand(abend)
    if not abend["hand"]["zwischenstaende"]:
        raise ValueError("Es gibt nichts zum Rueckgaengigmachen")
    letzter = abend["hand"]["zwischenstaende"].pop()
    if letzter["art"] == "aktion":
        letzte_aktion_loeschen(verbindung, zustand["hand_id"])
    else:
        board_speichern(verbindung, zustand["hand_id"], letzter["zustand"]["board"])
    abend["hand"]["zustand"] = letzter["zustand"]


def hand_abbrechen(abend):
    """Verwirft die laufende Hand. Sie bleibt mit abgeschlossen = 0 in der Datenbank
    und zaehlt nicht in der Statistik. Stacks und Button bleiben wie vor der Hand."""
    _zustand(abend)
    abend["hand"] = None


def phase(abend):
    """Was ist gerade zu tun?

    "keine_hand" | "aktion" | "karten" | "showdown" | "gewonnen"
    """
    if abend["hand"] is None:
        return "keine_hand"
    zustand = abend["hand"]["zustand"]
    if len(zustand["aktiv"]) == 1:
        return "gewonnen"
    if not live.setzrunde_abgeschlossen(zustand):
        return "aktion"
    if zustand["strasse"] == "river":
        return "showdown"
    return "karten"


def _hand_fertig(verbindung, abend, ergebnis_pro_spieler):
    """Nach der Abrechnung: Stacks uebernehmen, Button weiter, Abend speichern."""
    zustand = abend["hand"]["zustand"]
    for name in zustand["namen"]:
        abend["stacks"][name] = zustand["stacks"][name]
    abend["spieler"] = live.rotiere(abend["spieler"])
    abend["hand"] = None
    speichere_abend(verbindung, abend)
    return ergebnis_pro_spieler


def abrechnen_ohne_showdown(verbindung, abend):
    """Alle bis auf einen haben gefoldet: Er bekommt den Pot."""
    zustand = _zustand(abend)
    if phase(abend) != "gewonnen":
        raise ValueError("Es sind noch mehrere Spieler in der Hand")
    ergebnis = live.abrechnen(verbindung, zustand, live.gewinner_ohne_showdown(zustand))
    return _hand_fertig(verbindung, abend, ergebnis)


def showdown_vorschau(abend, gezeigte):
    """Wer gewinnt welchen Pot? Aendert nichts.

    gezeigte: {name: karten} der Spieler, die zeigen.
    Rueckgabe: Liste pro Pot {"betrag", "berechtigte", "gewinner"} (gewinner None =
    keiner der Berechtigten hat gezeigt, muss von Hand gewaehlt werden) und die
    Handart jedes gezeigten Spielers.
    """
    zustand = _zustand(abend)
    if phase(abend) != "showdown":
        raise ValueError("Es ist noch nicht Zeit fuer den Showdown")
    gewinner = live.showdown_gewinner(zustand, gezeigte)
    pots = []
    for pot_daten, gewinner_liste in zip(live.berechne_pots(zustand), gewinner):
        pots.append({"betrag": pot_daten["betrag"], "berechtigte": pot_daten["berechtigte"],
                     "gewinner": gewinner_liste})
    handarten = {}
    for name, karten in gezeigte.items():
        handarten[name] = handart_name(bewerte_hand(karten + zustand["board"]))
    return {"pots": pots, "handarten": handarten}


def showdown_abrechnen(verbindung, abend, gezeigte, gewinner_von_hand=None):
    """Rechnet den Showdown ab.

    gewinner_von_hand: {pot_nummer: [namen]} fuer Pots, bei denen keiner gezeigt hat.
    """
    zustand = _zustand(abend)
    vorschau = showdown_vorschau(abend, gezeigte)
    gewinner_pro_pot = []
    for nummer, pot_daten in enumerate(vorschau["pots"]):
        gewinner = pot_daten["gewinner"]
        if gewinner is None:
            von_hand = gewinner_von_hand or {}
            # Aus JSON kommen die Nummern als Text ("0"), aus Python als Zahl (0)
            gewinner = von_hand.get(nummer) or von_hand.get(str(nummer))
            if not gewinner:
                raise ValueError(f"Fuer Pot {nummer + 1} bitte den Gewinner waehlen")
        gewinner_pro_pot.append(gewinner)
    live.beende_hand(zustand)
    ergebnis = live.abrechnen(verbindung, zustand, gewinner_pro_pot, gezeigte)
    return _hand_fertig(verbindung, abend, ergebnis)


# ---------------- Anzeige ----------------


def _runde(betrag, schritt):
    """Auf ganze Vielfache von `schritt` runden (z. B. 10 Cent), ab der Haelfte aufrunden.

    (Pythons round() rundet 4.5 auf 4 - "zur geraden Zahl" -, das wollen wir hier nicht.)
    """
    return int(betrag / schritt + 0.5) * schritt


def raise_vorschlaege(zustand, name, schritt):
    """Betraege fuer die Schnellwahl: Mindest-Raise, halber Pot, Pot, All-in.

    Alle als Gesamteinsatz in dieser Setzrunde (wie bei verarbeite_aktion).
    """
    maximal = zustand["einsaetze"][name] + zustand["stacks"][name]
    mindest = min(live.mindest_erhoehung(zustand), maximal)
    pot_nach_call = live.pot(zustand) + min(live.zu_callen(zustand, name), zustand["stacks"][name])
    vorschlaege = {"mindest": mindest}
    for schluessel, faktor in [("halber_pot", 0.5), ("pot", 1.0)]:
        ziel = _runde(zustand["hoechster"] + faktor * pot_nach_call, schritt)
        vorschlaege[schluessel] = min(max(ziel, mindest), maximal)
    vorschlaege["allin"] = maximal
    return vorschlaege


def anzeige(abend):
    """Alles, was die Oberflaeche zeigen muss, in einem Dictionary."""
    daten = {
        "spieler": abend["spieler"],
        "stacks": abend["stacks"],
        "aussetzer": abend["aussetzer"],
        "small_blind": abend["small_blind"],
        "big_blind": abend["big_blind"],
        "phase": phase(abend),
        "hand": None,
    }
    if abend["hand"] is None:
        daten["naechste_hand"] = mitspieler(abend)
        return daten

    zustand = abend["hand"]["zustand"]
    am_zug = zustand["am_zug"]
    hand = {
        "hand_id": zustand["hand_id"],
        "namen": zustand["namen"],
        "aktiv": zustand["aktiv"],
        "strasse": zustand["strasse"],
        "board": zustand["board"],
        "pot": live.pot(zustand),
        "einsaetze": zustand["einsaetze"],
        "stacks": zustand["stacks"],
        "allin": [n for n in zustand["aktiv"] if live.ist_allin(zustand, n)],
        "am_zug": am_zug,
        "verlauf": zustand["verlauf"][-8:],
        "kann_rueckgaengig": len(abend["hand"]["zwischenstaende"]) > 0,
        "pots": live.berechne_pots(zustand),
    }
    if am_zug is not None and phase(abend) == "aktion":
        hand["erlaubt"] = live.erlaubte_aktionen(zustand, am_zug)
        hand["zu_callen"] = min(live.zu_callen(zustand, am_zug), zustand["stacks"][am_zug])
        if "raise" in hand["erlaubt"]:
            hand["raise"] = raise_vorschlaege(zustand, am_zug, abend["small_blind"])
    if phase(abend) == "karten":
        naechste = live.NAECHSTE_STRASSE[zustand["strasse"]]
        hand["naechste_strasse"] = naechste
        hand["neue_karten"] = live.NEUE_BOARD_KARTEN[naechste]
    daten["hand"] = hand
    return daten


def spieler_statistik(verbindung, name):
    """Statistik und erkannter Spielertyp eines Spielers (alle abgeschlossenen Haende)."""
    statistik = berechne_statistik(verbindung, name)
    erkennung = erkenne_typ(statistik)
    return {
        "name": name,
        "haende": statistik["haende"],
        "vpip": statistik["vpip"],
        "pfr": statistik["pfr"],
        "af": statistik["af"],
        "bb_pro_100": statistik["bb_pro_100"],
        "typ": erkennung["typ"],
        "sicherheit": erkennung["sicherheit"],
    }
