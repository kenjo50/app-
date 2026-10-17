"""Tests fuer den Lerntisch (poker/lerntisch.py)."""

import random

import pytest

from poker import lerntisch
from poker.profile import (aktion_speichern, ergebnis_speichern, hand_abschliessen, neue_hand,
                           oeffne_datenbank)
from poker.typen import GRUNDTYPEN


@pytest.fixture
def echt_db():
    """Heimrunde: Ben hat 30 Haende (viel callen), Clara nur 3."""
    db = oeffne_datenbank(":memory:")
    for nummer in range(30):
        hand_id = neue_hand(db, ["Ben", "Clara", "Dora"], 10, 10)
        aktion_speichern(db, hand_id, "Ben", "preflop", "call", 10)
        aktion_speichern(db, hand_id, "Clara", "preflop", "fold")
        aktion_speichern(db, hand_id, "Dora", "preflop", "check")
        for name in ["Ben", "Clara", "Dora"]:
            ergebnis_speichern(db, hand_id, name, 10, 20 if name == "Ben" else 0)
        if nummer < 3:
            hand_abschliessen(db, hand_id)
    # Nur Ben hat weitere abgeschlossene Haende -> Clara bleibt bei 3
    for nummer in range(27):
        hand_id = neue_hand(db, ["Ben", "Dora"], 10, 10)
        aktion_speichern(db, hand_id, "Ben", "preflop", "call", 10)
        aktion_speichern(db, hand_id, "Dora", "preflop", "check")
        hand_abschliessen(db, hand_id)
    yield db
    db.close()


@pytest.fixture
def lern_db():
    db = oeffne_datenbank(":memory:")
    yield db
    db.close()


def statistik(vpip, pfr, aggression, haende, aktionen=100):
    aggressiv = round(aggression * aktionen)
    return {"haende": haende, "vpip": vpip, "pfr": pfr, "af": None, "bb_pro_100": None,
            "aggressiv": aggressiv, "calls": aktionen - aggressiv, "tischgroessen": {6: haende}}


def spiele_hand(lern_db, echt_db, spiel, zufall, entscheidung=None):
    """Spielt eine Hand zu Ende; du checkst/callst (oder nach `entscheidung`)."""
    lerntisch.starte_hand(lern_db, spiel, zufall)
    for _ in range(500):
        phase = lerntisch.phase(spiel)
        if phase == "ende":
            return
        if phase == "held":
            erlaubt = lerntisch.anzeige(spiel)["hand"]["erlaubt"]
            aktion = entscheidung(erlaubt) if entscheidung else (
                "check" if "check" in erlaubt else "call")
            lerntisch.held_aktion(lern_db, echt_db, spiel, aktion, durchlaeufe=60)
        else:
            lerntisch.schritt(lern_db, spiel, zufall)
    raise AssertionError("Hand endet nicht")


# ---------- Nachahmer ----------


def test_ohne_haende_standard_typ():
    assert lerntisch.naechster_typ(statistik(None, None, 0, 0)) == "tag"


def test_wenige_haende_spielt_wie_grundtyp():
    typ, werte, nachgeahmt = lerntisch.nachahmer_werte(statistik(0.5, 0.04, 0.2, 10))
    assert typ == "station" and not nachgeahmt
    assert werte == GRUNDTYPEN["station"]


def test_viele_haende_werden_nachgeahmt():
    # Genau wie eine gemessene Station, nur lockerer -> Bot spielt mehr Haende
    typ, werte, nachgeahmt = lerntisch.nachahmer_werte(statistik(0.6, 0.04, 0.19, 300))
    assert typ == "station" and nachgeahmt
    assert werte["vpip"] > GRUNDTYPEN["station"]["vpip"]
    assert 1 <= werte["pfr"] <= werte["vpip"]
    assert 0 <= werte["aggression"] <= 1 and 0 <= werte["bluff"] <= 1


def test_aggressiver_als_der_typ_heisst_mehr_aggression():
    _, normal, _ = lerntisch.nachahmer_werte(statistik(0.16, 0.12, 0.78, 300))
    _, wild, _ = lerntisch.nachahmer_werte(statistik(0.16, 0.12, 0.95, 300))
    assert wild["aggression"] > normal["aggression"]
    assert wild["bluff"] > normal["bluff"]


def test_bots_aus_der_heimrunde(echt_db):
    ben = lerntisch.bot_fuer_spieler(echt_db, "Ben")
    clara = lerntisch.bot_fuer_spieler(echt_db, "Clara")
    assert ben["vorbild"] == "Ben" and "30 Haende" in ben["info"]
    assert "erst 3 Haende" in clara["info"]


# ---------- Spiel anlegen ----------


def test_neues_spiel(echt_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"spieler": "Ben"}, {"typ": "felsen"},
                                                      {"typ": "felsen"}])
    assert spiel["plaetze"] == ["Oliver", "Ben", "Felsen-Bot 1", "Felsen-Bot 2"]
    assert all(stack == lerntisch.STARTSTACK for stack in spiel["stacks"].values())
    assert lerntisch.phase(spiel) == "keine_hand"


