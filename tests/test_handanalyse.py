"""Tests fuer die Hand-Analyse (poker/handanalyse.py)."""

import pytest

from poker import handanalyse, live
from poker.deck import lies_karten
from poker.profile import handkarten_speichern, oeffne_datenbank


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def spiele_beispielhand(db):
    """Anna (AA) gegen Ben (KK), Ben trifft am Flop den Drilling.

    Preflop: Anna raise auf 60, Ben call. Flop: Ben bet 60, Anna call.
    Turn: beide check. River: Ben bet 200, Anna fold.
    """
    zustand = live.starte_hand(db, ["Anna", "Ben"], 10, 20, {"Anna": 1000, "Ben": 1000})
    handkarten_speichern(db, zustand["hand_id"], "Anna", lies_karten("As Ad"))
    handkarten_speichern(db, zustand["hand_id"], "Ben", lies_karten("Kh Kd"))
    board = lies_karten("2c 7s Ks 9d 3h")
    live.verarbeite_aktion(db, zustand, "Anna", "raise", 60)
    live.verarbeite_aktion(db, zustand, "Ben", "call")
    live.naechste_strasse(db, zustand, board[:3])
    live.verarbeite_aktion(db, zustand, "Ben", "raise", 60)
    live.verarbeite_aktion(db, zustand, "Anna", "call")
    live.naechste_strasse(db, zustand, board[3:4])
    live.verarbeite_aktion(db, zustand, "Ben", "check")
    live.verarbeite_aktion(db, zustand, "Anna", "check")
    live.naechste_strasse(db, zustand, board[4:5])
    live.verarbeite_aktion(db, zustand, "Ben", "raise", 200)
    live.verarbeite_aktion(db, zustand, "Anna", "fold")
    live.abrechnen(db, zustand, live.gewinner_ohne_showdown(zustand))
    return zustand["hand_id"]


# ---------- Equity und Outs ----------


def test_equity_bekannt_preflop():
    aa, kk = handanalyse.equity_bekannt([lies_karten("As Ad"), lies_karten("Kh Kd")], [])
    assert abs(aa - 0.82) < 0.03      # Referenz aus dem Fahrplan
    assert abs(aa + kk - 1) < 1e-9


def test_equity_bekannt_ist_ab_dem_flop_exakt():
    haende = [lies_karten("As Ad"), lies_karten("Kh Kd")]
    board = lies_karten("2c 7s Ks")
    erste = handanalyse.equity_bekannt(haende, board)
    assert erste == handanalyse.equity_bekannt(haende, board)   # kein Zufall mehr
    # AA braucht eins der zwei restlichen Asse (8,8 %) oder zwei weitere Pik
    # fuer den Flush mit dem Pik-Ass (Backdoor) - zusammen 121 von 990 Boards
    assert erste[0] == pytest.approx(121 / 990)


def test_equity_river_split():
    haende = [lies_karten("2c 3d"), lies_karten("2h 3s")]
    assert handanalyse.equity_bekannt(haende, lies_karten("As Ks Qs Js Ts")) == [0.5, 0.5]


def test_doppelte_karte():
    with pytest.raises(ValueError):
        handanalyse.equity_bekannt([lies_karten("As Ad"), lies_karten("As Kd")], [])


def test_outs_gegen_bekannte_hand():
    # Flush-Draw gegen Drilling: 9 Herz minus die, die dem Drilling Full House/Vierling geben
    o = handanalyse.outs(lies_karten("Ah Kh"), lies_karten("2h 7h 9d"), [lies_karten("9s 9c")])
    assert o["art"] == "outs" and o["anzahl"] == 8
    assert o["gruppen"][0]["handart"] == "Flush"


def test_outs_wenn_man_vorne_liegt():
    o = handanalyse.outs(lies_karten("9s 9c"), lies_karten("2h 7h 9d"), [lies_karten("Ah Kh")])
    assert o["art"] == "gefaehrlich" and o["anzahl"] == 8
    assert len(o["gruppen"]) == 1 and o["gruppen"][0]["handart"] is None


def test_outs_verbesserung_ohne_gegner():
    o = handanalyse.outs(lies_karten("Ah Kh"), lies_karten("2h 7h 9d"))
    assert o["art"] == "verbesserung"
    gruppen = {g["handart"]: len(g["karten"]) for g in o["gruppen"]}
    assert gruppen == {"Flush": 9, "Paar": 6}


