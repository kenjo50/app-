"""Live-Modus: eine Hand waehrend des Spiels mitschreiben und abrechnen.

Die App rechnet selbst mit, wie viel jeder in der aktuellen Setzrunde
gesetzt hat. Dadurch reicht beim Callen ein "c" ohne Betrag.

Betraege sind immer der Gesamteinsatz des Spielers in dieser Setzrunde
("raise auf 6", nicht "um 6"). So steht es auch in der Datenbank.

Die App weiss auch, wer an der Reihe ist:
- preflop beginnt der Spieler links vom Big Blind, der Big Blind spricht zuletzt
- ab dem Flop beginnt der erste aktive Spieler ab dem Small Blind
- Sonderfall zu zweit (heads-up): preflop beginnt der Small Blind (= Button),
  ab dem Flop der Big Blind
Eine Setzrunde ist vorbei, wenn jeder aktive Spieler nach dem letzten
bet/raise gehandelt hat.

Der Zustand einer Hand ist ein Dictionary (siehe starte_hand).
Ablauf: starte_hand -> verarbeite_aktion / naechste_strasse -> beende_hand
-> showdown_gewinner (falls noetig) -> abrechnen.
"""

from poker.bewertung import bewerte_hand, finde_gewinner
from poker.profile import (
    aktion_speichern,
    board_speichern,
    ergebnis_speichern,
    handkarten_speichern,
    neue_hand,
)

# Kuerzel und ausgeschriebene Woerter -> Grundaktion
KUERZEL = {
    "f": "fold", "fold": "fold",
    "x": "check", "check": "check",
    "c": "call", "call": "call",
    "r": "raise", "raise": "raise",
    "b": "raise", "bet": "raise",
}

NAECHSTE_STRASSE = {"preflop": "flop", "flop": "turn", "turn": "river"}

# Wie viele Board-Karten beim Wechsel in diese Setzrunde dazukommen
NEUE_BOARD_KARTEN = {"flop": 3, "turn": 1, "river": 1}


def starte_hand(verbindung, namen, small_blind, big_blind):
    """Legt eine neue Hand an und setzt die Blinds.

    `namen` in Sitzreihenfolge, beginnend mit dem Small Blind
    (der zweite Name ist der Big Blind). Gibt den Zustand der Hand zurueck.
    """
    hand_id = neue_hand(verbindung, namen, small_blind, big_blind)
    einsaetze = {}
    investiert = {}
    for name in namen:
        einsaetze[name] = 0
        investiert[name] = 0
    einsaetze[namen[0]] = small_blind
    einsaetze[namen[1]] = big_blind
    investiert[namen[0]] = small_blind
    investiert[namen[1]] = big_blind
    # Preflop beginnt der Spieler nach dem Big Blind (Platz 2).
    # Zu zweit ist das wieder Platz 0, also der Small Blind.
    erster = namen[2 % len(namen)]
    return {
        "hand_id": hand_id,
        "namen": list(namen),
        "aktiv": list(namen),        # wer noch nicht gefoldet hat
        "strasse": "preflop",
        "board": [],
        "einsaetze": einsaetze,      # Einsatz pro Spieler in dieser Setzrunde
        "investiert": investiert,    # Einsatz pro Spieler in der ganzen Hand
        "hoechster": big_blind,      # hoechster Einsatz in dieser Setzrunde
        "noch_dran": list(namen),    # wer in dieser Setzrunde noch handeln muss
        "am_zug": erster,            # wer jetzt handeln muss (None = Runde vorbei)
        "beendet": False,            # Setzen vorbei
        "abgerechnet": False,        # Pot verteilt und gespeichert
    }


def pot(zustand):
    """Gesamter Pot: alles, was in dieser Hand gesetzt wurde."""
    return sum(zustand["investiert"].values())


def zu_callen(zustand, name):
    """Wie viel muss dieser Spieler noch nachlegen, um mitzugehen?"""
    return zustand["hoechster"] - zustand["einsaetze"][name]


def naechster_am_zug(zustand, ab_platz):
    """Sucht ab Sitzplatz `ab_platz` (im Kreis) den ersten, der noch handeln muss.

    Gibt den Namen zurueck oder None, wenn keiner mehr handeln muss.
    """
    namen = zustand["namen"]
    for schritt in range(len(namen)):
        name = namen[(ab_platz + schritt) % len(namen)]
        if name in zustand["noch_dran"]:
            return name
    return None


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


