"""Handbewertung fuer Texas Hold'em.

Jede Hand bekommt einen Wert als Tupel: (handart, rang1, rang2, ...).
Python vergleicht Tupel von links nach rechts. Deshalb gilt:
bessere Hand = groesserer Wert. Erst entscheidet die Handart,
bei Gleichstand die Raenge (Paar-Rang, dann Kicker usw.).
"""

from itertools import combinations

from poker.deck import zaehle_raenge

# Handarten als Zahlen: je groesser, desto besser.
HOECHSTE_KARTE = 0
PAAR = 1
ZWEI_PAARE = 2
DRILLING = 3
STRASSE = 4
FLUSH = 5
FULL_HOUSE = 6
VIERLING = 7
STRAIGHT_FLUSH = 8

HANDART_NAMEN = {
    HOECHSTE_KARTE: "Hoechste Karte",
    PAAR: "Paar",
    ZWEI_PAARE: "Zwei Paare",
    DRILLING: "Drilling",
    STRASSE: "Strasse",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    VIERLING: "Vierling",
    STRAIGHT_FLUSH: "Straight Flush",
}


def hoechste_strassenkarte(raenge):
    """Prueft, ob 5 Raenge eine Strasse bilden.

    Gibt die hoechste Karte der Strasse zurueck, sonst None.
    Sonderfall A-2-3-4-5: Das Ass zaehlt unten, hoechste Karte ist die 5.
    """
    verschiedene = set(raenge)
    if len(verschiedene) != 5:
        return None
    if max(verschiedene) - min(verschiedene) == 4:
        return max(verschiedene)
    if verschiedene == {14, 2, 3, 4, 5}:
        return 5
    return None


def bewerte_fuenf(karten):
    """Bewertet genau 5 Karten und gibt den Wert als Tupel zurueck."""
    farben = []
    for karte in karten:
        farben.append(karte[1])
    ist_flush = len(set(farben)) == 1

    raenge = []
    for karte in karten:
        raenge.append(karte[0])
    strassen_hoch = hoechste_strassenkarte(raenge)

    # Gruppen bilden: (anzahl, rang), sortiert nach Anzahl, dann Rang.
    # Beispiel Full House K-K-K-4-4  ->  [(3, 13), (2, 4)]
    gruppen = []
    for rang, anzahl in zaehle_raenge(karten).items():
        gruppen.append((anzahl, rang))
    gruppen.sort(reverse=True)

    hoehen = []
    raenge_nach_gruppe = []
    for anzahl, rang in gruppen:
        hoehen.append(anzahl)
        raenge_nach_gruppe.append(rang)

    if strassen_hoch is not None and ist_flush:
        return (STRAIGHT_FLUSH, strassen_hoch)
    elif hoehen == [4, 1]:
        return (VIERLING, *raenge_nach_gruppe)
    elif hoehen == [3, 2]:
        return (FULL_HOUSE, *raenge_nach_gruppe)
    elif ist_flush:
        return (FLUSH, *sorted(raenge, reverse=True))
    elif strassen_hoch is not None:
        return (STRASSE, strassen_hoch)
    elif hoehen == [3, 1, 1]:
        return (DRILLING, *raenge_nach_gruppe)
    elif hoehen == [2, 2, 1]:
        return (ZWEI_PAARE, *raenge_nach_gruppe)
    elif hoehen == [2, 1, 1, 1]:
        return (PAAR, *raenge_nach_gruppe)
    else:
        return (HOECHSTE_KARTE, *raenge_nach_gruppe)


def bewerte_hand(karten):
    """Bewertet 5 bis 7 Karten: die beste Fuenfer-Kombination zaehlt.

    Bei 7 Karten sind das 21 Kombinationen. Einfach und sicher;
    optimiert wird erst, wenn es spaeter zu langsam ist.
    """
    if len(karten) < 5 or len(karten) > 7:
        raise ValueError("bewerte_hand braucht 5 bis 7 Karten")
    bester_wert = None
    for fuenf in combinations(karten, 5):
        wert = bewerte_fuenf(fuenf)
        if bester_wert is None or wert > bester_wert:
            bester_wert = wert
    return bester_wert


def handart_name(wert):
    """Gibt den Namen der Handart zu einem Wert zurueck, z. B. "Full House"."""
    return HANDART_NAMEN[wert[0]]


def finde_gewinner(werte):
    """Gibt die Positionen (Indizes) aller Haende mit dem hoechsten Wert zurueck.

    Mehr als ein Index bedeutet Split Pot.
    """
    bester = max(werte)
    gewinner = []
    for i in range(len(werte)):
        if werte[i] == bester:
            gewinner.append(i)
    return gewinner
