"""Live-Modus: eine Hand waehrend des Spiels mitschreiben und abrechnen.

Die App rechnet selbst mit, wie viel jeder in der aktuellen Setzrunde
gesetzt hat. Dadurch reicht beim Callen ein "c" ohne Betrag.

Betraege sind immer der Gesamteinsatz des Spielers in dieser Setzrunde
("raise auf 6", nicht "um 6"). So steht es auch in der Datenbank.

Stacks: Jeder Spieler hat einen Stack (Chips vor ihm). Wer alles gesetzt
hat, ist all-in: Er bleibt in der Hand, muss aber nicht mehr handeln.
Hat jemand weniger als den Call-Betrag, callt er mit dem Rest (all-in).
Daraus entstehen Side Pots (siehe berechne_pots).

Die App weiss auch, wer an der Reihe ist:
- preflop beginnt der Spieler links vom Big Blind, der Big Blind spricht zuletzt
- ab dem Flop beginnt der erste aktive Spieler ab dem Small Blind
- Sonderfall zu zweit (heads-up): preflop beginnt der Small Blind (= Button),
  ab dem Flop der Big Blind
Eine Setzrunde ist vorbei, wenn jeder aktive Spieler mit Chips nach dem
letzten bet/raise gehandelt hat.

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
    "a": "allin", "allin": "allin",
}

NAECHSTE_STRASSE = {"preflop": "flop", "flop": "turn", "turn": "river"}

# Wie viele Board-Karten beim Wechsel in diese Setzrunde dazukommen
NEUE_BOARD_KARTEN = {"flop": 3, "turn": 1, "river": 1}


def starte_hand(verbindung, namen, small_blind, big_blind, stacks):
    """Legt eine neue Hand an und setzt die Blinds.

    `namen` in Sitzreihenfolge, beginnend mit dem Small Blind
    (der zweite Name ist der Big Blind).
    `stacks`: {name: chips} zu Beginn der Hand. Jeder braucht mehr als 0.
    Hat jemand weniger als seinen Blind, setzt er alles (all-in).
    Gibt den Zustand der Hand zurueck.
    """
    for name in namen:
        if name not in stacks or stacks[name] <= 0:
            raise ValueError(f"{name} hat keine Chips")
    hand_id = neue_hand(verbindung, namen, small_blind, big_blind, stacks)

    zustand = {
        "hand_id": hand_id,
        "namen": list(namen),
        "aktiv": list(namen),        # wer noch nicht gefoldet hat
        "strasse": "preflop",
        "board": [],
        "stacks": {},                # Chips, die jeder noch vor sich hat
        "einsaetze": {},             # Einsatz pro Spieler in dieser Setzrunde
        "investiert": {},            # Einsatz pro Spieler in der ganzen Hand
        "hoechster": 0,              # hoechster Einsatz in dieser Setzrunde
        "noch_dran": [],             # wer in dieser Setzrunde noch handeln muss
        "am_zug": None,              # wer jetzt handeln muss (None = Runde vorbei)
        "beendet": False,            # Setzen vorbei
        "abgerechnet": False,        # Pot verteilt und gespeichert
    }
    for name in namen:
        zustand["stacks"][name] = stacks[name]
        zustand["einsaetze"][name] = 0
        zustand["investiert"][name] = 0

    _setze(zustand, namen[0], small_blind)
    _setze(zustand, namen[1], big_blind)
    zustand["hoechster"] = max(zustand["einsaetze"].values())

    # Preflop beginnt der Spieler nach dem Big Blind (Platz 2).
    # Zu zweit ist das wieder Platz 0, also der Small Blind.
    _neue_setzrunde(zustand, 2 % len(namen))
    return zustand


def _setze(zustand, name, neuer_einsatz):
    """Hilfsfunktion: erhoeht den Einsatz eines Spielers in dieser Runde.

    Mehr als sein Stack geht nicht, dann wird nur der Rest gesetzt.
    """
    dazu = min(neuer_einsatz - zustand["einsaetze"][name], zustand["stacks"][name])
    zustand["stacks"][name] -= dazu
    zustand["investiert"][name] += dazu
    zustand["einsaetze"][name] += dazu


def ist_allin(zustand, name):
    """True, wenn der Spieler noch in der Hand ist, aber keine Chips mehr hat."""
    return name in zustand["aktiv"] and zustand["stacks"][name] == 0


def _mit_chips(zustand):
    """Aktive Spieler, die noch Chips haben (also noch handeln koennen)."""
    ergebnis = []
    for name in zustand["aktiv"]:
        if zustand["stacks"][name] > 0:
            ergebnis.append(name)
    return ergebnis


def _neue_setzrunde(zustand, ab_platz):
    """Hilfsfunktion: wer muss in der neuen Setzrunde handeln, wer beginnt?"""
    zustand["noch_dran"] = _mit_chips(zustand)
    # Hat nur noch einer Chips und muss nichts nachlegen, gibt es nichts zu setzen:
    # die anderen sind all-in, die Karten werden einfach aufgedeckt.
    if len(zustand["noch_dran"]) == 1 and zu_callen(zustand, zustand["noch_dran"][0]) == 0:
        zustand["noch_dran"] = []
    zustand["am_zug"] = naechster_am_zug(zustand, ab_platz)


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


def lies_zahl(text):
    """Macht aus "2,5" oder "2.5" die Zahl 2.5."""
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError(f"'{text}' ist keine Zahl")


def lies_aktion(text, namen, am_zug=None):
    """Zerlegt eine Eingabe wie "anna r 6" in (name, grundaktion, betrag).

    Der Name darf fehlen ("r 6", "c"), dann ist der Spieler `am_zug` gemeint.
    grundaktion ist "fold", "check", "call", "raise" oder "allin".
    betrag ist nur bei "raise" gesetzt, sonst None.
    """
    teile = text.split()
    if len(teile) == 0:
        raise ValueError("Format: [name] <f|x|c|r|a> [betrag]")
    # Steht an zweiter Stelle eine Aktion, ist das erste Wort der Name.
    # Sonst ist das erste Wort schon die Aktion und der Name fehlt.
    if len(teile) >= 2 and teile[1].lower() in KUERZEL:
        name = finde_spieler(teile[0], namen)
        teile = teile[1:]
    elif teile[0].lower() in KUERZEL and am_zug is not None:
        name = am_zug
    else:
        raise ValueError("Format: [name] <f|x|c|r|a> [betrag]")
    kuerzel = teile[0].lower()
    if kuerzel not in KUERZEL:
        raise ValueError(f"Unbekannte Aktion '{teile[0]}' (f, x, c, r, a)")
    grundaktion = KUERZEL[kuerzel]

    betrag = None
    if grundaktion == "raise":
        if len(teile) != 2:
            raise ValueError("Bei raise/bet bitte den Betrag angeben, z. B. 'r 6'")
        betrag = lies_zahl(teile[1])
    elif len(teile) > 1:
        raise ValueError(f"Bei {grundaktion} gibt man keinen Betrag an")
    return name, grundaktion, betrag


def verarbeite_aktion(verbindung, zustand, name, grundaktion, betrag=None):
    """Prueft eine Aktion, rechnet den Einsatz aus und speichert sie.

    Aus "call" wird automatisch "check", wenn nichts zu bezahlen ist.
    Aus "raise" wird automatisch "bet", wenn in dieser Runde noch keiner gesetzt hat.
    "allin" setzt den ganzen Stack: als bet/raise, wenn das mehr ist als der
    hoechste Einsatz, sonst als call.
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
    # Hoechster Einsatz, den der Spieler in dieser Runde erreichen kann
    maximal = zustand["einsaetze"][name] + zustand["stacks"][name]

    if grundaktion == "allin":
        if maximal > zustand["hoechster"]:
            grundaktion = "raise"
            betrag = maximal
        else:
            grundaktion = "call"

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
            # Wer nicht genug hat, callt mit allem, was er hat.
            neuer_einsatz = min(zustand["hoechster"], maximal)
        else:
            aktion = "check"
            neuer_einsatz = None
    elif grundaktion == "raise":
        if betrag is None or betrag <= zustand["hoechster"]:
            raise ValueError(
                f"Der Betrag muss hoeher sein als der bisherige Einsatz ({zustand['hoechster']:g})"
            )
        if betrag > maximal:
            raise ValueError(f"{name} hat nur {maximal:g} (all-in mit 'a')")
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
        _setze(zustand, name, neuer_einsatz)
        zustand["hoechster"] = max(zustand["hoechster"], neuer_einsatz)

    # Wer muss jetzt noch handeln?
    if aktion in ["bet", "raise"]:
        # Nach einer Erhoehung muessen alle anderen mit Chips nochmal entscheiden.
        zustand["noch_dran"] = []
        for anderer in _mit_chips(zustand):
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
        raise ValueError("Nach dem River kommt keine Setzrunde mehr")
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
    if len(zustand["namen"]) == 2:
        _neue_setzrunde(zustand, 1)
    else:
        _neue_setzrunde(zustand, 0)
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


