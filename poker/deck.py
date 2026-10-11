"""Karten und Deck.

Eine Karte ist ein Tupel (rang, farbe):
- rang: Zahl von 2 bis 14 (11 = Bube, 12 = Dame, 13 = Koenig, 14 = Ass)
- farbe: "Karo", "Herz", "Pik" oder "Kreuz"

Eingabe-Format fuer Karten (wie in der Poker-Literatur ueblich):
Rang + Farbe, z. B. "As" = Pik-Ass, "Th" oder "10h" = Herz-Zehn.
- Raenge: 2-9, T oder 10, J oder B (Bube), Q oder D (Dame), K, A
- Farben: s (spades = Pik), h (hearts = Herz), d (diamonds = Karo), c (clubs = Kreuz)
"""

import re

RAENGE = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
FARBEN = ["Karo", "Herz", "Pik", "Kreuz"]

RANG_KUERZEL = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "t": 10, "10": 10, "j": 11, "b": 11, "q": 12, "d": 12, "k": 13, "a": 14,
}
FARB_KUERZEL = {"s": "Pik", "h": "Herz", "d": "Karo", "c": "Kreuz"}

# Eine Karte im Text: Rang (10 oder ein Zeichen), danach die Farbe.
KARTEN_MUSTER = re.compile(r"(10|[2-9tjbqdka])([shdc])")


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



def lies_karten(text):
    """Macht aus einem Text wie "As Kh" oder "AsKh" eine Liste von Karten.

    Gross-/Kleinschreibung ist egal. Doppelte Karten geben einen Fehler.
    """
    ohne_leerzeichen = text.lower().replace(" ", "")
    karten = []
    position = 0
    while position < len(ohne_leerzeichen):
        treffer = KARTEN_MUSTER.match(ohne_leerzeichen, position)
        if treffer is None:
            raise ValueError(f"'{text}' enthaelt keine gueltige Karte an Stelle {position + 1} "
                             "(Beispiel: As Kh 10d)")
        rang_text, farb_text = treffer.groups()
        karten.append((RANG_KUERZEL[rang_text], FARB_KUERZEL[farb_text]))
        position = treffer.end()
    if len(set(karten)) != len(karten):
        raise ValueError("Eine Karte wurde doppelt eingegeben")
    return karten
