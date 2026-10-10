"""Gewinnwahrscheinlichkeit (Equity) per Monte-Carlo-Simulation.

Idee: Die fehlenden Board-Karten werden sehr oft zufaellig ausgeteilt.
Wir zaehlen, wie oft jeder Spieler gewinnt. Gewinn geteilt durch Anzahl
Durchlaeufe ist dann (ungefaehr) die Gewinnwahrscheinlichkeit.
"""

import random

from poker.bewertung import bewerte_hand, finde_gewinner
from poker.deck import austeilen, erzeuge_deck

STANDARD_DURCHLAEUFE = 10000


def berechne_equity(haende, board=None, durchlaeufe=STANDARD_DURCHLAEUFE):
    """Schaetzt die Equity jedes Spielers.

    haende:      Liste der Handkarten, je Spieler eine Liste mit 2 Karten
    board:       bereits liegende Board-Karten (0, 3, 4 oder 5), Standard: keine
    durchlaeufe: wie oft simuliert wird

    Rueckgabe: Liste mit einer Zahl zwischen 0 und 1 pro Spieler.
    Ein Split Pot zaehlt anteilig (bei zwei Gewinnern bekommt jeder 0,5).
    Die Summe aller Werte ist daher 1.
    """
    if board is None:
        board = []
    if len(haende) < 2:
        raise ValueError("Es braucht mindestens zwei Spieler")
    if len(board) > 5:
        raise ValueError("Das Board hat hoechstens 5 Karten")

    # Alle bekannten Karten sammeln und auf Doppelte pruefen.
    bekannte_karten = list(board)
    for hand in haende:
        if len(hand) != 2:
            raise ValueError("Jede Hand braucht genau 2 Karten")
        bekannte_karten.extend(hand)
    if len(set(bekannte_karten)) != len(bekannte_karten):
        raise ValueError("Eine Karte ist doppelt vergeben")

    # Restdeck: alle Karten, die noch nicht im Spiel sind.
    restdeck = []
    for karte in erzeuge_deck():
        if karte not in bekannte_karten:
            restdeck.append(karte)

    fehlende = 5 - len(board)
    punkte = [0.0] * len(haende)

    for i in range(durchlaeufe):
        deck = list(restdeck)  # Kopie, damit das Restdeck vollstaendig bleibt
        random.shuffle(deck)
        komplettes_board = board + austeilen(deck, fehlende)

        werte = []
        for hand in haende:
            werte.append(bewerte_hand(hand + komplettes_board))

        gewinner = finde_gewinner(werte)
        for position in gewinner:
            punkte[position] = punkte[position] + 1 / len(gewinner)

    equity = []
    for p in punkte:
        equity.append(p / durchlaeufe)
    return equity