def test_board_paar_zaehlt_nicht_als_verbesserung():
    # Ein Board-Paar verbessert jeden - das ist kein Out fuer A-K
    o = handanalyse.outs(lies_karten("Ac Kd"), lies_karten("2h 7s 9d"))
    karten = [k for g in o["gruppen"] for k in g["karten"]]
    assert (2, "Pik") not in karten and (14, "Pik") in karten


def test_keine_outs_preflop_und_river():
    assert handanalyse.outs(lies_karten("Ah Kh"), []) is None
    assert handanalyse.outs(lies_karten("Ah Kh"), lies_karten("2h 7s 9d Qc 3s")) is None


# ---------- Gespeicherte Hand ----------


def test_analysiere_hand(db):
    hand_id = spiele_beispielhand(db)
    a = handanalyse.analysiere_hand(db, hand_id)
    assert [s["strasse"] for s in a["strassen"]] == ["preflop", "flop", "turn", "river"]
    assert a["ergebnis"] == {"Anna": -120, "Ben": 120}

    preflop, flop, turn, river = a["strassen"]
    assert preflop["pot"] == 30 and flop["pot"] == 120 and turn["pot"] == 240
    assert abs(preflop["equity"]["Anna"]["wirklich"] - 0.82) < 0.03
    assert 0 < preflop["equity"]["Anna"]["zufall"] < 1
    assert 0 < preflop["equity"]["Anna"]["bereich"] < 1

    # Ben callt preflop 40 in einen Pot von 80: braucht 1/3, hat ca. 18 %
    call = preflop["entscheidungen"][1]
    assert call["name"] == "Ben" and call["zu_callen"] == 40 and call["pot"] == 80
    assert abs(call["pot_odds"] - 1 / 3) < 1e-9
    assert call["urteil"] == "zu teuer"

    # Anna callt am Flop 60 in 180: braucht 25 %, hat gegen den Drilling ca. 9 %
    anna_call = flop["entscheidungen"][1]
    assert anna_call["zu_callen"] == 60 and anna_call["pot_odds"] == 0.25
    assert anna_call["urteil"] == "zu teuer"
    assert flop["outs"]["Anna"]["anzahl"] == 2          # die zwei letzten Asse
    assert flop["outs"]["Ben"]["art"] == "gefaehrlich"

    # River: Fold gegen den Drilling war richtig
    fold = river["entscheidungen"][1]
    assert fold["aktion"] == "fold" and fold["urteil"] == "Fold ok"
    assert river["equity"]["Anna"]["wirklich"] == 0.0


def test_analyse_ist_reproduzierbar(db):
    hand_id = spiele_beispielhand(db)
    assert handanalyse.analysiere_hand(db, hand_id) == handanalyse.analysiere_hand(db, hand_id)


def test_unbekannte_gegnerkarten(db):
    hand_id = spiele_beispielhand(db)
    db.execute("UPDATE teilnehmer SET handkarten = NULL WHERE spieler_id = "
               "(SELECT id FROM spieler WHERE name = 'Ben')")
    a = handanalyse.analysiere_hand(db, hand_id)
    werte = a["strassen"][1]["equity"]["Anna"]
    assert werte["wirklich"] is None                    # Bens Karten fehlen
    assert werte["zufall"] is not None and werte["bereich"] is not None
    assert "Ben" not in a["strassen"][1]["equity"]
    assert a["strassen"][1]["outs"]["Anna"]["art"] == "verbesserung"


def test_unbekannte_hand(db):
    with pytest.raises(ValueError):
        handanalyse.analysiere_hand(db, 99)


def test_hand_liste(db):
    hand_id = spiele_beispielhand(db)
    # Eine Hand ohne bekannte Karten taucht nicht auf
    zustand = live.starte_hand(db, ["Anna", "Ben"], 10, 20, {"Anna": 1000, "Ben": 1000})
    live.verarbeite_aktion(db, zustand, "Anna", "fold")
    live.abrechnen(db, zustand, live.gewinner_ohne_showdown(zustand))
    liste = handanalyse.hand_liste(db, "Anna")
    assert [h["hand_id"] for h in liste] == [hand_id]
    assert liste[0]["ergebnis"] == -120 and liste[0]["gewinner"] == ["Ben"]
    assert liste[0]["karten"] == lies_karten("As Ad")
    assert handanalyse.hand_liste(db, "Niemand") == []


