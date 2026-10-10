"""Tests fuer poker/clock.py: welche Ansage bei welcher Sekunde."""

import pytest

from poker.clock import (
    aktualisiere_clock,
    ansage_punkte,
    clock_restzeit,
    neue_clock,
    starte_clock,
    stoppe_clock,
)

START = 500.0


def nur_texte(punkte):
    ergebnis = []
    for restzeit, text, art in punkte:
        ergebnis.append(text if art == "sprache" else "PIEP")
    return ergebnis


def test_punkte_bei_30_sekunden():
    assert nur_texte(ansage_punkte(30)) == ["30 Sekunden", "20", "10", "3", "2", "1", "PIEP"]


def test_punkte_bei_45_sekunden():
    assert nur_texte(ansage_punkte(45)) == [
        "45 Sekunden", "40", "30", "20", "10", "3", "2", "1", "PIEP"]


def test_punkte_bei_kurzen_zeiten():
    assert nur_texte(ansage_punkte(10)) == ["10 Sekunden", "3", "2", "1", "PIEP"]
    assert nur_texte(ansage_punkte(5)) == ["5 Sekunden", "3", "2", "1", "PIEP"]
    assert nur_texte(ansage_punkte(3)) == ["3 Sekunden", "2", "1", "PIEP"]
    assert nur_texte(ansage_punkte(1)) == ["1 Sekunde", "PIEP"]


def test_ungueltige_zeit():
    for falsch in [0, -5, 2.5]:
        with pytest.raises(ValueError):
            ansage_punkte(falsch)


def test_ansagen_zur_richtigen_sekunde():
    c = neue_clock()
    start = starte_clock(c, START)  # Standard 30 Sekunden
    assert [a["text"] for a in start] == ["30 Sekunden"]

    # Sekunde fuer Sekunde durchgehen und notieren, wann was kommt
    gehoert = {}
    for sekunde in range(1, 31):
        for ansage in aktualisiere_clock(c, START + sekunde):
            gehoert[sekunde] = ansage["text"] if ansage["art"] == "sprache" else "PIEP"
    assert gehoert == {10: "20", 20: "10", 27: "3", 28: "2", 29: "1", 30: "PIEP"}
    assert not c["laeuft"]


def test_45_sekunden_zeitpunkte():
    c = neue_clock()
    starte_clock(c, START, 45)
    zeiten = []
    for ansage in aktualisiere_clock(c, START + 45):
        zeiten.append((ansage["zeit"] - START, ansage["text"]))
    assert zeiten == [(5, "40"), (15, "30"), (25, "20"), (35, "10"),
                      (42, "3"), (43, "2"), (44, "1"), (45, "")]


def test_keine_doppelten_ansagen():
    c = neue_clock()
    starte_clock(c, START)
    assert len(aktualisiere_clock(c, START + 10)) == 1
    assert aktualisiere_clock(c, START + 10.5) == []


def test_abbrechen():
    c = neue_clock()
    starte_clock(c, START, spieler="Ben")
    assert c["spieler"] == "Ben"
    stoppe_clock(c)
    assert aktualisiere_clock(c, START + 30) == []
    assert clock_restzeit(c, START + 5) == 0


def test_restzeit_aus_zeitstempel():
    c = neue_clock()
    starte_clock(c, START, 45)
    assert clock_restzeit(c, START + 12.5) == pytest.approx(32.5)


def test_neustart_nach_abbruch():
    c = neue_clock()
    starte_clock(c, START)
    stoppe_clock(c)
    starte_clock(c, START + 100, 20)
    assert [a["text"] for a in aktualisiere_clock(c, START + 110)] == ["10"]