def lies_aktion(text, namen, am_zug=None):
    """Zerlegt eine Eingabe wie "anna r 6" in (name, grundaktion, betrag).

    Der Name darf fehlen ("r 6", "c"), dann ist der Spieler `am_zug` gemeint.
    grundaktion ist "fold", "check", "call" oder "raise".
    betrag ist nur bei "raise" gesetzt, sonst None.
    """
    teile = text.split()
    if len(teile) == 0:
        raise ValueError("Format: [name] <f|x|c|r> [betrag]")
    # Steht an zweiter Stelle eine Aktion, ist das erste Wort der Name.
    # Sonst ist das erste Wort schon die Aktion und der Name fehlt.
    if len(teile) >= 2 and teile[1].lower() in KUERZEL:
        name = finde_spieler(teile[0], namen)
        teile = teile[1:]
    elif teile[0].lower() in KUERZEL and am_zug is not None:
        name = am_zug
    else:
        raise ValueError("Format: [name] <f|x|c|r> [betrag]")
    kuerzel = teile[0].lower()
    if kuerzel not in KUERZEL:
        raise ValueError(f"Unbekannte Aktion '{teile[0]}' (f, x, c, r)")
    grundaktion = KUERZEL[kuerzel]

    betrag = None
    if grundaktion == "raise":
        if len(teile) != 2:
            raise ValueError("Bei raise/bet bitte den Betrag angeben, z. B. 'r 6'")
        try:
            betrag = float(teile[1].replace(",", "."))
        except ValueError:
            raise ValueError(f"'{teile[1]}' ist keine Zahl")
    elif len(teile) > 1:
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
    if zustand["am_zug"] is None:
        raise ValueError("Die Setzrunde ist vorbei, bitte die naechsten Karten eingeben")
    if name != zustand["am_zug"]:
        raise ValueError(f"{zustand['am_zug']} ist dran, nicht {name}")

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
    elif neuer_einsatz is not None:
        # Nur die Differenz kommt neu in den Pot dazu.
        zustand["investiert"][name] += neuer_einsatz - zustand["einsaetze"][name]
        zustand["einsaetze"][name] = neuer_einsatz
        zustand["hoechster"] = max(zustand["hoechster"], neuer_einsatz)

    # Wer muss jetzt noch handeln?
    if aktion in ["bet", "raise"]:
        # Nach einer Erhoehung muessen alle anderen noch einmal entscheiden.
        zustand["noch_dran"] = []
        for anderer in zustand["aktiv"]:
            if anderer != name:
                zustand["noch_dran"].append(anderer)
    else:
        zustand["noch_dran"].remove(name)

    if len(zustand["aktiv"]) == 1:
        zustand["beendet"] = True
        zustand["noch_dran"] = []
    platz = zustand["namen"].index(name)
    zustand["am_zug"] = naechster_am_zug(zustand, platz + 1)

    return aktion, gespeicherter_betrag


def setzrunde_abgeschlossen(zustand):
    """True, wenn in dieser Setzrunde keiner mehr handeln muss."""
    return len(zustand["noch_dran"]) == 0


def naechste_strasse(verbindung, zustand, neue_karten):
    """Wechselt zur naechsten Setzrunde und legt die neuen Board-Karten hin.

    Flop: 3 Karten, Turn und River: je 1 Karte. Gibt den Namen der Runde zurueck.
    """
    if zustand["beendet"]:
        raise ValueError("Die Hand ist schon vorbei")
    if zustand["strasse"] not in NAECHSTE_STRASSE:
        raise ValueError("Nach dem River kommt keine Setzrunde mehr, gib 'ende' ein")
    if not setzrunde_abgeschlossen(zustand):
        raise ValueError(f"Die Setzrunde laeuft noch, {zustand['am_zug']} ist dran")

    neue_strasse = NAECHSTE_STRASSE[zustand["strasse"]]
    anzahl = NEUE_BOARD_KARTEN[neue_strasse]
    if len(neue_karten) != anzahl:
        raise ValueError(f"Fuer den {neue_strasse} braucht es {anzahl} Karte(n)")
    for karte in neue_karten:
        if karte in zustand["board"]:
            raise ValueError("Diese Karte liegt schon auf dem Board")

    zustand["board"] = zustand["board"] + list(neue_karten)
    board_speichern(verbindung, zustand["hand_id"], zustand["board"])
    for name in zustand["einsaetze"]:
        zustand["einsaetze"][name] = 0
    zustand["hoechster"] = 0
    zustand["strasse"] = neue_strasse
    # Ab dem Flop: erster aktiver Spieler ab dem Small Blind (Platz 0),
    # zu zweit beginnt der Big Blind (Platz 1).
    zustand["noch_dran"] = list(zustand["aktiv"])
    if len(zustand["namen"]) == 2:
        zustand["am_zug"] = naechster_am_zug(zustand, 1)
    else:
        zustand["am_zug"] = naechster_am_zug(zustand, 0)
    return neue_strasse


