"""Tests fuer poker/live.py."""

import pytest

from poker.deck import lies_karten
from poker.live import (
    abrechnen,
    beende_hand,
    finde_spieler,
    lies_aktion,
    naechste_strasse,
    pot,
    rotiere,
    showdown_gewinner,
    starte_hand,
    verarbeite_aktion,
    zu_callen,
)
from poker.profile import berechne_statistik, lade_aktionen, oeffne_datenbank

NAMEN = ["Anna", "Ben", "Clara"]  # Anna = Small Blind, Ben = Big Blind

FLOP = lies_karten("Ks 9h 4d")
TURN = lies_karten("2c")
RIVER = lies_karten("7s")


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


def test_lies_aktion_ohne_namen():
    assert lies_aktion("r 6", NAMEN, am_zug="Clara") == ("Clara", "raise", 6.0)
    assert lies_aktion("c", NAMEN, am_zug="Ben") == ("Ben", "call", None)
    # "b" ist bet, "ben" ist ein Name: beides funktioniert
    assert lies_aktion("b 4", NAMEN, am_zug="Anna") == ("Anna", "raise", 4.0)
    assert lies_aktion("b f", NAMEN, am_zug="Anna") == ("Ben", "fold", None)
    with pytest.raises(ValueError):
        lies_aktion("c", NAMEN)  # ohne am_zug geht es nicht


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

    assert naechste_strasse(db, z, FLOP) == "flop"
    assert pot(z) == 13
    assert verarbeite_aktion(db, z, "Ben", "call") == ("check", 0)  # nichts offen
    assert verarbeite_aktion(db, z, "Clara", "raise", 8) == ("bet", 8)  # erster Einsatz
    verarbeite_aktion(db, z, "Ben", "raise", 20)
    verarbeite_aktion(db, z, "Clara", "call")
    assert pot(z) == 53

    naechste_strasse(db, z, TURN)
    verarbeite_aktion(db, z, "Ben", "check")
    verarbeite_aktion(db, z, "Clara", "check")
    naechste_strasse(db, z, RIVER)
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
        ("Ben", "turn", "check", 0),
        ("Clara", "turn", "check", 0),
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
    assert naechste_strasse(db, z, FLOP) == "flop"


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
        naechste_strasse(db, z, FLOP)


def test_ende_erst_nach_river(db):
    z = starte_hand(db, NAMEN, 1, 2)
    with pytest.raises(ValueError):
        beende_hand(z)


# ---------- Reihenfolge ----------


def test_preflop_reihenfolge(db):
    z = starte_hand(db, NAMEN, 1, 2)
    assert z["am_zug"] == "Clara"  # links vom Big Blind
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Anna", "call")  # Anna ist noch nicht dran
    verarbeite_aktion(db, z, "Clara", "call")
    assert z["am_zug"] == "Anna"
    verarbeite_aktion(db, z, "Anna", "call")
    assert z["am_zug"] == "Ben"


def test_big_blind_option(db):
    # Alle callen, aber der Big Blind darf noch erhoehen.
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    with pytest.raises(ValueError):
        naechste_strasse(db, z, FLOP)  # Ben hat noch nicht gehandelt
    verarbeite_aktion(db, z, "Ben", "raise", 6)
    # Nach der Erhoehung muessen Clara und Anna nochmal entscheiden.
    assert z["am_zug"] == "Clara"
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "fold")
    assert z["am_zug"] is None
    naechste_strasse(db, z, FLOP)


def test_nach_dem_flop_beginnt_der_small_blind(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Anna"


def test_gefoldete_werden_uebersprungen(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Ben"


def test_heads_up_reihenfolge(db):
    z = starte_hand(db, ["Anna", "Ben"], 1, 2)
    assert z["am_zug"] == "Anna"  # preflop: Small Blind (= Button) zuerst
    verarbeite_aktion(db, z, "Anna", "call")
    assert z["am_zug"] == "Ben"   # Big Blind hat noch die Option
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Ben"   # ab dem Flop: Big Blind zuerst


def test_runde_vorbei_keine_aktion_mehr(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "check")
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "raise", 10)


# ---------- Board, Showdown, Abrechnung ----------


def spiele_bis_showdown(db):
    """Hilfsfunktion: Anna foldet, Ben und Clara checken bis zum River.

    Pot: Anna 1 (Small Blind) + Ben 2 + Clara 2 = 5
    """
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "check")
    for karten in [FLOP, TURN, RIVER]:
        naechste_strasse(db, z, karten)
        verarbeite_aktion(db, z, "Ben", "check")
        verarbeite_aktion(db, z, "Clara", "check")
    beende_hand(z)
    return z


