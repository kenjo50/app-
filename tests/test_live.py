"""Tests fuer poker/live.py."""

import pytest

from poker.live import (
    beende_hand,
    finde_spieler,
    lies_aktion,
    naechste_strasse,
    pot,
    rotiere,
    starte_hand,
    verarbeite_aktion,
    zu_callen,
)
from poker.profile import berechne_statistik, lade_aktionen, oeffne_datenbank

NAMEN = ["Anna", "Ben", "Clara"]  # Anna = Small Blind, Ben = Big Blind


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


# ---------- Eingabe zerlegen ----------


def test_lies_aktion():
    assert lies_aktion("anna r 6", NAMEN) == ("Anna", "raise", 6.0)
    assert lies_aktion("Ben c", NAMEN) == ("Ben", "call", None)
    assert lies_aktion("cl f", NAMEN) == ("Clara", "fold", None)
    assert lies_aktion("anna bet 2,5", NAMEN) == ("Anna", "raise", 2.5)


def test_lies_aktion_fehler():
    for falsch in ["anna", "anna q", "anna r", "anna r viel", "anna c 5", "zoe f"]:
        with pytest.raises(ValueError):
            lies_aktion(falsch, NAMEN)


def test_finde_spieler_mehrdeutig():
    with pytest.raises(ValueError):
        finde_spieler("an", ["Anna", "Andi"])
    assert finde_spieler("ann", ["Anna", "Andi"]) == "Anna"


# ---------- Mitrechnen ----------


def test_blinds_werden_gesetzt(db):
    zustand = starte_hand(db, NAMEN, 1, 2)
    assert pot(zustand) == 3
    assert zu_callen(zustand, "Anna") == 1
    assert zu_callen(zustand, "Ben") == 0
    assert zu_callen(zustand, "Clara") == 2


def test_ganze_hand(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "fold")
    assert verarbeite_aktion(db, z, "Ben", "call") == ("call", 6)
    assert pot(z) == 13  # 1 (Anna) + 6 + 6

    assert naechste_strasse(z) == "flop"
    assert pot(z) == 13
    assert verarbeite_aktion(db, z, "Ben", "call") == ("check", 0)  # nichts offen
    assert verarbeite_aktion(db, z, "Clara", "raise", 8) == ("bet", 8)  # erster Einsatz
    verarbeite_aktion(db, z, "Ben", "raise", 20)
    verarbeite_aktion(db, z, "Clara", "call")
    assert pot(z) == 53

    naechste_strasse(z)
    naechste_strasse(z)
    verarbeite_aktion(db, z, "Ben", "check")
    verarbeite_aktion(db, z, "Clara", "check")
    beende_hand(z)
    assert z["beendet"]

    assert lade_aktionen(db, z["hand_id"]) == [
        ("Clara", "preflop", "raise", 6),
        ("Anna", "preflop", "fold", 0),
        ("Ben", "preflop", "call", 6),
        ("Ben", "flop", "check", 0),
        ("Clara", "flop", "bet", 8),
        ("Ben", "flop", "raise", 20),
        ("Clara", "flop", "call", 20),
        ("Ben", "river", "check", 0),
        ("Clara", "river", "check", 0),
    ]
    # Die Statistik funktioniert direkt mit den gespeicherten Daten.
    assert berechne_statistik(db, "Clara")["pfr"] == 1.0


def test_hand_endet_wenn_alle_folden(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "fold")
    verarbeite_aktion(db, z, "Anna", "fold")
    assert z["beendet"]
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Ben", "check")


def test_big_blind_darf_checken(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    assert verarbeite_aktion(db, z, "Ben", "call") == ("check", 0)
    assert naechste_strasse(z) == "flop"


def test_ungueltige_aktionen(db):
    z = starte_hand(db, NAMEN, 1, 2)
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "check")      # 2 offen
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "raise", 2)   # nicht hoeher als 2
    verarbeite_aktion(db, z, "Clara", "fold")
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "call")       # schon raus
    # Fehlerhafte Eingaben duerfen nichts in die Datenbank schreiben.
    assert lade_aktionen(db, z["hand_id"]) == [("Clara", "preflop", "fold", 0)]


def test_strasse_erst_wenn_alle_bezahlt(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    with pytest.raises(ValueError):
        naechste_strasse(z)


def test_ende_erst_nach_river(db):
    z = starte_hand(db, NAMEN, 1, 2)
    with pytest.raises(ValueError):
        beende_hand(z)


def test_rotiere():
    assert rotiere(["Anna", "Ben", "Clara"]) == ["Ben", "Clara", "Anna"]
