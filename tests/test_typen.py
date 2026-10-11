"""Tests fuer poker/typen.py: Die Typ-Bots spielen erkennbar unterschiedlich."""

import random

import pytest

from poker.deck import lies_karten
from poker.profile import berechne_statistik
from poker.simulation import erstelle_aufstellung, oeffne_simulationsdatenbank, simuliere
from poker.typen import ALLE_TYPEN, GRUNDTYPEN, erstelle_typ_bot, streue_werte


def sicht(**werte):
    grund = {
        "name": "Bot", "handkarten": lies_karten("As Ah"), "board": [],
        "strasse": "preflop", "pot": 3, "zu_callen": 2, "hoechster": 2, "einsatz": 0,
        "stack": 200, "maximal": 200, "mindest_erhoehung": 4, "darf_erhoehen": True,
        "erlaubt": ["fold", "call", "raise"], "gegner": 2, "big_blind": 2,
        "verlauf": [], "aktive_gegner": ["A", "B"],
    }
    grund.update(werte)
    return grund


def test_mischtyp_ist_kein_grundtyp():
    assert "misch" in ALLE_TYPEN and "misch" not in GRUNDTYPEN


def test_streuung():
    zufall = random.Random(1)
    ohne = streue_werte(GRUNDTYPEN["felsen"], zufall, staerke=0)
    assert ohne == GRUNDTYPEN["felsen"]
    vpip_werte = [streue_werte(GRUNDTYPEN["station"], zufall)["vpip"] for i in range(200)]
    assert min(vpip_werte) < 50 < 60 < max(vpip_werte)   # es gibt Streuung ...
    assert 50 < sum(vpip_werte) / len(vpip_werte) < 60    # ... um den Grundwert
    for i in range(200):
        werte = streue_werte(GRUNDTYPEN["tag"], zufall)
        assert werte["pfr"] <= werte["vpip"]
        assert 0 <= werte["bluff"] <= 1


def test_felsen_preflop():
    bot, werte = erstelle_typ_bot("felsen", random.Random(2), streuung=0)
    assert bot(sicht(), random.Random(3))[0] == "raise"                           # AA
    assert bot(sicht(handkarten=lies_karten("9c 4d")), random.Random(3))[0] == "fold"
    # Big Blind ohne Erhoehung: checkt statt zu folden
    s = sicht(handkarten=lies_karten("9c 4d"), zu_callen=0, erlaubt=["check", "raise"])
    assert bot(s, random.Random(3))[0] == "check"


def test_station_callt_viel():
    bot, werte = erstelle_typ_bot("station", random.Random(2), streuung=0)
    assert bot(sicht(handkarten=lies_karten("Kc 8d")), random.Random(3))[0] == "call"
    # Nach dem Flop: callt einen Pot-Bet auch ohne Treffer
    s = sicht(handkarten=lies_karten("Kc 8d"), board=lies_karten("Ah 7s 2d"), strasse="flop",
              pot=20, zu_callen=10, hoechster=10, mindest_erhoehung=20, gegner=1)
    assert bot(s, random.Random(4))[0] == "call"


def test_unbekannter_typ():
    with pytest.raises(ValueError):
        erstelle_typ_bot("hai", random.Random(1))


def test_aufstellung_mit_typen():
    bots = erstelle_aufstellung(["felsen", "felsen", "station"], random.Random(1))
    assert list(bots) == ["Felsen 1", "Felsen 2", "Station 1"]


def test_typen_sind_in_der_statistik_unterscheidbar():
    db = oeffne_simulationsdatenbank(":memory:")
    simuliere(db, ["felsen", "station", "maniac", "tag"], 300, seed=8)
    felsen = berechne_statistik(db, "Felsen 1")
    station = berechne_statistik(db, "Station 1")
    maniac = berechne_statistik(db, "Maniac 1")
    tag = berechne_statistik(db, "Tag 1")
    assert felsen["vpip"] < tag["vpip"] < station["vpip"]
    assert station["pfr"] < tag["pfr"] < maniac["pfr"]
    # Passiv (AF unter 1) gegen aggressiv (AF ueber 1)
    assert station["af"] < 1 < tag["af"]
    assert 1 < maniac["af"]
