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


def equity_gegen_zufall(hand, board, anzahl_gegner, durchlaeufe=1000, zufall=random):
    """Equity einer Hand gegen Gegner, deren Karten man NICHT kennt.

    So sieht es ein Spieler am Tisch: eigene Karten und Board sind bekannt,
    die Gegner bekommen in jedem Durchlauf zufaellige Karten.
    zufall: Zufallsquelle (Standard: das random-Modul; fuer reproduzierbare
            Simulationen kann ein eigenes random.Random(seed) uebergeben werden).
    Rueckgabe: Zahl zwischen 0 und 1 (Split Pot zaehlt anteilig).
    """
    if anzahl_gegner < 1:
        raise ValueError("Es braucht mindestens einen Gegner")
    bekannte_karten = list(hand) + list(board)
    if len(set(bekannte_karten)) != len(bekannte_karten):
        raise ValueError("Eine Karte ist doppelt vergeben")

    restdeck = []
    for karte in erzeuge_deck():
        if karte not in bekannte_karten:
            restdeck.append(karte)

    fehlende = 5 - len(board)
    punkte = 0.0
    for i in range(durchlaeufe):
        deck = list(restdeck)
        zufall.shuffle(deck)
        gegner = []
        for g in range(anzahl_gegner):
            gegner.append(austeilen(deck, 2))
        komplettes_board = list(board) + austeilen(deck, fehlende)

        werte = [bewerte_hand(list(hand) + komplettes_board)]
        for gegner_hand in gegner:
            werte.append(bewerte_hand(gegner_hand + komplettes_board))
        gewinner = finde_gewinner(werte)
        if 0 in gewinner:
            punkte = punkte + 1 / len(gewinner)
    return punkte / durchlaeufe


def equity_gegen_bereiche(hand, board, bereiche, durchlaeufe=1000, zufall=random):
    """Equity gegen Gegner, deren Karten aus einem Handbereich stammen.

    bereiche: ein Prozentwert pro Gegner, z. B. [8, 100] = ein Gegner spielt
              nur die besten 8 % (Felsen), einer spielt alles (zufaellig).
    Wie equity_gegen_zufall, nur dass die Gegnerhaende nicht aus allen
    Haenden gezogen werden, sondern aus ihrem Bereich.
    """
    if len(bereiche) < 1:
        raise ValueError("Es braucht mindestens einen Gegner")
    # Import hier, damit equity.py auch ohne bereiche.py verstaendlich bleibt
    from poker.bereiche import konkrete_haende

    bekannte_karten = list(hand) + list(board)
    if len(set(bekannte_karten)) != len(bekannte_karten):
        raise ValueError("Eine Karte ist doppelt vergeben")

    # Kandidaten pro Gegner einmal vorab bestimmen (ohne eigene Karten und Board)
    kandidaten = []
    for prozent in bereiche:
        haende = konkrete_haende(prozent, bekannte_karten)
        if len(haende) == 0:
            raise ValueError("Im Bereich ist keine Hand mehr moeglich")
        kandidaten.append(haende)

    restdeck = []
    for karte in erzeuge_deck():
        if karte not in bekannte_karten:
            restdeck.append(karte)

    fehlende = 5 - len(board)
    punkte = 0.0
    gezaehlt = 0
    for i in range(durchlaeufe):
        # Gegnerhaende ziehen; zwei Gegner duerfen keine Karte teilen
        benutzt = set()
        gegner = []
        moeglich = True
        for haende in kandidaten:
            for versuch in range(50):
                gegner_hand = zufall.choice(haende)
                if gegner_hand[0] not in benutzt and gegner_hand[1] not in benutzt:
                    break
            else:
                moeglich = False
                break
            benutzt.update(gegner_hand)
            gegner.append(gegner_hand)
        if not moeglich:
            continue

        deck = [karte for karte in restdeck if karte not in benutzt]
        zufall.shuffle(deck)
        komplettes_board = list(board) + austeilen(deck, fehlende)

        werte = [bewerte_hand(list(hand) + komplettes_board)]
        for gegner_hand in gegner:
            werte.append(bewerte_hand(gegner_hand + komplettes_board))
        gewinner = finde_gewinner(werte)
        if 0 in gewinner:
            punkte = punkte + 1 / len(gewinner)
        gezaehlt = gezaehlt + 1
    if gezaehlt == 0:
        raise ValueError("Keine passenden Gegnerhaende gefunden")
    return punkte / gezaehlt
