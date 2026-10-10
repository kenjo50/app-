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


def bewerte_hand_einfach(karten):
    """Bewertet 5 bis 7 Karten: die beste Fuenfer-Kombination zaehlt.

    Bei 7 Karten sind das 21 Kombinationen. Einfach und sicher, aber langsam.
    Diese Version bleibt als Referenz: Die schnelle Version wird in den Tests
    an vielen Zufallshaenden gegen sie geprueft.
    """
    if len(karten) < 5 or len(karten) > 7:
        raise ValueError("bewerte_hand braucht 5 bis 7 Karten")
    bester_wert = None
    for fuenf in combinations(karten, 5):
        wert = bewerte_fuenf(fuenf)
        if bester_wert is None or wert > bester_wert:
            bester_wert = wert
    return bester_wert


def _hoechste_strasse(raenge):
    """Hoechste Karte der besten Strasse in einer Menge von Raengen, sonst None."""
    for hoch in range(14, 5, -1):
        if (hoch in raenge and hoch - 1 in raenge and hoch - 2 in raenge
                and hoch - 3 in raenge and hoch - 4 in raenge):
            return hoch
    if 14 in raenge and 2 in raenge and 3 in raenge and 4 in raenge and 5 in raenge:
        return 5  # A-2-3-4-5, das Ass zaehlt unten
    return None


def bewerte_hand(karten):
    """Bewertet 5 bis 7 Karten direkt, ohne alle Fuenfer-Kombinationen zu probieren.

    Liefert genau dasselbe Tupel wie bewerte_hand_einfach, ist aber etwa
    zehnmal schneller. Das braucht die Simulation mit vielen tausend Haenden.
    Vorgehen: Raenge und Farben zaehlen, dann von der besten Handart
    abwaerts pruefen.
    """
    if len(karten) < 5 or len(karten) > 7:
        raise ValueError("bewerte_hand braucht 5 bis 7 Karten")

    # Raenge pro Farbe und Anzahl pro Rang sammeln
    pro_farbe = {}
    anzahl = {}
    for rang, farbe in karten:
        if farbe not in pro_farbe:
            pro_farbe[farbe] = []
        pro_farbe[farbe].append(rang)
        anzahl[rang] = anzahl.get(rang, 0) + 1

    # Flush und Straight Flush (bei 7 Karten kann es nur eine Flush-Farbe geben)
    flush_raenge = None
    for raenge in pro_farbe.values():
        if len(raenge) >= 5:
            flush_raenge = sorted(raenge, reverse=True)
    if flush_raenge is not None:
        hoch = _hoechste_strasse(set(flush_raenge))
        if hoch is not None:
            return (STRAIGHT_FLUSH, hoch)

    # Raenge nach Anzahl gruppieren, jeweils absteigend
    vierlinge = []
    drillinge = []
    paare = []
    einzelne = []
    for rang in sorted(anzahl, reverse=True):
        if anzahl[rang] == 4:
            vierlinge.append(rang)
        elif anzahl[rang] == 3:
            drillinge.append(rang)
        elif anzahl[rang] == 2:
            paare.append(rang)
        else:
            einzelne.append(rang)

    if vierlinge:
        rest = [r for r in anzahl if r != vierlinge[0]]
        return (VIERLING, vierlinge[0], max(rest))

    if drillinge and (len(drillinge) >= 2 or paare):
        # Zweiter Drilling oder bestes Paar fuellt das Full House auf
        kandidaten = drillinge[1:] + paare
        return (FULL_HOUSE, drillinge[0], max(kandidaten))

    if flush_raenge is not None:
        return (FLUSH, *flush_raenge[:5])

    hoch = _hoechste_strasse(set(anzahl))
    if hoch is not None:
        return (STRASSE, hoch)

    if drillinge:
        kicker = sorted(paare + einzelne, reverse=True)[:2]
        return (DRILLING, drillinge[0], *kicker)

    if len(paare) >= 2:
        # Drittes Paar kann Kicker sein
        kicker = max(paare[2:] + einzelne)
        return (ZWEI_PAARE, paare[0], paare[1], kicker)

    if paare:
        return (PAAR, paare[0], *einzelne[:3])

    return (HOECHSTE_KARTE, *einzelne[:5])


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
