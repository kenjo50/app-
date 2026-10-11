"""Handbereiche: Welche Starthaende spielt ein Spieler?

Ein Felsen spielt z. B. nur die besten 8 % aller Starthaende, eine Calling
Station 50 %. Damit die KI gegen solche "Bereiche" rechnen kann, werden alle
169 Starthand-Klassen nach Staerke geordnet.

Staerke nach der Chen-Formel (bekannte Faustformel von Bill Chen):
- hoechste Karte: Ass 10, Koenig 8, Dame 7, Bube 6, sonst Rang / 2
- Paar: Punkte verdoppeln (mindestens 5)
- gleiche Farbe (suited): +2
- Luecke zwischen den Karten: 1 -> -1, 2 -> -2, 3 -> -4, 4 und mehr -> -5
- +1, wenn Luecke 0 oder 1 und beide Karten kleiner als Dame (Strassen-Chance)
- auf ganze Zahl aufrunden

Eine Starthand-Klasse ist ein Tupel (hoch, niedrig, suited), z. B.
(14, 13, True) fuer Ass-Koenig gleichfarbig, (7, 7, False) fuer 77.
"""

import math

from poker.deck import FARBEN, RAENGE

ALLE_KOMBINATIONEN = 1326  # 52 * 51 / 2 moegliche Starthaende


def hand_klasse(karten):
    """(14, "Pik"), (13, "Pik") -> (14, 13, True)"""
    (rang1, farbe1), (rang2, farbe2) = karten
    hoch = max(rang1, rang2)
    niedrig = min(rang1, rang2)
    suited = farbe1 == farbe2 and hoch != niedrig
    return (hoch, niedrig, suited)


def _kartenpunkte(rang):
    if rang == 14:
        return 10
    if rang == 13:
        return 8
    if rang == 12:
        return 7
    if rang == 11:
        return 6
    return rang / 2


def chen_punkte(klasse):
    """Chen-Punkte einer Starthand-Klasse. AA = 20, AKs = 12, 72o = -1."""
    hoch, niedrig, suited = klasse
    punkte = _kartenpunkte(hoch)
    if hoch == niedrig:
        return max(5, math.ceil(punkte * 2))
    if suited:
        punkte = punkte + 2
    luecke = hoch - niedrig - 1
    abzug = {0: 0, 1: 1, 2: 2, 3: 4}
    punkte = punkte - abzug.get(luecke, 5)
    if luecke <= 1 and hoch < 12:
        punkte = punkte + 1
    return math.ceil(punkte)


def anzahl_kombinationen(klasse):
    """Wie viele konkrete Kartenpaare gehoeren zur Klasse? Paar 6, suited 4, offsuit 12."""
    hoch, niedrig, suited = klasse
    if hoch == niedrig:
        return 6
    return 4 if suited else 12


def _alle_klassen():
    klassen = []
    for hoch in RAENGE:
        for niedrig in RAENGE:
            if niedrig > hoch:
                continue
            klassen.append((hoch, niedrig, False))
            if niedrig < hoch:
                klassen.append((hoch, niedrig, True))
    # Staerkste zuerst; bei gleichen Punkten entscheiden hohe Karten, dann suited
    klassen.sort(key=lambda k: (chen_punkte(k), k[0], k[1], k[2]), reverse=True)
    return klassen


# Alle 169 Klassen, staerkste zuerst
RANGLISTE = _alle_klassen()


def bereich(prozent):
    """Menge der Starthand-Klassen in den besten `prozent` % aller Haende.

    Gezaehlt wird nach konkreten Kombinationen (ein Paar zaehlt 6, AKo 12).
    100 bedeutet: alle Haende.
    """
    if prozent >= 100:
        return set(RANGLISTE)
    grenze = prozent / 100 * ALLE_KOMBINATIONEN
    klassen = set()
    summe = 0
    for klasse in RANGLISTE:
        if summe >= grenze:
            break
        klassen.add(klasse)
        summe = summe + anzahl_kombinationen(klasse)
    return klassen


def ist_im_bereich(karten, prozent):
    """Gehoert diese Starthand zu den besten `prozent` %?"""
    return hand_klasse(karten) in bereich(prozent)


def konkrete_haende(prozent, tote_karten=()):
    """Alle konkreten Kartenpaare im Bereich, ohne bereits bekannte Karten."""
    klassen = bereich(prozent)
    tot = set(tote_karten)
    haende = []
    for i in range(len(RAENGE)):
        for j in range(i, len(RAENGE)):
            for f1 in range(len(FARBEN)):
                for f2 in range(len(FARBEN)):
                    karte1 = (RAENGE[i], FARBEN[f1])
                    karte2 = (RAENGE[j], FARBEN[f2])
                    if i == j and f2 <= f1:
                        continue  # jedes Paar nur einmal
                    if karte1 in tot or karte2 in tot:
                        continue
                    if hand_klasse([karte1, karte2]) in klassen:
                        haende.append([karte1, karte2])
    return haende
