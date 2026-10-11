"""Tests fuer poker/equity.py."""

import random

import pytest

from poker.equity import berechne_equity

ASSE = [(14, "Pik"), (14, "Herz")]
KOENIGE = [(13, "Pik"), (13, "Herz")]


def test_asse_gegen_koenige_rund_82_prozent():
    random.seed(1)
    equity = berechne_equity([ASSE, KOENIGE])
    # 10000 Durchlaeufe: Zufallsschwankung etwa +-1 Prozentpunkt
    assert 0.80 < equity[0] < 0.84


def test_summe_ist_eins():
    random.seed(2)
    equity = berechne_equity([ASSE, KOENIGE, [(7, "Karo"), (2, "Kreuz")]],
                             durchlaeufe=500)
    assert sum(equity) == pytest.approx(1.0)


def test_gleicher_seed_gleiches_ergebnis():
    random.seed(5)
    erstes = berechne_equity([ASSE, KOENIGE], durchlaeufe=300)
    random.seed(5)
    zweites = berechne_equity([ASSE, KOENIGE], durchlaeufe=300)
    assert erstes == zweites


def test_volles_board_ist_sicher():
    # River liegt, Koenige haben einen Drilling -> gewinnen immer.
    board = [(13, "Karo"), (9, "Pik"), (6, "Herz"), (4, "Kreuz"), (2, "Karo")]
    assert berechne_equity([ASSE, KOENIGE], board, durchlaeufe=50) == [0.0, 1.0]


def test_split_pot_zaehlt_halb():
    # Strasse auf dem Board, keiner kann sie verbessern.
    board = [(10, "Pik"), (9, "Herz"), (8, "Karo"), (7, "Kreuz"), (6, "Pik")]
    haende = [[(2, "Herz"), (3, "Karo")], [(2, "Kreuz"), (4, "Pik")]]
    assert berechne_equity(haende, board, durchlaeufe=50) == [0.5, 0.5]


def test_doppelte_karte_gibt_fehler():
    with pytest.raises(ValueError):
        berechne_equity([ASSE, [(14, "Pik"), (13, "Karo")]])


def test_karte_auf_board_und_hand_gibt_fehler():
    with pytest.raises(ValueError):
        berechne_equity([ASSE, KOENIGE], board=[(14, "Pik"), (2, "Herz"), (3, "Herz")])


def test_mindestens_zwei_spieler():
    with pytest.raises(ValueError):
        berechne_equity([ASSE])
