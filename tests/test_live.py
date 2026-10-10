"""Tests fuer poker/live.py."""

import pytest

from poker.deck import lies_karten
from poker.live import (
    abrechnen,
    beende_hand,
    berechne_pots,
    darf_erhoehen,
    gewinner_ohne_showdown,
    ist_allin,
    finde_spieler,
    lies_aktion,
    mindest_erhoehung,
    naechste_strasse,
    pot,
    rebuy,
    rotiere,
    showdown_gewinner,
    starte_hand,
    verarbeite_aktion,
    zu_callen,
)
from poker.profile import (
    anzahl_abgebrochene,
    berechne_statistik,
    lade_aktionen,
    oeffne_datenbank,
)

NAMEN = ["Anna", "Ben", "Clara"]  # Anna = Small Blind, Ben = Big Blind
STACKS = {"Anna": 200, "Ben": 200, "Clara": 200}

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
    zustand = starte_hand(db, NAMEN, 1, 2, STACKS)
    assert pot(zustand) == 3
    assert zu_callen(zustand, "Anna") == 1
    assert zu_callen(zustand, "Ben") == 0
    assert zu_callen(zustand, "Clara") == 2


def test_ganze_hand(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    abrechnen(db, z, [["Clara"]])

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
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "fold")
    verarbeite_aktion(db, z, "Anna", "fold")
    assert z["beendet"]
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Ben", "check")


def test_big_blind_darf_checken(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    assert verarbeite_aktion(db, z, "Ben", "call") == ("check", 0)
    assert naechste_strasse(db, z, FLOP) == "flop"


def test_ungueltige_aktionen(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    with pytest.raises(ValueError):
        naechste_strasse(db, z, FLOP)


def test_ende_erst_nach_river(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    with pytest.raises(ValueError):
        beende_hand(z)


# ---------- Reihenfolge ----------


def test_preflop_reihenfolge(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    assert z["am_zug"] == "Clara"  # links vom Big Blind
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Anna", "call")  # Anna ist noch nicht dran
    verarbeite_aktion(db, z, "Clara", "call")
    assert z["am_zug"] == "Anna"
    verarbeite_aktion(db, z, "Anna", "call")
    assert z["am_zug"] == "Ben"


def test_big_blind_option(db):
    # Alle callen, aber der Big Blind darf noch erhoehen.
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Anna"


def test_gefoldete_werden_uebersprungen(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Ben"


def test_heads_up_reihenfolge(db):
    z = starte_hand(db, ["Anna", "Ben"], 1, 2, STACKS)
    assert z["am_zug"] == "Anna"  # preflop: Small Blind (= Button) zuerst
    verarbeite_aktion(db, z, "Anna", "call")
    assert z["am_zug"] == "Ben"   # Big Blind hat noch die Option
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] == "Ben"   # ab dem Flop: Big Blind zuerst


def test_runde_vorbei_keine_aktion_mehr(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
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
    assert showdown_gewinner(z, gezeigte) == [["Clara"]]
    ergebnis = abrechnen(db, z, [["Clara"]], gezeigte)
    assert ergebnis == {"Anna": -1, "Ben": -2, "Clara": 3}


def test_showdown_split_pot(db):
    z = spiele_bis_showdown(db)
    gezeigte = {"Ben": lies_karten("Ah 3c"), "Clara": lies_karten("Ac 3d")}
    assert showdown_gewinner(z, gezeigte) == [["Ben", "Clara"]]
    ergebnis = abrechnen(db, z, [["Ben", "Clara"]], gezeigte)
    assert ergebnis == {"Anna": -1, "Ben": 0.5, "Clara": 0.5}


def test_wer_nicht_zeigt_verliert(db):
    z = spiele_bis_showdown(db)
    # Nur Ben zeigt, Clara wirft ihre Karten weg.
    assert showdown_gewinner(z, {"Ben": lies_karten("2h 3h")}) == [["Ben"]]


def test_showdown_fehler(db):
    z = spiele_bis_showdown(db)
    assert showdown_gewinner(z, {}) == [None]  # keiner zeigt -> von Hand angeben
    with pytest.raises(ValueError):
        showdown_gewinner(z, {"Ben": lies_karten("Ks Qc")})  # Ks liegt auf dem Board
    with pytest.raises(ValueError):
        showdown_gewinner(z, {"Anna": lies_karten("Ah Ac")})  # Anna hat gefoldet


def test_alle_folden_gewinner_bekommt_pot(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "fold")
    ergebnis = abrechnen(db, z, [["Clara"]])
    assert ergebnis == {"Anna": -1, "Ben": -2, "Clara": 3}
    with pytest.raises(ValueError):
        abrechnen(db, z, [["Clara"]])  # nicht zweimal


def test_abrechnen_erst_am_ende(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    with pytest.raises(ValueError):
        abrechnen(db, z, [["Clara"]])


def test_bb_pro_100(db):
    # Clara gewinnt 3 (= 1,5 BB), dann 3 (= 1,5 BB): 2 Haende, +3 BB
    # -> 1,5 BB pro Hand -> 150 bb/100
    for i in range(2):
        z = starte_hand(db, NAMEN, 1, 2, STACKS)
        verarbeite_aktion(db, z, "Clara", "raise", 6)
        verarbeite_aktion(db, z, "Anna", "fold")
        verarbeite_aktion(db, z, "Ben", "fold")
        abrechnen(db, z, [["Clara"]])
    assert berechne_statistik(db, "Clara")["bb_pro_100"] == pytest.approx(150)
    assert berechne_statistik(db, "Ben")["bb_pro_100"] == pytest.approx(-100)


# ---------- Stacks, All-in, Side Pots ----------

BOARD = lies_karten("Ks 9h 4d 2c 7s")


def board_hinlegen(db, z):
    """Hilfsfunktion: Flop, Turn und River hinlegen (keiner muss mehr handeln)."""
    naechste_strasse(db, z, BOARD[:3])
    naechste_strasse(db, z, BOARD[3:4])
    naechste_strasse(db, z, BOARD[4:])
    beende_hand(z)


def test_stacks_werden_abgezogen(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    assert z["stacks"] == {"Anna": 199, "Ben": 198, "Clara": 200}
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    assert z["stacks"]["Clara"] == 194


def test_raise_hoeher_als_stack_geht_nicht(db):
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 200, "Clara": 50})
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "raise", 60)
    verarbeite_aktion(db, z, "Clara", "raise", 50)  # genau alles geht
    assert ist_allin(z, "Clara")


def test_allin_kuerzel(db):
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 200, "Clara": 50})
    assert verarbeite_aktion(db, z, "Clara", "allin") == ("raise", 50)
    assert lies_aktion("a", NAMEN, am_zug="Anna") == ("Anna", "allin", None)


def test_call_mit_zu_wenig_chips(db):
    # Clara hat nur 30 und callt einen Raise auf 100 -> all-in fuer 30
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 200, "Clara": 30})
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "raise", 100)
    verarbeite_aktion(db, z, "Ben", "fold")
    assert z["am_zug"] == "Clara"
    assert verarbeite_aktion(db, z, "Clara", "call") == ("call", 30)
    assert ist_allin(z, "Clara")
    assert z["am_zug"] is None


