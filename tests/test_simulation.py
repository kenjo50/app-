"""Tests fuer poker/simulation.py."""

import random

import pytest

from poker.profile import anzahl_abgebrochene, berechne_statistik
from poker.simulation import (
    erstelle_aufstellung,
    oeffne_simulationsdatenbank,
    simuliere,
    spiele_bot_hand,
    werte_aus,
)


@pytest.fixture
def db():
    verbindung = oeffne_simulationsdatenbank(":memory:")
    yield verbindung
    verbindung.close()


def test_aufstellung_namen():
    bots = erstelle_aufstellung(["zufall", "equity", "equity"])
    assert list(bots) == ["Zufall 1", "Equity 1", "Equity 2"]
    for falsch in [["zufall"], ["zufall", "hai"]]:
        with pytest.raises(ValueError):
            erstelle_aufstellung(falsch)


def test_eine_hand_keine_chips_verschwinden(db):
    bots = erstelle_aufstellung(["zufall", "zufall", "zufall"])
    namen = list(bots)
    zufall = random.Random(7)
    for i in range(50):
        stacks = {name: 200 for name in namen}
        ergebnis = spiele_bot_hand(db, namen, bots, stacks, 1, 2, zufall)
        assert sum(ergebnis.values()) == pytest.approx(0)


def test_viele_zufallshaende_laufen_fehlerfrei(db):
    # Zufalls-Bots probieren alle moeglichen Aktionen und Raise-Groessen aus:
    # Laeuft das ohne Fehler, halten sich die Bots an alle Regeln.
    auswertung = simuliere(db, ["zufall"] * 6, 300, seed=11)
    summe = sum(w["gesamt_bb"] for w in auswertung.values())
    assert summe == pytest.approx(0)
    assert anzahl_abgebrochene(db) == 0


def test_gleicher_seed_gleiches_ergebnis():
    erstes = simuliere(oeffne_simulationsdatenbank(":memory:"), ["zufall", "equity"], 30, seed=5)
    zweites = simuliere(oeffne_simulationsdatenbank(":memory:"), ["zufall", "equity"], 30, seed=5)
    assert erstes == zweites


def test_haende_landen_in_der_statistik(db):
    simuliere(db, ["zufall", "zufall"], 20, seed=3)
    statistik = berechne_statistik(db, "Zufall 1")
    assert statistik["haende"] == 20
    assert statistik["vpip"] is not None
    # Alle Handkarten werden gespeichert (auch ohne Showdown)
    ohne_karten = db.execute("SELECT COUNT(*) FROM teilnehmer WHERE handkarten IS NULL").fetchone()
    assert ohne_karten[0] == 0


def test_equity_bot_schlaegt_zufalls_bot(db):
    auswertung = simuliere(db, ["zufall", "equity"], 150, seed=21)
    assert auswertung["Equity 1"]["bb_pro_100"] > 0
    assert auswertung["Zufall 1"]["bb_pro_100"] < 0


def test_fortschritt_wird_gemeldet(db):
    meldungen = []
    simuliere(db, ["zufall", "zufall"], 5, seed=1,
              fortschritt=lambda fertig, gesamt: meldungen.append((fertig, gesamt)))
    assert meldungen[-1] == (5, 5) and len(meldungen) == 5


def test_auswertung():
    a = werte_aus({"A": [1, -1, 2, 2]})["A"]
    assert a["haende"] == 4
    assert a["gesamt_bb"] == 4
    assert a["bb_pro_100"] == 100
    # Mittelwert 1, Standardabweichung wurzel(2), Standardfehler wurzel(2) / wurzel(4)
    assert a["fehler_95"] == pytest.approx(1.96 * 2 ** 0.5 / 2 * 100)
    assert werte_aus({"B": [3]})["B"]["fehler_95"] is None


# ---------- Duplicate-Modus ----------


def immer_mitgehen(sicht, zufall):
    """Test-Bot ohne Zufall: checkt oder callt immer."""
    return ("check", None) if "check" in sicht["erlaubt"] else ("call", None)


def test_duplicate_gleiche_bots_genau_null(db):
    # Zwei identische Bots ohne Zufall: Im Duplicate-Modus bekommt jeder genau
    # dieselben Karten auf demselben Platz -> beide enden exakt bei 0.
    from poker.simulation import simuliere_bots
    bots = {"A": immer_mitgehen, "B": immer_mitgehen}
    auswertung = simuliere_bots(db, bots, 100, zufall=random.Random(1), duplicate=True)
    assert auswertung["A"]["gesamt_bb"] == pytest.approx(0)
    assert auswertung["B"]["gesamt_bb"] == pytest.approx(0)
    # Ohne Duplicate entscheidet das Kartenglueck
    normal = simuliere_bots(db, bots, 100, zufall=random.Random(1))
    assert normal["A"]["gesamt_bb"] != pytest.approx(0)


def test_duplicate_gleiche_karten_auf_gleichem_platz(db):
    simuliere(db, ["zufall", "zufall", "zufall"], 3, seed=4, duplicate=True)
    karten_platz_0 = db.execute(
        "SELECT handkarten FROM teilnehmer WHERE sitzplatz = 0 ORDER BY hand_id").fetchall()
    assert len(karten_platz_0) == 3
    assert karten_platz_0[0] == karten_platz_0[1] == karten_platz_0[2]
    spieler_platz_0 = db.execute(
        "SELECT spieler_id FROM teilnehmer WHERE sitzplatz = 0 ORDER BY hand_id").fetchall()
    assert len(set(spieler_platz_0)) == 3   # jedes Mal ein anderer Bot


def test_duplicate_rundet_handzahl_auf(db):
    auswertung = simuliere(db, ["zufall", "zufall", "zufall"], 5, seed=1, duplicate=True)
    assert auswertung["Zufall 1"]["haende"] == 6


def test_duplicate_verkleinert_unsicherheit():
    normal = simuliere(oeffne_simulationsdatenbank(":memory:"),
                       ["zufall", "equity"], 400, seed=9)
    duplicate = simuliere(oeffne_simulationsdatenbank(":memory:"),
                          ["zufall", "equity"], 400, seed=9, duplicate=True)
    assert duplicate["Equity 1"]["fehler_95"] < normal["Equity 1"]["fehler_95"]


def test_auswertung_mit_gruppen():
    # Gruppen [1, -1] und [2, 2] -> Mittel 0 und 2
    a = werte_aus({"A": [1, -1, 2, 2]}, gruppe=2)["A"]
    assert a["bb_pro_100"] == 100
    assert a["fehler_95"] == pytest.approx(1.96 * 2 ** 0.5 / 2 ** 0.5 * 100)