def test_board_karten_pruefen(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "check")
    with pytest.raises(ValueError):
        naechste_strasse(db, z, lies_karten("Ks 9h"))  # nur 2 Karten
    naechste_strasse(db, z, FLOP)
    with pytest.raises(ValueError):
        naechste_strasse(db, z, lies_karten("Ks"))  # liegt schon
    assert z["board"] == FLOP


def test_showdown_bessere_hand_gewinnt(db):
    z = spiele_bis_showdown(db)
    gezeigte = {"Ben": lies_karten("Kh Qc"), "Clara": lies_karten("9s 9c")}
    # Board Ks 9h 4d 2c 7s: Clara hat Drilling Neunen, Ben ein Koenigspaar
    assert showdown_gewinner(z, gezeigte) == ["Clara"]
    ergebnis = abrechnen(db, z, ["Clara"], gezeigte)
    assert ergebnis == {"Anna": -1, "Ben": -2, "Clara": 3}


def test_showdown_split_pot(db):
    z = spiele_bis_showdown(db)
    gezeigte = {"Ben": lies_karten("Ah 3c"), "Clara": lies_karten("Ac 3d")}
    assert showdown_gewinner(z, gezeigte) == ["Ben", "Clara"]
    ergebnis = abrechnen(db, z, ["Ben", "Clara"], gezeigte)
    assert ergebnis == {"Anna": -1, "Ben": 0.5, "Clara": 0.5}


def test_wer_nicht_zeigt_verliert(db):
    z = spiele_bis_showdown(db)
    # Nur Ben zeigt, Clara wirft ihre Karten weg.
    assert showdown_gewinner(z, {"Ben": lies_karten("2h 3h")}) == ["Ben"]


def test_showdown_fehler(db):
    z = spiele_bis_showdown(db)
    with pytest.raises(ValueError):
        showdown_gewinner(z, {})  # keiner zeigt
    with pytest.raises(ValueError):
        showdown_gewinner(z, {"Ben": lies_karten("Ks Qc")})  # Ks liegt auf dem Board
    with pytest.raises(ValueError):
        showdown_gewinner(z, {"Anna": lies_karten("Ah Ac")})  # Anna hat gefoldet


def test_alle_folden_gewinner_bekommt_pot(db):
    z = starte_hand(db, NAMEN, 1, 2)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "fold")
    ergebnis = abrechnen(db, z, ["Clara"])
    assert ergebnis == {"Anna": -1, "Ben": -2, "Clara": 3}
    with pytest.raises(ValueError):
        abrechnen(db, z, ["Clara"])  # nicht zweimal


def test_abrechnen_erst_am_ende(db):
    z = starte_hand(db, NAMEN, 1, 2)
    with pytest.raises(ValueError):
        abrechnen(db, z, ["Clara"])


def test_bb_pro_100(db):
    # Clara gewinnt 3 (= 1,5 BB), dann 3 (= 1,5 BB): 2 Haende, +3 BB
    # -> 1,5 BB pro Hand -> 150 bb/100
    for i in range(2):
        z = starte_hand(db, NAMEN, 1, 2)
        verarbeite_aktion(db, z, "Clara", "raise", 6)
        verarbeite_aktion(db, z, "Anna", "fold")
        verarbeite_aktion(db, z, "Ben", "fold")
        abrechnen(db, z, ["Clara"])
    assert berechne_statistik(db, "Clara")["bb_pro_100"] == pytest.approx(150)
    assert berechne_statistik(db, "Ben")["bb_pro_100"] == pytest.approx(-100)


def test_rotiere():
    assert rotiere(["Anna", "Ben", "Clara"]) == ["Ben", "Clara", "Anna"]
