"""Tests fuer poker/profile.py. Jede Datenbank liegt nur im Arbeitsspeicher."""

import pytest

from poker.profile import (
    aktion_speichern,
    berechne_statistik,
    board_speichern,
    handkarten_speichern,
    lade_aktionen,
    neue_hand,
    oeffne_datenbank,
    spieler_id,
    text_zu_karten,
)


@pytest.fixture
def db():
    """Frische, leere Datenbank fuer jeden Test."""
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def test_spieler_wird_nur_einmal_angelegt(db):
    erste = spieler_id(db, "Anna")
    zweite = spieler_id(db, "Anna")
    assert erste == zweite
    assert spieler_id(db, "Ben") != erste


def test_aktionen_in_reihenfolge(db):
    hand = neue_hand(db, ["Anna", "Ben"], 1, 2)
    aktion_speichern(db, hand, "Anna", "preflop", "raise", 6)
    aktion_speichern(db, hand, "Ben", "preflop", "call", 6)
    aktion_speichern(db, hand, "Ben", "flop", "check")
    aktion_speichern(db, hand, "Anna", "flop", "bet", 8)
    aktion_speichern(db, hand, "Ben", "flop", "fold")
    assert lade_aktionen(db, hand) == [
        ("Anna", "preflop", "raise", 6),
        ("Ben", "preflop", "call", 6),
        ("Ben", "flop", "check", 0),
        ("Anna", "flop", "bet", 8),
        ("Ben", "flop", "fold", 0),
    ]


def test_karten_speichern_und_laden(db):
    hand = neue_hand(db, ["Anna", "Ben"], 1, 2)
    board = [(14, "Pik"), (7, "Herz"), (2, "Karo")]
    board_speichern(db, hand, board)
    handkarten_speichern(db, hand, "Anna", [(13, "Kreuz"), (13, "Herz")])
    gespeichertes_board = db.execute("SELECT board FROM haende WHERE id = ?", (hand,)).fetchone()[0]
    assert text_zu_karten(gespeichertes_board) == board
    gespeicherte_hand = db.execute(
        "SELECT handkarten FROM teilnehmer WHERE hand_id = ?", (hand,)
    ).fetchall()
    # Annas Karten sind bekannt, Bens nicht (None)
    assert text_zu_karten(gespeicherte_hand[0][0]) == [(13, "Kreuz"), (13, "Herz")]
    assert gespeicherte_hand[1][0] is None


def test_falsche_eingaben_geben_fehler(db):
    hand = neue_hand(db, ["Anna", "Ben"], 1, 2)
    with pytest.raises(ValueError):
        aktion_speichern(db, hand, "Anna", "preflop", "allin", 100)  # unbekannte Aktion
    with pytest.raises(ValueError):
        aktion_speichern(db, hand, "Anna", "showdown", "bet", 5)  # unbekannte Strasse
    with pytest.raises(ValueError):
        aktion_speichern(db, hand, "Clara", "preflop", "call", 2)  # nicht am Tisch
    with pytest.raises(ValueError):
        aktion_speichern(db, hand, "Anna", "preflop", "raise", 0)  # raise ohne Betrag
    with pytest.raises(ValueError):
        neue_hand(db, ["Anna", "Anna"], 1, 2)


def test_statistik(db):
    # Hand 1: Anna erhoeht, Ben callt. Flop: Anna bettet, Ben callt.
    h1 = neue_hand(db, ["Anna", "Ben"], 1, 2)
    aktion_speichern(db, h1, "Anna", "preflop", "raise", 6)
    aktion_speichern(db, h1, "Ben", "preflop", "call", 6)
    aktion_speichern(db, h1, "Ben", "flop", "check")
    aktion_speichern(db, h1, "Anna", "flop", "bet", 8)
    aktion_speichern(db, h1, "Ben", "flop", "call", 8)
    aktion_speichern(db, h1, "Ben", "turn", "bet", 20)
    aktion_speichern(db, h1, "Anna", "turn", "call", 20)

    # Hand 2: Anna foldet, Ben gewinnt die Blinds.
    h2 = neue_hand(db, ["Anna", "Ben"], 1, 2)
    aktion_speichern(db, h2, "Anna", "preflop", "fold")

    # Hand 3: Anna callt nur, Ben checkt (Big Blind, nicht freiwillig).
    h3 = neue_hand(db, ["Anna", "Ben"], 1, 2)
    aktion_speichern(db, h3, "Anna", "preflop", "call", 2)
    aktion_speichern(db, h3, "Ben", "preflop", "check")
    aktion_speichern(db, h3, "Ben", "flop", "bet", 2)
    aktion_speichern(db, h3, "Anna", "flop", "raise", 8)
    aktion_speichern(db, h3, "Ben", "flop", "fold")

    anna = berechne_statistik(db, "Anna")
    assert anna["haende"] == 3
    assert anna["vpip"] == pytest.approx(2 / 3)  # Hand 1 und 3
    assert anna["pfr"] == pytest.approx(1 / 3)   # nur Hand 1
    assert anna["af"] == pytest.approx(2 / 1)    # bet + raise, 1 call

    ben = berechne_statistik(db, "Ben")
    assert ben["vpip"] == pytest.approx(1 / 3)   # nur Hand 1 (Check im BB zaehlt nicht)
    assert ben["pfr"] == 0
    assert ben["af"] == pytest.approx(2 / 1)     # 2 bets, 1 call


def test_statistik_ohne_calls_hat_keinen_af(db):
    hand = neue_hand(db, ["Anna", "Ben"], 1, 2)
    aktion_speichern(db, hand, "Anna", "preflop", "fold")
    assert berechne_statistik(db, "Anna")["af"] is None


def test_unbekannter_spieler(db):
    with pytest.raises(ValueError):
        berechne_statistik(db, "Niemand")


def test_alte_datenbank_bekommt_neue_spalten(tmp_path):
    # Eine Datenbank im alten Format (ohne investiert/gewonnen) anlegen ...
    import sqlite3
    pfad = tmp_path / "alt.db"
    alt = sqlite3.connect(pfad)
    alt.execute("CREATE TABLE teilnehmer (hand_id INTEGER, spieler_id INTEGER, "
                "sitzplatz INTEGER, handkarten TEXT)")
    alt.commit()
    alt.close()
    # ... und mit der neuen Version oeffnen: die Spalten werden nachgeruestet.
    verbindung = oeffne_datenbank(pfad)
    spalten = []
    for zeile in verbindung.execute("PRAGMA table_info(teilnehmer)"):
        spalten.append(zeile[1])
    verbindung.close()
    assert "investiert" in spalten and "gewonnen" in spalten
