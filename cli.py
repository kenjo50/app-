"""Kommandozeile fuer die Poker-KI.

Start:  python cli.py                 Demo: zufaellige Hand austeilen und bewerten
        python cli.py 42              Demo mit Seed 42 (immer gleiches Ergebnis)
        python cli.py live            Live-Modus: Aktionen am Tisch mitschreiben
        python cli.py live test.db    Live-Modus mit anderer Datenbank-Datei
"""

import random
import sys

from poker.bewertung import bewerte_hand, finde_gewinner, handart_name
from poker.deck import austeilen, erzeuge_deck, lies_karten
from poker.equity import berechne_equity
from poker.live import (
    NAECHSTE_STRASSE,
    abrechnen,
    beende_hand,
    finde_spieler,
    lies_aktion,
    naechste_strasse,
    pot,
    rotiere,
    setzrunde_abgeschlossen,
    showdown_gewinner,
    starte_hand,
    verarbeite_aktion,
    zu_callen,
)
from poker.profile import berechne_statistik, oeffne_datenbank

STANDARD_DATENBANK = "heimrunde.db"

HILFE = """
Eingaben waehrend einer Hand (die App zeigt, wer dran ist):
  r 6          raise (oder bet) AUF 6
  c            call (oder check, wenn nichts offen ist)
  x            check
  f            fold
  anna r 6     mit Name geht es auch, die App prueft dann, ob Anna dran ist
  stats        Statistiken aller Spieler
  hilfe        diese Hilfe
  quit         Programm beenden
Ist eine Setzrunde vorbei, fragt die App nach den Board-Karten.
Karten: Rang (2-9, T/10, J/B, Q/D, K, A) + Farbe (s Pik, h Herz, d Karo, c Kreuz),
z. B. "Ks 9h 4d".
"""

RANG_ZEICHEN = {11: "B", 12: "D", 13: "K", 14: "A"}
FARB_ZEICHEN = {"Karo": "♦", "Herz": "♥", "Pik": "♠", "Kreuz": "♣"}


def karte_als_text(karte):
    """Macht aus (14, "Pik") den Text "A♠"."""
    rang, farbe = karte
    rang_text = RANG_ZEICHEN.get(rang, str(rang))
    return rang_text + FARB_ZEICHEN[farbe]


def karten_als_text(karten):
    """Macht aus einer Kartenliste einen Text wie "A♠ K♥"."""
    texte = []
    for karte in karten:
        texte.append(karte_als_text(karte))
    return " ".join(texte)


def spiele_eine_hand(namen):
    """Teilt eine Hand aus, bewertet sie und gibt alles auf dem Bildschirm aus."""
    deck = erzeuge_deck()
    random.shuffle(deck)

    handkarten = {}
    for name in namen:
        handkarten[name] = austeilen(deck, 2)
    board = austeilen(deck, 5)

    # Equity vor dem Flop: Wer hatte die besten Chancen, bevor das Board kam?
    alle_haende = []
    for name in namen:
        alle_haende.append(handkarten[name])
    equity = berechne_equity(alle_haende)

    print("Board:", karten_als_text(board))
    print()

    print(f"{'Spieler':<10} {'Hand':<8} {'Equity preflop':<16} Ergebnis")
    werte = []
    for i in range(len(namen)):
        name = namen[i]
        wert = bewerte_hand(handkarten[name] + board)
        werte.append(wert)
        hand_text = karten_als_text(handkarten[name])
        equity_text = f"{equity[i] * 100:.1f} %"
        print(f"{name:<10} {hand_text:<8} {equity_text:<16} {handart_name(wert)}")

    print()
    gewinner = finde_gewinner(werte)
    if len(gewinner) == 1:
        print("Gewinner:", namen[gewinner[0]])
    else:
        gewinner_namen = []
        for i in gewinner:
            gewinner_namen.append(namen[i])
        print("Split Pot:", ", ".join(gewinner_namen))


# ---------------- Live-Modus ----------------


def zahl_als_text(zahl):
    """Zahl ohne unnoetige Nachkommastellen: 6.0 wird zu 6, 2.5 bleibt 2.5."""
    return f"{zahl:g}"


def prozent_als_text(wert):
    """Anteil als Prozent-Text: 0.25 wird zu 25 %, None zu einem Strich."""
    if wert is None:
        return "-"
    return f"{wert * 100:.0f} %"


def zeige_statistik(db, namen):
    print(f"{'Spieler':<10} {'Haende':>6} {'VPIP':>6} {'PFR':>6} {'AF':>6} {'bb/100':>8}")
    for name in namen:
        st = berechne_statistik(db, name)
        af_text = "-" if st["af"] is None else f"{st['af']:.1f}"
        bb_text = "-" if st["bb_pro_100"] is None else f"{st['bb_pro_100']:+.0f}"
        print(f"{name:<10} {st['haende']:>6} {prozent_als_text(st['vpip']):>6} "
              f"{prozent_als_text(st['pfr']):>6} {af_text:>6} {bb_text:>8}")


def zeige_stand(zustand):
    """Zeigt Board, Pot und wer wie viel nachlegen muss."""
    if zustand["board"]:
        print("   Board:", karten_als_text(zustand["board"]))
    offen = []
    for name in zustand["aktiv"]:
        betrag = zu_callen(zustand, name)
        if betrag > 0:
            offen.append(f"{name} {zahl_als_text(betrag)}")
    zeile = f"   Pot {zahl_als_text(pot(zustand))}"
    if offen:
        zeile = zeile + " | offen: " + ", ".join(offen)
    print(zeile)


