"""Tests fuer poker/messung.py (Prototypen je Tischgroesse messen)."""

import pytest

from poker.messung import als_python, miss_tischgroesse


def test_messung_liefert_alle_typen():
    ergebnis = miss_tischgroesse(3, 400, seed=1)   # 4 Runden: jeder Typ einmal gesetzt
    assert set(ergebnis) == {"felsen", "station", "maniac", "tag"}
    for vpip, pfr, aggression in ergebnis.values():
        assert 0 <= pfr <= vpip <= 1
        assert 0 <= aggression <= 1


def test_messung_ist_reproduzierbar():
    assert miss_tischgroesse(2, 100, seed=7) == miss_tischgroesse(2, 100, seed=7)


def test_felsen_spielt_weniger_als_station():
    ergebnis = miss_tischgroesse(4, 400, seed=3)
    assert ergebnis["felsen"][0] < ergebnis["station"][0]
    assert ergebnis["station"][1] < ergebnis["maniac"][1]


def test_falsche_tischgroesse():
    with pytest.raises(ValueError):
        miss_tischgroesse(1, 100)
    with pytest.raises(ValueError):
        miss_tischgroesse(10, 100)


def test_als_python_laesst_sich_einlesen():
    messungen = {2: {"felsen": (0.1, 0.05, 0.7)}, 3: {"felsen": (0.12, 0.06, 0.71)}}
    namensraum = {}
    exec(als_python(messungen), namensraum)
    assert namensraum["PROTOTYPEN_NACH_GROESSE"] == messungen
