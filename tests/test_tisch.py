"""Tests fuer poker/tisch.py: ein Live-Abend fuer die Web-App (Betraege in Cent)."""

import pytest

from poker import tisch
from poker.deck import lies_karten
from poker.profile import berechne_statistik, lade_aktionen, oeffne_datenbank

SPIELER = ["Anna", "Ben", "Clara"]
STACKS = {"Anna": 1000, "Ben": 1000, "Clara": 1000}   # je 10 Euro


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


@pytest.fixture
def abend(db):
    return tisch.neuer_abend(db, SPIELER, STACKS, 10, 20)   # Blinds 0,10 / 0,20 Euro


# ---------- Abend ----------


def test_abend_pruefungen(db):
    for spieler, stacks, sb, bb in [
        (["Anna"], {"Anna": 1000}, 10, 20),
        (["Anna", "Anna"], {"Anna": 1000}, 10, 20),
        (["Anna", "Ben"], {"Anna": 1000}, 10, 20),          # Ben ohne Stack
        (["Anna", "Ben"], {"Anna": 1000, "Ben": 1000}, 30, 20),
    ]:
        with pytest.raises(ValueError):
            tisch.neuer_abend(db, spieler, stacks, sb, bb)


def test_abend_uebersteht_neustart(db, abend):
    tisch.starte_naechste_hand(db, abend)
    geladen = tisch.lade_abend(db)
    assert geladen["spieler"] == SPIELER
    assert geladen["hand"] is None         # laufende Hand wird verworfen
    tisch.beende_abend(db)
    assert tisch.lade_abend(db) is None


# ---------- Hand spielen ----------


def test_ganze_hand_mit_fold(db, abend):
    tisch.starte_naechste_hand(db, abend)
    a = tisch.anzeige(abend)
    assert a["hand"]["am_zug"] == "Clara"
    assert a["hand"]["erlaubt"] == ["fold", "call", "raise"]
    tisch.aktion(db, abend, "raise", 60)
    tisch.aktion(db, abend, "fold")
    tisch.aktion(db, abend, "fold")
    assert tisch.phase(abend) == "gewonnen"
    ergebnis = tisch.abrechnen_ohne_showdown(db, abend)
    assert ergebnis == {"Anna": -10, "Ben": -20, "Clara": 30}
    assert abend["stacks"] == {"Anna": 990, "Ben": 980, "Clara": 1030}
    # Button wandert: naechste Hand ist Ben Small Blind
    assert abend["spieler"] == ["Ben", "Clara", "Anna"]
    assert tisch.lade_abend(db)["stacks"]["Clara"] == 1030   # gespeichert


def test_hand_bis_zum_showdown(db, abend):
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "call")    # Clara
    tisch.aktion(db, abend, "fold")    # Anna
    tisch.aktion(db, abend, "check")   # Ben
    assert tisch.phase(abend) == "karten"
    assert tisch.anzeige(abend)["hand"]["neue_karten"] == 3
    for karten in ["Ks 9h 4d", "2c", "7s"]:
        tisch.board_karten(db, abend, lies_karten(karten))
        tisch.aktion(db, abend, "check")
        tisch.aktion(db, abend, "check")
    assert tisch.phase(abend) == "showdown"
    gezeigt = {"Ben": lies_karten("Kh Qc"), "Clara": lies_karten("9s 9c")}
    vorschau = tisch.showdown_vorschau(abend, gezeigt)
    assert vorschau["pots"][0]["gewinner"] == ["Clara"]
    assert vorschau["handarten"] == {"Ben": "Paar", "Clara": "Drilling"}
    ergebnis = tisch.showdown_abrechnen(db, abend, gezeigt)
    assert ergebnis["Clara"] == 30


def test_showdown_ohne_gezeigte_karten(db, abend):
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "call")
    tisch.aktion(db, abend, "call")
    tisch.aktion(db, abend, "check")
    for karten in ["Ks 9h 4d", "2c", "7s"]:
        tisch.board_karten(db, abend, lies_karten(karten))
        for i in range(3):
            tisch.aktion(db, abend, "check")
    assert tisch.showdown_vorschau(abend, {})["pots"][0]["gewinner"] is None
    with pytest.raises(ValueError):
        tisch.showdown_abrechnen(db, abend, {})
    ergebnis = tisch.showdown_abrechnen(db, abend, {}, {"0": ["Anna"]})
    assert ergebnis["Anna"] == 40


def test_allin_mit_side_pot(db):
    abend = tisch.neuer_abend(db, SPIELER, {"Anna": 300, "Ben": 1000, "Clara": 1000}, 10, 20)
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "raise", 100)   # Clara
    tisch.aktion(db, abend, "allin")        # Anna 300
    tisch.aktion(db, abend, "call")         # Ben
    tisch.aktion(db, abend, "call")         # Clara
    assert tisch.phase(abend) == "karten"   # Setzrunde vorbei, Flop kommt
    pots = tisch.anzeige(abend)["hand"]["pots"]
    assert pots[0]["betrag"] == 900


# ---------- Rueckgaengig ----------