def test_allin_spieler_wird_uebersprungen(db):
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 200, "Clara": 30})
    verarbeite_aktion(db, z, "Clara", "allin")  # raise auf 30
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "call")
    naechste_strasse(db, z, FLOP)
    verarbeite_aktion(db, z, "Anna", "check")
    assert z["am_zug"] == "Ben"   # Clara ist all-in und wird uebersprungen
    verarbeite_aktion(db, z, "Ben", "check")
    assert z["am_zug"] is None


def test_alle_allin_keine_setzrunden_mehr(db):
    z = starte_hand(db, ["Anna", "Ben"], 1, 2, {"Anna": 50, "Ben": 80})
    verarbeite_aktion(db, z, "Anna", "allin")
    verarbeite_aktion(db, z, "Ben", "call")
    # Ben hat noch Chips, aber keiner kann mehr gegen ihn setzen.
    naechste_strasse(db, z, FLOP)
    assert z["am_zug"] is None
    naechste_strasse(db, z, TURN)
    naechste_strasse(db, z, RIVER)
    beende_hand(z)
    assert z["beendet"]


def test_blind_groesser_als_stack(db):
    # Ben hat nur 1 Chip und ist mit dem Big Blind schon all-in.
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 1, "Clara": 200})
    assert ist_allin(z, "Ben")
    assert z["investiert"]["Ben"] == 1
    assert z["hoechster"] == 1