# ---------- Odds-Rechner ----------


def test_odds_rechner_zwei_haende():
    r = handanalyse.odds_rechner([lies_karten("As Ks"), lies_karten("Qd Qc")], [])
    assert r["art"] == "wirklich"
    assert abs(r["haende"][0]["equity"] - 0.46) < 0.02


def test_odds_rechner_gegen_zufall():
    r = handanalyse.odds_rechner([lies_karten("As Ad")], [], zufalls_gegner=1)
    assert r["art"] == "zufall" and abs(r["haende"][0]["equity"] - 0.85) < 0.03


@pytest.mark.parametrize("haende, board", [
    ([], []),
    ([lies_karten("As")], []),
    ([lies_karten("As Kd"), lies_karten("As Qd")], []),
    ([lies_karten("As Kd")], lies_karten("2c 3c")),
])
def test_odds_rechner_fehler(haende, board):
    with pytest.raises(ValueError):
        handanalyse.odds_rechner(haende, board)


# ---------- Tisch-Rechner (Strasse fuer Strasse) ----------


def test_odds_verlauf_strasse_fuer_strasse():
    r = handanalyse.odds_verlauf([lies_karten("As Ad"), lies_karten("Kh Kd")],
                                 lies_karten("2c 7s Ks 9d 3h"))
    assert [s["strasse"] for s in r["strassen"]] == ["preflop", "flop", "turn", "river"]
    preflop, flop, turn, river = [[h["equity"] for h in s["haende"]] for s in r["strassen"]]
    assert abs(preflop[0] - 0.82) < 0.03
    assert flop[0] == pytest.approx(121 / 990)     # exakt, wie oben
    assert river == [0.0, 1.0]
    assert r["strassen"][1]["haende"][0]["outs"]["anzahl"] == 2
    assert r["strassen"][3]["haende"][1]["handart"] == "Drilling"


def test_odds_verlauf_nur_bis_zum_eingegebenen_board():
    r = handanalyse.odds_verlauf([lies_karten("As Ad"), lies_karten("Kh Kd")], lies_karten("2c 7s Ks"))
    assert [s["strasse"] for s in r["strassen"]] == ["preflop", "flop"]


def test_odds_verlauf_mit_unbekannten_gegnern():
    r = handanalyse.odds_verlauf([lies_karten("As Ad")], [], zufalls_gegner=3)
    s = r["strassen"][0]
    assert abs(s["haende"][0]["equity"] - 0.64) < 0.03      # AA gegen 3 Zufallshaende
    assert abs(s["haende"][0]["equity"] + s["zufall_equity"] - 1) < 1e-9


def test_odds_verlauf_bekannt_und_unbekannt_gemischt():
    r = handanalyse.odds_verlauf([lies_karten("As Ad"), lies_karten("Kh Kd")], [], zufalls_gegner=1)
    aa, kk = [h["equity"] for h in r["strassen"][0]["haende"]]
    assert aa > kk > 0
    assert abs(aa + kk + r["strassen"][0]["zufall_equity"] - 1) < 1e-9


def test_odds_verlauf_ist_reproduzierbar():
    argumente = ([lies_karten("As Kd")], lies_karten("2c 7s 9d"), 2)
    assert handanalyse.odds_verlauf(*argumente) == handanalyse.odds_verlauf(*argumente)


@pytest.mark.parametrize("haende, board, zufall", [
    ([], [], 2),                                         # keine bekannte Hand
    ([lies_karten("As Kd")], [], 0),                     # allein am Tisch
    ([lies_karten("As Kd")] * 1, [], 9),                 # 10 Spieler
    ([lies_karten("As Kd"), lies_karten("As Qd")], [], 0),
    ([lies_karten("As Kd")], lies_karten("2c 3c"), 1),
])
def test_odds_verlauf_fehler(haende, board, zufall):
    with pytest.raises(ValueError):
        handanalyse.odds_verlauf(haende, board, zufall)