def berechne_pots(zustand):
    """Teilt den Pot in Hauptpot und Side Pots auf.

    Idee: Jeder aktive Spieler kann hoechstens so viel von jedem Gegner
    gewinnen, wie er selbst gesetzt hat. Wir bilden "Stufen" bei den
    Gesamteinsaetzen der aktiven Spieler. Jede Stufe ist ein eigener Pot,
    um den alle spielen, die mindestens so viel gesetzt haben.

    Beispiel: Anna all-in 30, Ben 100, Clara 100
    -> Hauptpot 90 (Anna, Ben, Clara), Side Pot 140 (Ben, Clara)

    Rueckgabe: Liste von Dictionaries {"betrag": ..., "berechtigte": [...]},
    der Hauptpot zuerst.
    """
    stufen = []
    for name in zustand["aktiv"]:
        if zustand["investiert"][name] not in stufen:
            stufen.append(zustand["investiert"][name])
    stufen.sort()

    pots = []
    vorherige_stufe = 0
    for stufe in stufen:
        betrag = 0
        # Von jedem Spieler (auch gefoldeten) den Anteil zwischen den Stufen
        for einsatz in zustand["investiert"].values():
            betrag += min(einsatz, stufe) - min(einsatz, vorherige_stufe)
        berechtigte = []
        for name in zustand["namen"]:
            if name in zustand["aktiv"] and zustand["investiert"][name] >= stufe:
                berechtigte.append(name)
        if betrag > 0:
            pots.append({"betrag": betrag, "berechtigte": berechtigte})
        vorherige_stufe = stufe

    # Sicherheitsnetz: Geld von Gefoldeten oberhalb der hoechsten Stufe
    rest = pot(zustand)
    for p in pots:
        rest -= p["betrag"]
    if rest > 0:
        pots[-1]["betrag"] += rest
    return pots


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
    """Ermittelt die Gewinner jedes Pots mit der Handbewertung.

    gezeigte: {name: handkarten} der Spieler, die ihre Karten zeigen.
    Wer nicht zeigt, gibt auf (mucked) und kann nicht gewinnen.

    Rueckgabe: eine Liste mit einem Eintrag pro Pot (wie bei berechne_pots).
    Jeder Eintrag ist die Liste der Gewinner (mehrere = Split Pot) oder None,
    wenn keiner der Berechtigten gezeigt hat und es mehrere Berechtigte gibt.
    Dann muss der Gewinner von Hand angegeben werden.
    """
    if len(zustand["board"]) != 5:
        raise ValueError("Fuer den Showdown muessen alle 5 Board-Karten liegen")
    pruefe_gezeigte(zustand, gezeigte)

    gewinner_pro_pot = []
    for p in berechne_pots(zustand):
        zeigende = []
        for name in p["berechtigte"]:
            if name in gezeigte:
                zeigende.append(name)
        if len(zeigende) == 0:
            if len(p["berechtigte"]) == 1:
                gewinner_pro_pot.append(list(p["berechtigte"]))
            else:
                gewinner_pro_pot.append(None)
            continue
        werte = []
        for name in zeigende:
            werte.append(bewerte_hand(gezeigte[name] + zustand["board"]))
        gewinner = []
        for position in finde_gewinner(werte):
            gewinner.append(zeigende[position])
        gewinner_pro_pot.append(gewinner)
    return gewinner_pro_pot