def test_side_pots_berechnen(db):
    # Anna all-in 30, Ben und Clara je 100
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 30, "Ben": 200, "Clara": 200})
    verarbeite_aktion(db, z, "Clara", "raise", 100)
    verarbeite_aktion(db, z, "Anna", "allin")   # call fuer 30
    verarbeite_aktion(db, z, "Ben", "call")
    assert berechne_pots(z) == [
        {"betrag": 90, "berechtigte": ["Anna", "Ben", "Clara"]},
        {"betrag": 140, "berechtigte": ["Ben", "Clara"]},
    ]


def test_side_pot_mit_gefoldetem_spieler(db):
    # Ben callt 10 und foldet spaeter: sein Geld bleibt im Pot.
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 20, "Ben": 200, "Clara": 200})
    verarbeite_aktion(db, z, "Clara", "raise", 10)
    verarbeite_aktion(db, z, "Anna", "allin")   # raise auf 20
    verarbeite_aktion(db, z, "Ben", "call")
    verarbeite_aktion(db, z, "Clara", "call")
    naechste_strasse(db, z, FLOP)
    verarbeite_aktion(db, z, "Ben", "raise", 50)
    verarbeite_aktion(db, z, "Clara", "raise", 150)
    verarbeite_aktion(db, z, "Ben", "fold")
    pots = berechne_pots(z)
    assert pots[0] == {"betrag": 60, "berechtigte": ["Anna", "Clara"]}
    # Side Pot: Bens 50 und Claras 150, beide ueber den 20 aus dem Hauptpot
    assert pots[1] == {"betrag": 200, "berechtigte": ["Clara"]}
    assert pot(z) == 260


def test_abrechnung_mit_side_pot(db):
    # Anna (all-in 30) hat die beste Hand, Ben die zweitbeste.
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 30, "Ben": 200, "Clara": 200})
    verarbeite_aktion(db, z, "Clara", "raise", 100)
    verarbeite_aktion(db, z, "Anna", "allin")
    verarbeite_aktion(db, z, "Ben", "call")
    naechste_strasse(db, z, BOARD[:3])
    verarbeite_aktion(db, z, "Ben", "check")
    verarbeite_aktion(db, z, "Clara", "check")
    naechste_strasse(db, z, BOARD[3:4])
    verarbeite_aktion(db, z, "Ben", "check")
    verarbeite_aktion(db, z, "Clara", "check")
    naechste_strasse(db, z, BOARD[4:])
    verarbeite_aktion(db, z, "Ben", "check")
    verarbeite_aktion(db, z, "Clara", "check")
    beende_hand(z)

    gezeigte = {
        "Anna": lies_karten("Kh Kc"),   # Drilling Koenige
        "Ben": lies_karten("9s 9c"),    # Drilling Neunen
        "Clara": lies_karten("Ad Qd"),  # nur Ass hoch
    }
    gewinner = showdown_gewinner(z, gezeigte)
    assert gewinner == [["Anna"], ["Ben"]]
    ergebnis = abrechnen(db, z, gewinner, gezeigte)
    assert ergebnis == {"Anna": 60, "Ben": 40, "Clara": -100}
    assert z["stacks"] == {"Anna": 90, "Ben": 240, "Clara": 100}


def test_zu_hoher_bet_kommt_zurueck(db):
    # Clara setzt 100, Anna kann nur 30 callen: 70 bekommt Clara zurueck.
    z = starte_hand(db, ["Anna", "Clara"], 1, 2, {"Anna": 30, "Clara": 200})
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Clara", "raise", 100)
    verarbeite_aktion(db, z, "Anna", "call")    # all-in fuer 30
    board_hinlegen(db, z)
    gezeigte = {"Anna": lies_karten("Kh Kc"), "Clara": lies_karten("Ad Qd")}
    gewinner = showdown_gewinner(z, gezeigte)
    assert gewinner == [["Anna"], ["Clara"]]
    ergebnis = abrechnen(db, z, gewinner, gezeigte)
    assert ergebnis == {"Anna": 30, "Clara": -30}


def test_gewinner_ohne_showdown(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "fold")
    abrechnen(db, z, gewinner_ohne_showdown(z))
    assert z["stacks"] == {"Anna": 199, "Ben": 198, "Clara": 203}


def test_ohne_chips_kein_mitspielen(db):
    with pytest.raises(ValueError):
        starte_hand(db, NAMEN, 1, 2, {"Anna": 200, "Ben": 0, "Clara": 200})


