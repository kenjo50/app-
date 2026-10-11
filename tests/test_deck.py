"""Tests fuer poker/deck.py."""

import pytest

from poker.deck import austeilen, erzeuge_deck, lies_karten, zaehle_raenge


def test_deck_hat_52_verschiedene_karten():
    deck = erzeuge_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52


def test_deck_ist_ungemischt():
    deck = erzeuge_deck()
    assert deck[0] == (2, "Karo")
    assert deck[-1] == (14, "Kreuz")


def test_austeilen_entfernt_karten_aus_deck():
    deck = erzeuge_deck()
    hand = austeilen(deck, 2)
    assert len(hand) == 2
    assert len(deck) == 50
    for karte in hand:
        assert karte not in deck


def test_zaehle_raenge():
    karten = [(14, "Pik"), (14, "Herz"), (7, "Karo")]
    assert zaehle_raenge(karten) == {14: 2, 7: 1}


def test_lies_karten():
    assert lies_karten("As Kh") == [(14, "Pik"), (13, "Herz")]
    assert lies_karten("10d Tc") == [(10, "Karo"), (10, "Kreuz")]
    assert lies_karten("QsDh") == [(12, "Pik"), (12, "Herz")]
    assert lies_karten("jc BD") == [(11, "Kreuz"), (11, "Karo")]
    assert lies_karten("") == []


def test_lies_karten_fehler():
    for falsch in ["A", "1s", "Ax", "As As", "11h", "As K"]:
        with pytest.raises(ValueError):
            lies_karten(falsch)