def abrechnen(verbindung, zustand, gewinner_pro_pot, gezeigte=None):
    """Verteilt jeden Pot an seine Gewinner und speichert das Ergebnis aller Spieler.

    gewinner_pro_pot: eine Liste von Gewinner-Listen, ein Eintrag pro Pot
    (Reihenfolge wie bei berechne_pots). Mehrere Gewinner teilen sich den Pot.
    Die Stacks im Zustand werden um die Gewinne erhoeht.
    Gibt {name: gewinn_oder_verlust} zurueck (gewonnen minus investiert).
    """
    if gezeigte is None:
        gezeigte = {}
    if not zustand["beendet"]:
        raise ValueError("Die Hand laeuft noch")
    if zustand["abgerechnet"]:
        raise ValueError("Die Hand ist schon abgerechnet")
    pots = berechne_pots(zustand)
    if len(gewinner_pro_pot) != len(pots):
        raise ValueError(f"Es gibt {len(pots)} Pot(s), aber {len(gewinner_pro_pot)} Angaben")
    for i in range(len(pots)):
        gewinner = gewinner_pro_pot[i]
        if gewinner is None or len(gewinner) == 0:
            raise ValueError(f"Fuer Pot {i + 1} fehlt der Gewinner")
        for name in gewinner:
            if name not in pots[i]["berechtigte"]:
                raise ValueError(f"{name} kann Pot {i + 1} nicht gewinnen")
    pruefe_gezeigte(zustand, gezeigte)

    gewonnen = {}
    for name in zustand["namen"]:
        gewonnen[name] = 0
    for i in range(len(pots)):
        anteil = pots[i]["betrag"] / len(gewinner_pro_pot[i])
        for name in gewinner_pro_pot[i]:
            gewonnen[name] += anteil

    ergebnis = {}
    for name in zustand["namen"]:
        ergebnis_speichern(verbindung, zustand["hand_id"], name,
                           zustand["investiert"][name], gewonnen[name])
        zustand["stacks"][name] += gewonnen[name]
        ergebnis[name] = gewonnen[name] - zustand["investiert"][name]
    for name, karten in gezeigte.items():
        handkarten_speichern(verbindung, zustand["hand_id"], name, karten)
    zustand["abgerechnet"] = True
    return ergebnis


def gewinner_ohne_showdown(zustand):
    """Alle bis auf einen haben gefoldet: er gewinnt jeden Pot."""
    if len(zustand["aktiv"]) != 1:
        raise ValueError("Es sind noch mehrere Spieler in der Hand")
    gewinner_pro_pot = []
    for p in berechne_pots(zustand):
        gewinner_pro_pot.append(list(zustand["aktiv"]))
    return gewinner_pro_pot


def rebuy(stacks, name, betrag):
    """Gibt neue Stacks zurueck, in denen `name` zusaetzlich `betrag` Chips hat.

    Neue Spieler werden so auch angelegt.
    """
    if betrag <= 0:
        raise ValueError("Der Betrag muss groesser als 0 sein")
    neue = dict(stacks)
    neue[name] = neue.get(name, 0) + betrag
    return neue


def rotiere(namen):
    """Naechste Hand: der Button wandert, der bisherige Small Blind ist jetzt hinten."""
    return namen[1:] + namen[:1]
