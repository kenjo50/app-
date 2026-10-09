"""Tests fuer poker/bewertung.py.

Die Faelle sind 7 Karten (2 Handkarten + 5 Board-Karten), wie am Tisch.
"""

from poker.bewertung import (
    DRILLING,
    FLUSH,
    FULL_HOUSE,
    HOECHSTE_KARTE,
    PAAR,
    STRAIGHT_FLUSH,
    STRASSE,
    VIERLING,
    ZWEI_PAARE,
    bewerte_hand,
    finde_gewinner,
    handart_name,
)

# ---------- Jede Handart mindestens einmal ----------


def test_hoechste_karte():
    karten = [(14, "Pik"), (12, "Herz"), (9, "Karo"), (7, "Kreuz"),
              (5, "Pik"), (3, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (HOECHSTE_KARTE, 14, 12, 9, 7, 5)


def test_paar():
    karten = [(10, "Pik"), (10, "Herz"), (14, "Karo"), (8, "Kreuz"),
              (6, "Pik"), (4, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (PAAR, 10, 14, 8, 6)


def test_zwei_paare():
    karten = [(10, "Pik"), (10, "Herz"), (4, "Karo"), (4, "Kreuz"),
              (14, "Pik"), (8, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (ZWEI_PAARE, 10, 4, 14)


def test_drilling():
    karten = [(7, "Pik"), (7, "Herz"), (7, "Karo"), (13, "Kreuz"),
              (11, "Pik"), (4, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (DRILLING, 7, 13, 11)


def test_strasse():
    karten = [(9, "Pik"), (8, "Herz"), (7, "Karo"), (6, "Kreuz"),
              (5, "Pik"), (13, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (STRASSE, 9)


def test_flush():
    karten = [(14, "Herz"), (11, "Herz"), (8, "Herz"), (5, "Herz"),
              (3, "Herz"), (13, "Pik"), (12, "Karo")]
    assert bewerte_hand(karten) == (FLUSH, 14, 11, 8, 5, 3)


def test_full_house():
    karten = [(13, "Pik"), (13, "Herz"), (13, "Karo"), (4, "Kreuz"),
              (4, "Pik"), (9, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (FULL_HOUSE, 13, 4)


def test_vierling():
    karten = [(6, "Pik"), (6, "Herz"), (6, "Karo"), (6, "Kreuz"),
              (14, "Pik"), (10, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (VIERLING, 6, 14)


def test_straight_flush():
    karten = [(9, "Kreuz"), (8, "Kreuz"), (7, "Kreuz"), (6, "Kreuz"),
              (5, "Kreuz"), (14, "Herz"), (14, "Pik")]
    assert bewerte_hand(karten) == (STRAIGHT_FLUSH, 9)


def test_royal_flush_ist_hoechster_straight_flush():
    karten = [(14, "Pik"), (13, "Pik"), (12, "Pik"), (11, "Pik"),
              (10, "Pik"), (2, "Herz"), (3, "Karo")]
    assert bewerte_hand(karten) == (STRAIGHT_FLUSH, 14)


def test_reihenfolge_der_handarten():
    """Jede Handart schlaegt alle schwaecheren."""
    assert (HOECHSTE_KARTE < PAAR < ZWEI_PAARE < DRILLING < STRASSE
            < FLUSH < FULL_HOUSE < VIERLING < STRAIGHT_FLUSH)


# ---------- Sonderfaelle ----------


def test_zwei_drillinge_ergeben_full_house():
    karten = [(9, "Pik"), (9, "Herz"), (9, "Karo"), (5, "Kreuz"),
              (5, "Pik"), (5, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (FULL_HOUSE, 9, 5)


def test_drei_paare_ergeben_zwei_paare_mit_bestem_kicker():
    # Paare: Koenige, Achter, Dreier. Die Dreier fallen weg,
    # bester Kicker ist dann die 10 (nicht die 3 aus dem dritten Paar).
    karten = [(13, "Pik"), (13, "Herz"), (8, "Karo"), (8, "Kreuz"),
              (3, "Pik"), (3, "Herz"), (10, "Karo")]
    assert bewerte_hand(karten) == (ZWEI_PAARE, 13, 8, 10)


def test_drei_paare_kicker_aus_drittem_paar():
    # Hier ist der beste Kicker eine Karte aus dem dritten Paar (die 7).
    karten = [(13, "Pik"), (13, "Herz"), (8, "Karo"), (8, "Kreuz"),
              (7, "Pik"), (7, "Herz"), (2, "Karo")]
    assert bewerte_hand(karten) == (ZWEI_PAARE, 13, 8, 7)


def test_ass_niedrige_strasse():
    karten = [(14, "Pik"), (2, "Herz"), (3, "Karo"), (4, "Kreuz"),
              (5, "Pik"), (9, "Herz"), (13, "Karo")]
    assert bewerte_hand(karten) == (STRASSE, 5)


def test_ass_niedrige_strasse_ist_die_niedrigste():
    rad = bewerte_hand([(14, "Pik"), (2, "Herz"), (3, "Karo"), (4, "Kreuz"),
                        (5, "Pik"), (9, "Herz"), (13, "Karo")])
    sechs_hoch = bewerte_hand([(2, "Herz"), (3, "Karo"), (4, "Kreuz"),
                               (5, "Pik"), (6, "Pik"), (9, "Herz"), (13, "Karo")])
    assert rad < sechs_hoch


def test_ass_zaehlt_nicht_in_der_mitte():
    # K-A-2-3-4 ist KEINE Strasse.
    karten = [(13, "Pik"), (14, "Herz"), (2, "Karo"), (3, "Kreuz"),
              (4, "Pik"), (9, "Herz"), (7, "Karo")]
    assert bewerte_hand(karten)[0] == HOECHSTE_KARTE


def test_laengere_strasse_zaehlt_hoechste_fuenf():
    # 4-5-6-7-8-9 vorhanden -> Strasse bis 9.
    karten = [(4, "Pik"), (5, "Herz"), (6, "Karo"), (7, "Kreuz"),
              (8, "Pik"), (9, "Herz"), (13, "Karo")]
    assert bewerte_hand(karten) == (STRASSE, 9)


def test_flush_mit_sechs_karten_beste_fuenf():
    karten = [(14, "Karo"), (12, "Karo"), (10, "Karo"), (7, "Karo"),
              (4, "Karo"), (2, "Karo"), (13, "Pik")]
    assert bewerte_hand(karten) == (FLUSH, 14, 12, 10, 7, 4)


def test_flush_mit_sieben_karten_beste_fuenf():
    karten = [(13, "Herz"), (11, "Herz"), (9, "Herz"), (7, "Herz"),
              (5, "Herz"), (3, "Herz"), (2, "Herz")]
    assert bewerte_hand(karten) == (FLUSH, 13, 11, 9, 7, 5)


def test_strasse_und_flush_aber_kein_straight_flush():
    # Strasse 5-6-7-8-9 (gemischte Farben) und ein Herz-Flush,
    # aber die Herz-Karten bilden keine Strasse -> Flush.
    karten = [(5, "Herz"), (6, "Pik"), (7, "Herz"), (8, "Karo"),
              (9, "Herz"), (13, "Herz"), (2, "Herz")]
    assert bewerte_hand(karten) == (FLUSH, 13, 9, 7, 5, 2)


def test_straight_flush_schlaegt_hoehere_strasse():
    # Herz 5-9 ist Straight Flush, zusaetzlich gibt es eine 10 (Strasse bis 10).
    karten = [(5, "Herz"), (6, "Herz"), (7, "Herz"), (8, "Herz"),
              (9, "Herz"), (10, "Pik"), (2, "Karo")]
    assert bewerte_hand(karten) == (STRAIGHT_FLUSH, 9)


# ---------- Haende vergleichen ----------

BOARD = [(13, "Pik"), (13, "Herz"), (8, "Karo"), (5, "Kreuz"), (2, "Pik")]


def test_kicker_entscheidet():
    # Beide haben ein Koenigspaar (vom Board). Ass-Kicker schlaegt Dame-Kicker.
    spieler_a = [(14, "Karo"), (3, "Herz")]
    spieler_b = [(12, "Karo"), (4, "Herz")]
    wert_a = bewerte_hand(spieler_a + BOARD)
    wert_b = bewerte_hand(spieler_b + BOARD)
    assert wert_a[0] == PAAR and wert_b[0] == PAAR
    assert wert_a > wert_b
    assert finde_gewinner([wert_a, wert_b]) == [0]


def test_kicker_bei_gleichem_paar_aus_der_hand():
    board = [(10, "Pik"), (9, "Herz"), (6, "Karo"), (4, "Kreuz"), (2, "Pik")]
    wert_a = bewerte_hand([(14, "Pik"), (11, "Herz")] + board)  # A-B: Hoechste Karte
    wert_b = bewerte_hand([(14, "Herz"), (12, "Karo")] + board)  # A-D: besser
    assert wert_b > wert_a


def test_split_pot():
    # Das Board ist eine Strasse, keiner verbessert sie -> beide gleich stark.
    board = [(10, "Pik"), (9, "Herz"), (8, "Karo"), (7, "Kreuz"), (6, "Pik")]
    wert_a = bewerte_hand([(2, "Herz"), (3, "Karo")] + board)
    wert_b = bewerte_hand([(2, "Kreuz"), (4, "Pik")] + board)
    assert wert_a == wert_b == (STRASSE, 10)
    assert finde_gewinner([wert_a, wert_b]) == [0, 1]


def test_split_pot_gleiche_kicker_mit_verschiedenen_farben():
    spieler_a = [(14, "Karo"), (3, "Herz")]
    spieler_b = [(14, "Kreuz"), (3, "Karo")]
    wert_a = bewerte_hand(spieler_a + BOARD)
    wert_b = bewerte_hand(spieler_b + BOARD)
    assert wert_a == wert_b
    assert finde_gewinner([wert_a, wert_b]) == [0, 1]


def test_handart_name():
    assert handart_name((FULL_HOUSE, 13, 4)) == "Full House"
