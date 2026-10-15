"""Tests fuer den Analyse-Modus (poker/analyse.py)."""

import pytest

from poker import analyse
from poker.profile import (aktion_speichern, board_speichern, empfehlung_speichern,
                           ergebnis_speichern, hand_abschliessen, handkarten_speichern,
                           neue_hand, oeffne_datenbank)

BOARD = [(2, "Herz"), (7, "Pik"), (9, "Karo"), (12, "Kreuz"), (4, "Herz")]


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def spiele_hand(db, ergebnis_anna, datum="2026-10-01", aktion_anna="call",
                abgeschlossen=True, big_blind=20, empfehlungen=()):
    """Eine Hand Anna gegen Ben. ergebnis_anna in Big Blinds (+ gewinnt, - verliert).

    empfehlungen: Liste (strasse, empfohlen, gespielt) fuer Anna.
    """
    hand_id = neue_hand(db, ["Anna", "Ben"], big_blind // 2, big_blind,
                        zeitpunkt=datum + "T20:00:00")
    if aktion_anna == "fold":
        aktion_speichern(db, hand_id, "Anna", "preflop", "fold")
    else:
        aktion_speichern(db, hand_id, "Anna", "preflop", aktion_anna, big_blind * 2)
        aktion_speichern(db, hand_id, "Ben", "preflop", "call", big_blind * 2)
    board_speichern(db, hand_id, BOARD)
    handkarten_speichern(db, hand_id, "Anna", [(14, "Pik"), (13, "Herz")])
    for strasse, empfohlen, gespielt in empfehlungen:
        empfehlung_speichern(db, hand_id, "Anna", strasse, empfohlen, None, gespielt, None,
                             empfohlen == gespielt, 0.5, 0.3)
    einsatz = abs(ergebnis_anna) * big_blind
    if ergebnis_anna >= 0:
        ergebnis_speichern(db, hand_id, "Anna", einsatz, 2 * einsatz)
        ergebnis_speichern(db, hand_id, "Ben", einsatz, 0)
    else:
        ergebnis_speichern(db, hand_id, "Anna", einsatz, 0)
        ergebnis_speichern(db, hand_id, "Ben", einsatz, 2 * einsatz)
    if abgeschlossen:
        hand_abschliessen(db, hand_id)
    return hand_id


def test_unbekannter_spieler(db):
    with pytest.raises(ValueError):
        analyse.gewinnkurve(db, "Niemand")


def test_verlauf_pro_abend_gruppiert_nach_datum(db):
    spiele_hand(db, 2, datum="2026-10-01", aktion_anna="raise")
    spiele_hand(db, -1, datum="2026-10-01", aktion_anna="fold")
    spiele_hand(db, -3, datum="2026-10-08", aktion_anna="call")
    abende = analyse.verlauf_pro_abend(db, "Anna")
    assert [a["datum"] for a in abende] == ["2026-10-01", "2026-10-08"]
    erster = abende[0]
    assert erster["haende"] == 2
    assert erster["vpip"] == 0.5
    assert erster["pfr"] == 0.5
    assert erster["bb"] == 1
    assert erster["bb_pro_100"] == 50
    assert abende[1]["bb_pro_100"] == -300


def test_abgebrochene_haende_zaehlen_nicht(db):
    spiele_hand(db, 5)
    spiele_hand(db, -10, abgeschlossen=False)
    assert analyse.gewinnkurve(db, "Anna")[-1]["bb"] == 5
    assert analyse.verlauf_pro_abend(db, "Anna")[0]["haende"] == 1


def test_gewinnkurve_summiert_auf(db):
    spiele_hand(db, 2)
    spiele_hand(db, -1)
    spiele_hand(db, 4)
    kurve = analyse.gewinnkurve(db, "Anna")
    assert [punkt["bb"] for punkt in kurve] == [2, 1, 5]
    assert [punkt["nr"] for punkt in kurve] == [1, 2, 3]


def test_ki_auswertung_teilt_in_gruppen(db):
    # befolgt: alle Entscheidungen wie empfohlen
    spiele_hand(db, 3, empfehlungen=[("preflop", "call", "call"), ("flop", "check", "check")])
    # abgewichen: eine Entscheidung anders
    spiele_hand(db, -4, empfehlungen=[("preflop", "fold", "call"), ("flop", "check", "check")])
    # ohne KI
    spiele_hand(db, 1)
    ki = analyse.ki_auswertung(db, "Anna")
    assert ki["entscheidungen"] == 4
    assert ki["befolgt"] == 3
    assert ki["quote"] == 0.75
    assert ki["gruppen"]["befolgt"] == {"haende": 1, "bb": 3, "bb_pro_100": 300}
    assert ki["gruppen"]["abgewichen"]["bb_pro_100"] == -400
    assert ki["gruppen"]["ohne_ki"]["haende"] == 1


def test_ki_auswertung_ohne_empfehlungen(db):
    spiele_hand(db, 1)
    ki = analyse.ki_auswertung(db, "Anna")
    assert ki["quote"] is None
    assert ki["gruppen"]["befolgt"]["bb_pro_100"] is None


def test_fehlentscheidungen_teuerste_zuerst(db):
    spiele_hand(db, -2, empfehlungen=[("preflop", "fold", "call")])
    spiele_hand(db, -8, empfehlungen=[("turn", "fold", "call")])
    spiele_hand(db, 5, empfehlungen=[("preflop", "fold", "fold")])   # befolgt -> nicht dabei
    spiele_hand(db, -20, abgeschlossen=False,
                empfehlungen=[("river", "fold", "call")])            # abgebrochen -> nicht dabei
    fehler = analyse.fehlentscheidungen(db, "Anna")
    assert [f["ergebnis_bb"] for f in fehler] == [-8, -2]
    assert fehler[0]["strasse"] == "turn"
    assert fehler[0]["board"] == BOARD[:4]     # auf dem Turn lagen 4 Karten
    assert fehler[1]["board"] == []
    assert fehler[0]["handkarten"] == [(14, "Pik"), (13, "Herz")]


def test_teuerste_haende(db):
    spiele_hand(db, -2)
    spiele_hand(db, 6)
    spiele_hand(db, -7)
    teuerste = analyse.teuerste_haende(db, "Anna", anzahl=5)
    assert [h["bb"] for h in teuerste] == [-7, -2]
    assert teuerste[0]["gewinner"] == ["Ben"]
    assert teuerste[0]["verlauf"][0] == {"name": "Anna", "strasse": "preflop",
                                         "aktion": "call", "betrag": 40}


def test_gegner_uebersicht(db):
    for _ in range(3):
        spiele_hand(db, 1)
    gegner = analyse.gegner_uebersicht(db, ohne="Anna")
    assert [g["name"] for g in gegner] == ["Ben"]
    assert gegner[0]["haende"] == 3
    assert gegner[0]["typ"] == "unbekannt"      # unter 20 Haenden
    assert gegner[0]["tipps"] == analyse.ANPASSUNG["unbekannt"]


def test_jeder_typ_hat_tipps():
    from poker.ki import TYP_NAMEN
    for typ in TYP_NAMEN:
        assert analyse.ANPASSUNG[typ]


def test_analyse_paket(db):
    spiele_hand(db, 1)
    paket = analyse.analyse(db, "Anna")
    assert set(paket) == {"name", "statistik", "abende", "kurve", "ki", "fehler",
                          "teuerste", "gegner"}
    assert paket["gegner"][0]["name"] == "Ben"