def test_rebuy():
    stacks = {"Anna": 0, "Ben": 150}
    neue = rebuy(stacks, "Anna", 100)
    assert neue == {"Anna": 100, "Ben": 150}
    assert stacks["Anna"] == 0  # das Original bleibt unveraendert
    assert rebuy(neue, "Clara", 200)["Clara"] == 200
    with pytest.raises(ValueError):
        rebuy(stacks, "Anna", 0)


# ---------- Mindest-Erhoehung ----------


def test_mindest_raise_preflop(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    assert mindest_erhoehung(z) == 4          # Big Blind 2 + Erhoehung 2
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "raise", 3)
    verarbeite_aktion(db, z, "Clara", "raise", 6)   # um 4 erhoeht
    assert mindest_erhoehung(z) == 10
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Anna", "raise", 9)
    verarbeite_aktion(db, z, "Anna", "raise", 10)


def test_mindest_bet_nach_dem_flop(db):
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "call")
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "check")
    naechste_strasse(db, z, FLOP)
    assert mindest_erhoehung(z) == 2          # ein Big Blind
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Anna", "raise", 1)
    verarbeite_aktion(db, z, "Anna", "raise", 5)   # Bet 5
    assert mindest_erhoehung(z) == 10              # Raise mindestens um 5
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Ben", "raise", 8)
    verarbeite_aktion(db, z, "Ben", "raise", 10)


def test_kleines_allin_ist_erlaubt(db):
    # Clara erhoeht auf 20, Mindest-Raise waere auf 38. Anna hat nur 25:
    # all-in auf 25 ist trotzdem erlaubt, auch mit Betrag statt "a".
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 25, "Ben": 200, "Clara": 200})
    verarbeite_aktion(db, z, "Clara", "raise", 20)
    assert mindest_erhoehung(z) == 38
    assert verarbeite_aktion(db, z, "Anna", "raise", 25) == ("raise", 25)


def test_zu_kleines_allin_oeffnet_nicht_wieder(db):
    # Clara erhoeht auf 20, Anna geht all-in auf 25 (nur um 5, keine volle Erhoehung).
    # Ben darf noch erhoehen (er hat noch nicht gehandelt), Clara nur callen/folden.
    z = starte_hand(db, NAMEN, 1, 2, {"Anna": 25, "Ben": 200, "Clara": 200})
    verarbeite_aktion(db, z, "Clara", "raise", 20)
    verarbeite_aktion(db, z, "Anna", "allin")
    assert darf_erhoehen(z, "Ben")
    verarbeite_aktion(db, z, "Ben", "call")
    assert z["am_zug"] == "Clara"
    assert not darf_erhoehen(z, "Clara")
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "raise", 60)
    with pytest.raises(ValueError):
        verarbeite_aktion(db, z, "Clara", "allin")
    verarbeite_aktion(db, z, "Clara", "call")
    assert z["am_zug"] is None


def test_volle_erhoehung_oeffnet_wieder(db):
    # Nach einer vollen Erhoehung darf jeder wieder erhoehen.
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "call")
    verarbeite_aktion(db, z, "Ben", "raise", 20)
    assert darf_erhoehen(z, "Clara")
    verarbeite_aktion(db, z, "Clara", "raise", 34)


# ---------- Abgebrochene Haende ----------


def test_abgebrochene_hand_zaehlt_nicht(db):
    # Hand 1 wird fertig gespielt, Hand 2 mittendrin abgebrochen (quit).
    z = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, z, "Clara", "raise", 6)
    verarbeite_aktion(db, z, "Anna", "fold")
    verarbeite_aktion(db, z, "Ben", "fold")
    abrechnen(db, z, gewinner_ohne_showdown(z))

    abgebrochen = starte_hand(db, NAMEN, 1, 2, STACKS)
    verarbeite_aktion(db, abgebrochen, "Clara", "call")
    verarbeite_aktion(db, abgebrochen, "Anna", "call")
    # ... hier wurde quit eingegeben

    clara = berechne_statistik(db, "Clara")
    assert clara["haende"] == 1
    assert clara["vpip"] == 1.0 and clara["pfr"] == 1.0
    anna = berechne_statistik(db, "Anna")
    assert anna["haende"] == 1
    assert anna["vpip"] == 0   # der Call aus der abgebrochenen Hand zaehlt nicht
    assert anzahl_abgebrochene(db) == 1


def test_rotiere():
    assert rotiere(["Anna", "Ben", "Clara"]) == ["Ben", "Clara", "Anna"]
