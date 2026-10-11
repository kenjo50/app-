"""Tests fuer poker/bereiche.py und equity_gegen_bereiche."""

import random

import pytest

from poker.bereiche import (
    ALLE_KOMBINATIONEN,
    RANGLISTE,
    anzahl_kombinationen,
    bereich,
    chen_punkte,
    hand_klasse,
    ist_im_bereich,
    konkrete_haende,
)
from poker.deck import lies_karten
from poker.equity import equity_gegen_bereiche


def test_hand_klasse():
    assert hand_klasse(lies_karten("As Ks")) == (14, 13, True)
    assert hand_klasse(lies_karten("Kh As")) == (14, 13, False)
    assert hand_klasse(lies_karten("7c 7d")) == (7, 7, False)


def test_chen_punkte_bekannte_werte():
    assert chen_punkte((14, 14, False)) == 20   # AA
    assert chen_punkte((13, 13, False)) == 16   # KK
    assert chen_punkte((2, 2, False)) == 5      # 22: mindestens 5
    assert chen_punkte((14, 13, True)) == 12    # AKs
    assert chen_punkte((11, 10, True)) == 9     # JTs: 6 + 2 + 1
    assert chen_punkte((7, 2, False)) == -1     # 72o: 3,5 - 5 = -1,5 -> aufgerundet -1


def test_rangliste_vollstaendig():
    assert len(RANGLISTE) == 169
    summe = sum(anzahl_kombinationen(k) for k in RANGLISTE)
    assert summe == ALLE_KOMBINATIONEN
    assert RANGLISTE[0] == (14, 14, False)


def test_bereiche():
    assert ist_im_bereich(lies_karten("As Ah"), 1)
    assert not ist_im_bereich(lies_karten("7c 2d"), 50)
    assert ist_im_bereich(lies_karten("7c 2d"), 100)
    assert bereich(0.4) == {(14, 14, False)}
    # Ein groesserer Bereich enthaelt immer den kleineren
    assert bereich(10) < bereich(20) < bereich(50)


def test_konkrete_haende():
    assert len(konkrete_haende(100)) == 1326
    assert len(konkrete_haende(0.4)) == 6                       # nur AA
    assert len(konkrete_haende(0.4, lies_karten("As"))) == 3    # ein Ass ist weg
    zehn = len(konkrete_haende(10))
    assert 120 <= zehn <= 150   # ca. 10 % von 1326


def test_equity_gegen_bereiche():
    zufall = random.Random(1)
    # KK gegen genau AA: ca. 18 %
    assert equity_gegen_bereiche(lies_karten("Ks Kh"), [], [0.4], 4000, zufall) == \
        pytest.approx(0.18, abs=0.025)
    # AK ist gegen einen engen Bereich deutlich schlechter als gegen einen weiten
    eng = equity_gegen_bereiche(lies_karten("As Kh"), [], [5], 2000, zufall)
    weit = equity_gegen_bereiche(lies_karten("As Kh"), [], [60], 2000, zufall)
    assert eng + 0.08 < weit


def test_equity_gegen_bereiche_mehrere_gegner_und_board():
    zufall = random.Random(2)
    wert = equity_gegen_bereiche(lies_karten("As Ah"), lies_karten("Ks 9h 4d"),
                                 [10, 40], 500, zufall)
    assert 0.5 < wert < 1


def test_equity_gegen_bereiche_fehler():
    with pytest.raises(ValueError):
        equity_gegen_bereiche(lies_karten("As Ah"), [], [])
    # Beide Asse weg, Bereich "nur AA" ist unmoeglich
    with pytest.raises(ValueError):
        equity_gegen_bereiche(lies_karten("As Ah"), lies_karten("Ad Ac 2h"), [0.4], 10)
