"""Karten und Deck.

Eine Karte ist ein Tupel (rang, farbe):
- rang: Zahl von 2 bis 14 (11 = Bube, 12 = Dame, 13 = Koenig, 14 = Ass)
- farbe: "Karo", "Herz", "Pik" oder "Kreuz"
"""

RAENGE = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
FARBEN = ["Karo", "Herz", "Pik", "Kreuz"]


def erzeuge_deck():
    """Gibt ein ungemischtes Deck mit 52 Karten zurueck.

    Gemischt wird bewusst beim Aufrufer (random.shuffle), damit Tests
    ein Deck in bekannter Reihenfolge nutzen koennen.
    """
    deck = []
    for rang in RAENGE:
        for farbe in FARBEN:
            karte = (rang, farbe)
            deck.append(karte)
    return deck


def austeilen(deck, anzahl):
    """Nimmt `anzahl` Karten vom Deck (mit pop) und gibt sie als Liste zurueck.

    Die Karten werden wirklich aus dem Deck entfernt, damit keine Karte
    doppelt im Spiel ist.
    """
    karten = []
    for i in range(anzahl):
        karten.append(deck.pop())
    return karten


def zaehle_raenge(karten):
    """Zaehlt, wie oft jeder Rang vorkommt. Ergebnis: {rang: anzahl}."""
    zaehler = {}
    for karte in karten:
        rang = karte[0]
        if rang in zaehler:
            zaehler[rang] = zaehler[rang] + 1
        else:
            zaehler[rang] = 1
    return zaehler