def test_rueckgaengig_aktion(db, abend):
    tisch.starte_naechste_hand(db, abend)
    hand_id = abend["hand"]["zustand"]["hand_id"]
    tisch.aktion(db, abend, "raise", 60)
    tisch.aktion(db, abend, "fold")       # vertippt!
    tisch.rueckgaengig(db, abend)
    a = tisch.anzeige(abend)["hand"]
    assert a["am_zug"] == "Anna"
    assert "Anna" in a["aktiv"]
    assert lade_aktionen(db, hand_id) == [("Clara", "preflop", "raise", 60)]
    tisch.aktion(db, abend, "call")
    assert lade_aktionen(db, hand_id)[-1] == ("Anna", "preflop", "call", 60)


def test_rueckgaengig_mehrere_schritte_und_karten(db, abend):
    tisch.starte_naechste_hand(db, abend)
    hand_id = abend["hand"]["zustand"]["hand_id"]
    tisch.aktion(db, abend, "call")
    tisch.aktion(db, abend, "call")
    tisch.aktion(db, abend, "check")
    tisch.board_karten(db, abend, lies_karten("Ks 9h 4d"))
    tisch.rueckgaengig(db, abend)            # Flop zurueck
    assert abend["hand"]["zustand"]["board"] == []
    gespeichert = db.execute("SELECT board FROM haende WHERE id = ?", (hand_id,)).fetchone()[0]
    assert gespeichert == "[]"
    tisch.rueckgaengig(db, abend)            # Check von Ben zurueck
    tisch.rueckgaengig(db, abend)            # Call von Anna zurueck
    assert tisch.anzeige(abend)["hand"]["am_zug"] == "Anna"
    assert len(lade_aktionen(db, hand_id)) == 1
    tisch.rueckgaengig(db, abend)
    with pytest.raises(ValueError):
        tisch.rueckgaengig(db, abend)        # nichts mehr da


def test_fehler_wird_nicht_gemerkt(db, abend):
    tisch.starte_naechste_hand(db, abend)
    with pytest.raises(ValueError):
        tisch.aktion(db, abend, "check")     # Clara muss callen
    assert tisch.anzeige(abend)["hand"]["kann_rueckgaengig"] is False


def test_rueckgaengig_nach_letztem_fold(db, abend):
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "fold")
    tisch.aktion(db, abend, "fold")
    assert tisch.phase(abend) == "gewonnen"
    tisch.rueckgaengig(db, abend)
    assert tisch.phase(abend) == "aktion"


# ---------- Abgebrochene Haende ----------


def test_abgebrochene_hand_zaehlt_nicht(db, abend):
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "raise", 60)
    tisch.hand_abbrechen(abend)
    assert abend["stacks"] == STACKS            # nichts verloren
    assert abend["spieler"] == SPIELER          # Button bleibt
    assert berechne_statistik(db, "Clara")["haende"] == 0


# ---------- Zwischen den Haenden ----------


def test_aussetzen_nachkauf_dazukommen(db, abend):
    tisch.setze_aus(db, abend, "Ben")
    assert tisch.mitspieler(abend) == ["Anna", "Clara"]
    tisch.setze_aus(db, abend, "Ben", False)
    tisch.nachkauf(db, abend, "Anna", 500)
    assert abend["stacks"]["Anna"] == 1500
    tisch.spieler_dazu(db, abend, "Dave", 1000)
    assert abend["spieler"][-1] == "Dave"
    tisch.starte_naechste_hand(db, abend)
    with pytest.raises(ValueError):
        tisch.nachkauf(db, abend, "Anna", 500)   # nicht waehrend der Hand


def test_pleite_spieler_bekommt_keine_karten(db):
    abend = tisch.neuer_abend(db, SPIELER, {"Anna": 100, "Ben": 1000, "Clara": 1000}, 10, 20)
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "raise", 100)    # Clara
    tisch.aktion(db, abend, "allin")         # Anna
    tisch.aktion(db, abend, "fold")          # Ben
    for karten in ["Ks 9h 4d", "2c", "7s"]:
        tisch.board_karten(db, abend, lies_karten(karten))
    tisch.showdown_abrechnen(db, abend, {"Anna": lies_karten("2h 3h"),
                                         "Clara": lies_karten("Ah Ad")})
    assert abend["stacks"]["Anna"] == 0
    assert "Anna" not in tisch.mitspieler(abend)


# ---------- Anzeige ----------


def test_raise_vorschlaege(db, abend):
    tisch.starte_naechste_hand(db, abend)
    r = tisch.anzeige(abend)["hand"]["raise"]
    # Pot 30, Clara muss 20 callen -> Pot nach Call 50
    assert r == {"mindest": 40, "halber_pot": 50, "pot": 70, "allin": 1000}


def test_spieler_statistik(db, abend):
    tisch.starte_naechste_hand(db, abend)
    tisch.aktion(db, abend, "raise", 60)
    tisch.aktion(db, abend, "fold")
    tisch.aktion(db, abend, "fold")
    tisch.abrechnen_ohne_showdown(db, abend)
    s = tisch.spieler_statistik(db, "Clara")
    assert s["haende"] == 1 and s["pfr"] == 1.0
    assert s["typ"] == "unbekannt"     # zu wenige Haende