def beende_hand(zustand):
    """Beendet das Setzen nach dem River (es kommt zum Showdown)."""
    if zustand["beendet"]:
        return
    if zustand["strasse"] != "river":
        raise ValueError("Die Hand kann erst nach dem River beendet werden "
                         "(oder wenn alle bis auf einen gefoldet haben)")
    if not setzrunde_abgeschlossen(zustand):
        raise ValueError(f"Auf dem River ist noch {zustand['am_zug']} dran")
    zustand["beendet"] = True


def pruefe_gezeigte(zustand, gezeigte):
    """Prueft gezeigte Handkarten {name: [karte, karte]} auf Fehler."""
    gesehen = list(zustand["board"])
    for name, karten in gezeigte.items():
        if name not in zustand["aktiv"]:
            raise ValueError(f"{name} ist nicht mehr in der Hand")
        if len(karten) != 2:
            raise ValueError(f"{name} braucht genau 2 Karten")
        for karte in karten:
            if karte in gesehen:
                raise ValueError(f"Eine Karte von {name} ist schon vergeben")
            gesehen.append(karte)


def showdown_gewinner(zustand, gezeigte):
    """Ermittelt die Gewinner beim Showdown mit der Handbewertung.

    gezeigte: {name: handkarten} der Spieler, die ihre Karten zeigen.
    Wer nicht zeigt, gibt auf (mucked) und kann nicht gewinnen.
    Gibt die Namen der Gewinner zurueck (mehrere = Split Pot).
    """
    if len(zustand["board"]) != 5:
        raise ValueError("Fuer den Showdown muessen alle 5 Board-Karten liegen")
    if len(gezeigte) == 0:
        raise ValueError("Keiner hat Karten gezeigt, Gewinner bitte direkt angeben")
    pruefe_gezeigte(zustand, gezeigte)

    namen = list(gezeigte.keys())
    werte = []
    for name in namen:
        werte.append(bewerte_hand(gezeigte[name] + zustand["board"]))
    gewinner = []
    for position in finde_gewinner(werte):
        gewinner.append(namen[position])
    return gewinner


def abrechnen(verbindung, zustand, gewinner, gezeigte=None):
    """Verteilt den Pot an die Gewinner und speichert das Ergebnis aller Spieler.

    Bei mehreren Gewinnern wird der Pot gleichmaessig geteilt.
    Gibt {name: gewinn_oder_verlust} zurueck (gewonnen minus investiert).
    """
    if gezeigte is None:
        gezeigte = {}
    if not zustand["beendet"]:
        raise ValueError("Die Hand laeuft noch")
    if zustand["abgerechnet"]:
        raise ValueError("Die Hand ist schon abgerechnet")
    if len(gewinner) == 0:
        raise ValueError("Es braucht mindestens einen Gewinner")
    for name in gewinner:
        if name not in zustand["aktiv"]:
            raise ValueError(f"{name} hat gefoldet und kann nicht gewinnen")
    pruefe_gezeigte(zustand, gezeigte)

    anteil = pot(zustand) / len(gewinner)
    ergebnis = {}
    for name in zustand["namen"]:
        gewonnen = anteil if name in gewinner else 0
        ergebnis_speichern(verbindung, zustand["hand_id"], name,
                           zustand["investiert"][name], gewonnen)
        ergebnis[name] = gewonnen - zustand["investiert"][name]
    for name, karten in gezeigte.items():
        handkarten_speichern(verbindung, zustand["hand_id"], name, karten)
    zustand["abgerechnet"] = True
    return ergebnis


def rotiere(namen):
    """Naechste Hand: der Button wandert, der bisherige Small Blind ist jetzt hinten."""
    return namen[1:] + namen[:1]
