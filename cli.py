"""Kommandozeilen-Demo: Karten austeilen, Haende bewerten, Gewinner zeigen.

Start:  python cli.py            (zufaellig)
        python cli.py 42         (mit Seed 42, immer gleiches Ergebnis)
"""

import random
import sys

from poker.bewertung import bewerte_hand, finde_gewinner, handart_name
from poker.deck import austeilen, erzeuge_deck
from poker.equity import berechne_equity

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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        random.seed(int(sys.argv[1]))
    spiele_eine_hand(["Spieler 1", "Spieler 2", "Spieler 3", "Spieler 4"])
