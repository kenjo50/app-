"""Live-Modus: eine Hand waehrend des Spiels mitschreiben.

Die App rechnet selbst mit, wie viel jeder in der aktuellen Setzrunde
gesetzt hat. Dadurch reicht beim Callen ein "c" ohne Betrag.

Betraege sind immer der Gesamteinsatz des Spielers in dieser Setzrunde
("raise auf 6", nicht "um 6"). So steht es auch in der Datenbank.

Der Zustand einer Hand ist ein Dictionary (siehe starte_hand).
"""

from poker.profile import aktion_speichern, neue_hand

# Kuerzel und ausgeschriebene Woerter -> Grundaktion
KUERZEL = {
    "f": "fold", "fold": "fold",
    "x": "check", "check": "check",
    "c": "call", "call": "call",
    "r": "raise", "raise": "raise",
    "b": "raise", "bet": "raise",
}

NAECHSTE_STRASSE = {"preflop": "flop", "flop": "turn", "turn": "river"}


def starte_hand(verbindung, namen, small_blind, big_blind):
    """Legt eine neue Hand an und setzt die Blinds.

    `namen` in Sitzreihenfolge, beginnend mit dem Small Blind
    (der zweite Name ist der Big Blind). Gibt den Zustand der Hand zurueck.
    """
    hand_id = neue_hand(verbindung, namen, small_blind, big_blind)
    einsaetze = {}
    for name in namen:
        einsaetze[name] = 0
    einsaetze[namen[0]] = small_blind
    einsaetze[namen[1]] = big_blind
    return {
        "hand_id": hand_id,
        "namen": list(namen),
        "aktiv": list(namen),        # wer noch nicht gefoldet hat
        "strasse": "preflop",
        "einsaetze": einsaetze,      # Einsatz pro Spieler in dieser Setzrunde
        "hoechster": big_blind,      # hoechster Einsatz in dieser Setzrunde
        "pot_vorher": 0,             # Geld aus frueheren Setzrunden
        "beendet": False,
    }


def pot(zustand):
    """Gesamter Pot: fruehere Setzrunden plus aktuelle Einsaetze."""
    return zustand["pot_vorher"] + sum(zustand["einsaetze"].values())


def zu_callen(zustand, name):
    """Wie viel muss dieser Spieler noch nachlegen, um mitzugehen?"""
    return zustand["hoechster"] - zustand["einsaetze"][name]


def finde_spieler(eingabe, namen):
    """Findet einen Namen, Gross-/Kleinschreibung egal.

    Ein eindeutiger Anfang reicht auch: "an" findet "Anna".
    """
    eingabe = eingabe.lower()
    for name in namen:
        if name.lower() == eingabe:
            return name
    treffer = []
    for name in namen:
        if name.lower().startswith(eingabe):
            treffer.append(name)
    if len(treffer) == 1:
        return treffer[0]
    if len(treffer) == 0:
        raise ValueError(f"Kein Spieler heisst '{eingabe}'")
    raise ValueError(f"'{eingabe}' ist nicht eindeutig: {', '.join(treffer)}")


def lies_aktion(text, namen):
    """Zerlegt eine Eingabe wie "anna r 6" in (name, grundaktion, betrag).

    grundaktion ist "fold", "check", "call" oder "raise".
    betrag ist nur bei "raise" gesetzt, sonst None.
    """
    teile = text.split()
    if len(teile) < 2:
        raise ValueError("Format: <name> <f|x|c|r> [betrag]")
    name = finde_spieler(teile[0], namen)
    kuerzel = teile[1].lower()
    if kuerzel not in KUERZEL:
        raise ValueError(f"Unbekannte Aktion '{teile[1]}' (f, x, c, r)")
    grundaktion = KUERZEL[kuerzel]

    betrag = None
    if grundaktion == "raise":
        if len(teile) != 3:
            raise ValueError("Bei raise/bet bitte den Betrag angeben, z. B. 'anna r 6'")
        try:
            betrag = float(teile[2].replace(",", "."))
        except ValueError:
            raise ValueError(f"'{teile[2]}' ist keine Zahl")
    elif len(teile) > 2:
        raise ValueError(f"Bei {grundaktion} gibt man keinen Betrag an")
    return name, grundaktion, betrag