@pytest.mark.parametrize("held, gegner", [
    ("", [{"typ": "tag"}]),
    ("Oliver", []),
    ("Oliver", [{"typ": "tag"}] * 9),
    ("Ben", [{"spieler": "Ben"}]),
    ("Oliver", [{"spieler": "Ben"}, {"spieler": "Ben"}]),
    ("Oliver", [{"spieler": "Niemand"}]),
    ("Oliver", [{"typ": "drache"}]),
])
def test_falsche_angaben(echt_db, held, gegner):
    with pytest.raises(ValueError):
        lerntisch.neues_spiel(echt_db, held, gegner)


# ---------- Spielen ----------


def test_haende_spielen(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"spieler": "Ben"}, {"spieler": "Clara"},
                                                      {"typ": "maniac"}])
    zufall = random.Random(5)
    echte_haende = echt_db.execute("SELECT COUNT(*) FROM haende").fetchone()[0]
    for _ in range(12):
        spiele_hand(lern_db, echt_db, spiel, zufall)
        # Kein Chip geht verloren oder kommt dazu
        assert sum(spiel["stacks"].values()) == sum(spiel["eingekauft"].values())
        ergebnis = spiel["hand"]["ergebnis"]
        assert ergebnis["gewinner"]
        assert sum(ergebnis["gewinn"].values()) == 0
    assert spiel["sitzung"]["haende"] == 12
    entscheidungen = spiel["sitzung"]["entscheidungen"]
    assert entscheidungen > 0
    # Jede Entscheidung steht im Protokoll des Lerntischs, die Heimrunde bleibt unberuehrt
    assert lern_db.execute("SELECT COUNT(*) FROM empfehlungen").fetchone()[0] == entscheidungen
    assert echt_db.execute("SELECT COUNT(*) FROM haende").fetchone()[0] == echte_haende


def test_button_wandert(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "tag"}, {"typ": "felsen"}])
    zufall = random.Random(1)
    spiele_hand(lern_db, echt_db, spiel, zufall)
    assert spiel["plaetze"][0] != "Oliver"
    assert spiel["hand"]["zustand"]["namen"][0] == "Oliver"


def test_karten_der_bots_bleiben_verdeckt(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "station"}, {"typ": "station"}])
    zufall = random.Random(2)
    lerntisch.starte_hand(lern_db, spiel, zufall)
    while lerntisch.phase(spiel) == "bots":
        lerntisch.schritt(lern_db, spiel, zufall)
    hand = lerntisch.anzeige(spiel)["hand"]
    assert list(hand["karten"]) == ["Oliver"]


def test_showdown_zeigt_karten(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "station"}])
    zufall = random.Random(3)
    for _ in range(20):
        spiele_hand(lern_db, echt_db, spiel, zufall)
        ergebnis = spiel["hand"]["ergebnis"]
        if ergebnis["gezeigt"]:
            karten = lerntisch.anzeige(spiel)["hand"]["karten"]
            assert set(ergebnis["gezeigt"]) <= set(karten)
            assert set(ergebnis["handarten"]) == set(ergebnis["gezeigt"])
            return
    raise AssertionError("Kein Showdown in 20 Haenden")


def test_tipp_nach_der_entscheidung(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "felsen"}, {"typ": "tag"}])
    zufall = random.Random(4)
    lerntisch.starte_hand(lern_db, spiel, zufall)
    while lerntisch.phase(spiel) == "bots":
        lerntisch.schritt(lern_db, spiel, zufall)
    assert lerntisch.anzeige(spiel)["hand"]["letzter_tipp"] is None   # vorher nichts verraten
    tipp = lerntisch.held_aktion(lern_db, echt_db, spiel, "fold", durchlaeufe=60)
    assert tipp["du"] == "fold"
    assert tipp["gleich"] == (tipp["ki"] == "fold")
    assert lerntisch.anzeige(spiel)["hand"]["letzter_tipp"] == tipp


def test_nicht_dran(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "felsen"}])
    with pytest.raises(ValueError):
        lerntisch.held_aktion(lern_db, echt_db, spiel, "fold")


def test_pleite_bekommt_neues_spielgeld(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "felsen"}])
    spiel["stacks"]["Oliver"] = 0
    lerntisch.starte_hand(lern_db, spiel, random.Random(1))
    assert spiel["eingekauft"]["Oliver"] == 2 * lerntisch.STARTSTACK
    assert spiel["hand"]["zustand"]["stacks"]["Oliver"] + \
        spiel["hand"]["zustand"]["einsaetze"]["Oliver"] == lerntisch.STARTSTACK


def test_zusammenfassung(echt_db, lern_db):
    spiel = lerntisch.neues_spiel(echt_db, "Oliver", [{"typ": "maniac"}, {"typ": "station"}])
    zufall = random.Random(6)
    for _ in range(5):
        spiele_hand(lern_db, echt_db, spiel, zufall, entscheidung=lambda erlaubt: "fold"
                    if "fold" in erlaubt else "check")
    z = lerntisch.zusammenfassung(spiel)
    assert z["haende"] == 5
    assert z["entscheidungen"] == sum(p["entscheidungen"] for p in z["pro_strasse"].values())
    assert 0 <= z["quote"] <= 1
    assert z["ergebnis_cent"] == spiel["stacks"]["Oliver"] - spiel["eingekauft"]["Oliver"]
    assert z["ergebnis_bb"] == z["ergebnis_cent"] / 10
    for abweichung in z["abweichungen"]:
        assert abweichung["ki"] != abweichung["du"]
