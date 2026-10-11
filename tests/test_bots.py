"""Tests fuer poker/bots.py."""

import random

from poker.bots import equity_bot, pot_odds, raise_betrag, zufalls_bot
from poker.deck import lies_karten


def sicht(**werte):
    """Eine Beispiel-Sicht: Flop, Pot 20, nichts zu callen. Werte ueberschreibbar."""
    grund = {
        "name": "Bot", "handkarten": lies_karten("As Ah"), "board": lies_karten("Ks 9h 4d"),
        "strasse": "flop", "pot": 20, "zu_callen": 0, "hoechster": 0, "einsatz": 0,
        "stack": 200, "maximal": 200, "mindest_erhoehung": 2, "darf_erhoehen": True,
        "erlaubt": ["check", "raise"], "gegner": 1, "big_blind": 2,
        "verlauf": [], "aktive_gegner": ["Gegner"],
    }
    grund.update(werte)
    return grund


# ---------- Raise-Groessen ----------


def test_raise_betrag_ohne_vorherigen_einsatz():
    s = sicht()
    assert raise_betrag(s, "halber_pot") == 10
    assert raise_betrag(s, "pot") == 20
    assert raise_betrag(s, "allin") == 200


def test_raise_betrag_nach_einem_bet():
    # Gegner setzt 10 in Pot 20 -> Pot 30, ich muss 10 callen.
    # Pot-Raise: 10 + (30 + 10) = auf 50
    s = sicht(pot=30, zu_callen=10, hoechster=10, mindest_erhoehung=20,
              erlaubt=["fold", "call", "raise"])
    assert raise_betrag(s, "pot") == 50
    assert raise_betrag(s, "halber_pot") == 30


def test_raise_betrag_grenzen():
    # Mindestens die Mindest-Erhoehung, hoechstens der Stack
    assert raise_betrag(sicht(pot=2, mindest_erhoehung=2), "halber_pot") == 2
    assert raise_betrag(sicht(pot=1000, maximal=150), "pot") == 150


def test_pot_odds():
    assert pot_odds(sicht(pot=10, zu_callen=5)) == 5 / 15
    assert pot_odds(sicht()) == 0


# ---------- Zufalls-Bot ----------


def test_zufalls_bot_waehlt_nur_erlaubtes():
    zufall = random.Random(1)
    gesehen = set()
    for i in range(300):
        aktion, betrag = zufalls_bot(sicht(erlaubt=["fold", "call", "raise"], pot=30, zu_callen=10,
                                           hoechster=10, mindest_erhoehung=20), zufall)
        gesehen.add(aktion)
        assert aktion in ["fold", "call", "raise"]
        if aktion == "raise":
            assert betrag in [30, 50, 200]   # halber Pot, Pot, All-in
        else:
            assert betrag is None
    assert gesehen == {"fold", "call", "raise"}  # alle kommen vor


def test_zufalls_bot_etwa_gleich_verteilt():
    zufall = random.Random(2)
    zaehler = {"check": 0, "raise": 0}
    for i in range(2000):
        zaehler[zufalls_bot(sicht(), zufall)[0]] += 1
    assert 900 < zaehler["check"] < 1100


# ---------- Equity-Bot ----------


def test_equity_bot_erhoeht_mit_starker_hand():
    # Asse auf K-9-4: weit ueber 70 % -> Raise um den Pot
    assert equity_bot(sicht(), random.Random(3)) == ("raise", 20)


def test_equity_bot_checkt_mit_schwacher_hand():
    s = sicht(handkarten=lies_karten("7c 2h"))
    assert equity_bot(s, random.Random(4)) == ("check", None)


def test_equity_bot_foldet_ohne_pot_odds():
    # 7-2 ohne Treffer gegen einen grossen Bet: Pot Odds ca. 47 %, Equity viel weniger
    s = sicht(handkarten=lies_karten("7c 2h"), pot=170, zu_callen=150, hoechster=150,
              mindest_erhoehung=300, erlaubt=["fold", "call", "raise"])
    assert equity_bot(s, random.Random(5)) == ("fold", None)


def test_equity_bot_callt_mit_guten_pot_odds():
    # T-8 ohne Treffer gegen einen kleinen Bet: ca. 32 % Equity, Pot Odds nur ca. 8 %
    s = sicht(handkarten=lies_karten("Tc 8c"), board=lies_karten("Kh 9h 4d"),
              pot=22, zu_callen=2, hoechster=2, mindest_erhoehung=4,
              erlaubt=["fold", "call", "raise"])
    assert equity_bot(s, random.Random(6)) == ("call", None)