def spiele_live_hand(db, namen, small_blind, big_blind):
    """Schreibt eine Hand mit. Gibt False zurueck, wenn der Nutzer beenden will."""
    zustand = starte_hand(db, namen, small_blind, big_blind)
    print()
    print(f"=== Hand {zustand['hand_id']} === SB: {namen[0]}, BB: {namen[1]}")
    zeige_stand(zustand)

    while not zustand["beendet"]:
        try:
            if setzrunde_abgeschlossen(zustand):
                # Runde vorbei: nach dem River zum Showdown, sonst neue Karten.
                if zustand["strasse"] == "river":
                    beende_hand(zustand)
                    continue
                strasse = NAECHSTE_STRASSE[zustand["strasse"]]
                eingabe = input(f"   Karten fuer den {strasse}: ").strip()
            else:
                eingabe = input(f"[{zustand['strasse']}] {zustand['am_zug']} > ").strip()
        except EOFError:
            return False
        befehl = eingabe.lower()

        try:
            if befehl == "":
                continue
            elif befehl in ["quit", "q", "exit"]:
                return False
            elif befehl == "hilfe":
                print(HILFE)
            elif befehl == "stats":
                zeige_statistik(db, namen)
            elif setzrunde_abgeschlossen(zustand):
                naechste_strasse(db, zustand, lies_karten(eingabe))
                zeige_stand(zustand)
            else:
                name, grundaktion, betrag = lies_aktion(
                    eingabe, zustand["namen"], zustand["am_zug"]
                )
                aktion, gesetzt = verarbeite_aktion(db, zustand, name, grundaktion, betrag)
                text = f"   {name}: {aktion}"
                if gesetzt > 0:
                    text = text + f" (auf {zahl_als_text(gesetzt)})"
                print(text)
                zeige_stand(zustand)
        except ValueError as fehler:
            # Fehler aus dem Kern anzeigen, die Hand laeuft weiter.
            print(f"   Fehler: {fehler}")

    try:
        if len(zustand["aktiv"]) == 1:
            gewinner = list(zustand["aktiv"])
            gezeigte = {}
        else:
            gewinner, gezeigte = frage_showdown(zustand)
    except EOFError:
        return False

    ergebnis = abrechnen(db, zustand, gewinner, gezeigte)
    print(f"   Pot {zahl_als_text(pot(zustand))} geht an: {', '.join(gewinner)}")
    for name in zustand["namen"]:
        if ergebnis[name] != 0:
            print(f"   {name:<10} {ergebnis[name]:+g}")
    return True


def frage_showdown(zustand):
    """Fragt die gezeigten Karten ab und ermittelt die Gewinner.

    Gibt (gewinner, gezeigte) zurueck.
    """
    print(f"   Showdown zwischen {', '.join(zustand['aktiv'])}.")
    print("   Karten eingeben, leer lassen = Karten nicht gezeigt.")
    while True:
        gezeigte = {}
        try:
            for name in zustand["aktiv"]:
                text = input(f"   Karten von {name}: ").strip()
                if text != "":
                    gezeigte[name] = lies_karten(text)

            if len(gezeigte) > 0:
                gewinner = showdown_gewinner(zustand, gezeigte)
                for name, karten in gezeigte.items():
                    wert = bewerte_hand(karten + zustand["board"])
                    print(f"   {name:<10} {karten_als_text(karten)}   {handart_name(wert)}")
                return gewinner, gezeigte

            # Notloesung: keiner zeigt, Gewinner direkt eingeben.
            text = input("   Keiner zeigt. Wer gewinnt? (Namen mit Komma): ")
            gewinner = []
            for teil in text.split(","):
                if teil.strip() != "":
                    gewinner.append(finde_spieler(teil.strip(), zustand["aktiv"]))
            if len(gewinner) == 0:
                raise ValueError("Bitte mindestens einen Namen eingeben")
            return gewinner, gezeigte
        except ValueError as fehler:
            print(f"   Fehler: {fehler} -- bitte nochmal.")


def frage_blinds():
    while True:
        teile = input("Small Blind und Big Blind (z. B. 1 2): ").replace(",", ".").split()
        try:
            small_blind = float(teile[0])
            big_blind = float(teile[1])
            if 0 < small_blind <= big_blind:
                return small_blind, big_blind
        except (ValueError, IndexError):
            pass
        print("Bitte zwei Zahlen eingeben, Small Blind nicht groesser als Big Blind.")


def frage_namen():
    while True:
        text = input("Spieler mit Komma getrennt, erster = Small Blind: ")
        namen = []
        for teil in text.split(","):
            if teil.strip() != "":
                namen.append(teil.strip())
        if len(namen) >= 2 and len(set(namen)) == len(namen):
            return namen
        print("Bitte mindestens zwei verschiedene Namen eingeben.")


def live_modus(pfad):
    db = oeffne_datenbank(pfad)
    print(f"Live-Modus, Datenbank: {pfad}")
    try:
        namen = frage_namen()
        small_blind, big_blind = frage_blinds()
        print(HILFE)
        while spiele_live_hand(db, namen, small_blind, big_blind):
            namen = rotiere(namen)  # der Button wandert weiter
        print()
        zeige_statistik(db, namen)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        if len(sys.argv) > 2:
            live_modus(sys.argv[2])
        else:
            live_modus(STANDARD_DATENBANK)
    else:
        if len(sys.argv) > 1:
            random.seed(int(sys.argv[1]))
        spiele_eine_hand(["Spieler 1", "Spieler 2", "Spieler 3", "Spieler 4"])
