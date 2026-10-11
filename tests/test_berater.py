"""Tests fuer poker/berater.py: KI-Empfehlung fuer den Helden am Live-Tisch."""

import pytest

from poker import tisch
from poker.berater import empfehlung
from poker.deck import lies_karten
from poker.profile import oeffne_datenbank

SPIELER = ["Anna", "Ben", "Clara"]
STACKS = {"Anna": 1000, "Ben": 1000, "Clara": 1000}


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def hand_mit_held(db, held, karten, spieler=SPIELER, stacks=STACKS):
    abend = tisch.neuer_abend(db, spieler, stacks, 10, 20)
    tisch.setze_held(db, abend, held)
    tisch.starte_naechste_hand(db, abend)
    tisch.setze_held_karten(abend, lies_karten(karten))
    return abend


def test_fehler_ohne_held_karten_oder_nicht_dran(db):
    abend = tisch.neuer_abend(db, SPIELER, STACKS, 10, 20)
    tisch.starte_naechste_hand(db, abend)
    with pytest.raises(ValueError):
        empfehlung(db, abend)                        # kein Held
    tisch.setze_held(db, abend, "Ben")
    with pytest.raises(ValueError):
        empfehlung(db, abend)                        # keine Karten
    tisch.setze_held_karten(abend, lies_karten("As Ah"))
    with pytest.raises(ValueError):
        empfehlung(db, abend)                        # Clara ist dran, nicht Ben


def test_asse_werden_erhoeht(db):
    abend = hand_mit_held(db, "Clara", "As Ah")
    e = empfehlung(db, abend, durchlaeufe=500)
    assert e["aktion"] == "raise"
    assert e["betrag"] % 10 == 0                     # zahlbar mit 10-Cent-Chips
    assert e["equity"] > 0.6
    assert any("erhoehen" in g for g in e["gruende"])


def test_schwache_hand_gegen_grossen_raise_fold(db):
    abend = hand_mit_held(db, "Anna", "7c 2d")
    tisch.aktion(db, abend, "raise", 300)            # Clara erhoeht kraeftig
    e = empfehlung(db, abend, durchlaeufe=500)
    assert e["aktion"] == "fold"
    assert e["equity"] < e["pot_odds"]


def test_gleiche_situation_gleiche_empfehlung(db):
    abend = hand_mit_held(db, "Clara", "Kd Jc")
    assert empfehlung(db, abend, 300) == empfehlung(db, abend, 300)


def test_empfehlung_auf_dem_flop(db):
    abend = hand_mit_held(db, "Ben", "Kd Kc")
    tisch.aktion(db, abend, "call")    # Clara
    tisch.aktion(db, abend, "call")    # Anna
    tisch.aktion(db, abend, "check")   # Ben
    tisch.board_karten(db, abend, lies_karten("Ks 9h 4d"))   # Set Koenige
    tisch.aktion(db, abend, "check")   # Anna
    assert tisch.anzeige(abend)["hand"]["held_dran"]
    e = empfehlung(db, abend, durchlaeufe=500)
    assert e["aktion"] == "raise" and e["equity"] > 0.8


def test_held_karten_pruefen(db):
    abend = hand_mit_held(db, "Ben", "Kd Kc")
    with pytest.raises(ValueError):
        tisch.setze_held_karten(abend, lies_karten("Kd Kd"))
    with pytest.raises(ValueError):
        tisch.setze_held_karten(abend, lies_karten("Kd"))
    for aktion in ["call", "call", "check"]:
        tisch.aktion(db, abend, aktion)
    with pytest.raises(ValueError):
        tisch.board_karten(db, abend, lies_karten("Kd 9h 4d"))   # Kd hat der Held


def test_held_wechseln(db):
    abend = hand_mit_held(db, "Ben", "Kd Kc")
    tisch.setze_held(db, abend, "Anna")
    assert tisch.anzeige(abend)["hand"]["held_karten"] is None
    assert tisch.lade_abend(db)["held"] == "Anna"
    with pytest.raises(ValueError):
        tisch.setze_held(db, abend, "Zoe")


def test_profile_aus_der_datenbank_werden_genutzt(db):
    # Vorgeschichte: "Station 1" hat 150 Haende als Calling Station gespielt
    from poker.simulation import simuliere
    simuliere(db, ["station", "felsen", "tag"], 150, seed=3)
    abend = tisch.neuer_abend(db, ["Felsen 1", "Station 1", "Ich"],
                              {"Felsen 1": 1000, "Station 1": 1000, "Ich": 1000}, 10, 20)
    tisch.setze_held(db, abend, "Ich")
    tisch.starte_naechste_hand(db, abend)
    tisch.setze_held_karten(abend, lies_karten("As Kd"))
    e = empfehlung(db, abend, durchlaeufe=300)
    typen = {g["name"]: g["typ"] for g in e["gegner"]}
    assert typen["Station 1"] == "station"
    assert any("Station 1: Calling Station" in g for g in e["gruende"])
