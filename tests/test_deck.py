"""Tests fuer poker/deck.py."""

from poker.deck import austeilen, erzeuge_deck, zaehle_raenge


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