def verarbeite_aktion(verbindung, zustand, name, grundaktion, betrag=None):
    """Prueft eine Aktion, rechnet den Einsatz aus und speichert sie.

    Aus "call" wird automatisch "check", wenn nichts zu bezahlen ist.
    Aus "raise" wird automatisch "bet", wenn in dieser Runde noch keiner gesetzt hat.
    Gibt die gespeicherte Aktion als (aktion, betrag) zurueck.
    """
    if zustand["beendet"]:
        raise ValueError("Die Hand ist schon vorbei")
    if name not in zustand["aktiv"]:
        raise ValueError(f"{name} ist nicht mehr in der Hand")

    offen = zu_callen(zustand, name)

    if grundaktion == "fold":
        aktion = "fold"
        neuer_einsatz = None
    elif grundaktion == "check":
        if offen > 0:
            raise ValueError(f"{name} kann nicht checken, es sind {offen:g} offen")
        aktion = "check"
        neuer_einsatz = None
    elif grundaktion == "call":
        if offen > 0:
            aktion = "call"
            neuer_einsatz = zustand["hoechster"]
        else:
            aktion = "check"
            neuer_einsatz = None
    elif grundaktion == "raise":
        if betrag is None or betrag <= zustand["hoechster"]:
            raise ValueError(
                f"Der Betrag muss hoeher sein als der bisherige Einsatz ({zustand['hoechster']:g})"
            )
        if zustand["hoechster"] == 0:
            aktion = "bet"
        else:
            aktion = "raise"
        neuer_einsatz = betrag
    else:
        raise ValueError(f"Unbekannte Aktion: {grundaktion}")

    # Erst speichern (das prueft auch nochmal), dann den Zustand aendern.
    gespeicherter_betrag = 0 if neuer_einsatz is None else neuer_einsatz
    aktion_speichern(verbindung, zustand["hand_id"], name, zustand["strasse"],
                     aktion, gespeicherter_betrag)

    if aktion == "fold":
        zustand["aktiv"].remove(name)
        if len(zustand["aktiv"]) == 1:
            zustand["beendet"] = True
    elif neuer_einsatz is not None:
        zustand["einsaetze"][name] = neuer_einsatz
        zustand["hoechster"] = max(zustand["hoechster"], neuer_einsatz)

    return aktion, gespeicherter_betrag


def setzrunde_abgeschlossen(zustand):
    """True, wenn alle aktiven Spieler gleich viel gesetzt haben."""
    for name in zustand["aktiv"]:
        if zu_callen(zustand, name) > 0:
            return False
    return True


def naechste_strasse(zustand):
    """Wechselt zur naechsten Setzrunde (flop, turn, river). Gibt ihren Namen zurueck."""
    if zustand["beendet"]:
        raise ValueError("Die Hand ist schon vorbei")
    if zustand["strasse"] not in NAECHSTE_STRASSE:
        raise ValueError("Nach dem River kommt keine Setzrunde mehr, gib 'ende' ein")
    if not setzrunde_abgeschlossen(zustand):
        offen = []
        for name in zustand["aktiv"]:
            if zu_callen(zustand, name) > 0:
                offen.append(name)
        raise ValueError(f"Es muessen noch callen oder folden: {', '.join(offen)}")

    zustand["pot_vorher"] = pot(zustand)
    for name in zustand["einsaetze"]:
        zustand["einsaetze"][name] = 0
    zustand["hoechster"] = 0
    zustand["strasse"] = NAECHSTE_STRASSE[zustand["strasse"]]
    return zustand["strasse"]


def beende_hand(zustand):
    """Beendet die Hand nach dem River (Showdown)."""
    if zustand["beendet"]:
        return
    if zustand["strasse"] != "river":
        raise ValueError("Die Hand kann erst nach dem River beendet werden "
                         "(oder wenn alle bis auf einen gefoldet haben)")
    if not setzrunde_abgeschlossen(zustand):
        raise ValueError("Auf dem River muss noch jemand callen oder folden")
    zustand["beendet"] = True


def rotiere(namen):
    """Naechste Hand: der Button wandert, der bisherige Small Blind ist jetzt hinten."""
    return namen[1:] + namen[:1]
