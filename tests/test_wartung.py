"""Tests fuer poker/wartung.py: Sicherung und Aufraeumen."""

from datetime import datetime, timedelta

import pytest

from poker import kasse, tisch
from poker.profile import anzahl_abgebrochene, berechne_statistik, oeffne_datenbank, spieler_namen
from poker.wartung import (
    abend_loeschen,
    abgebrochene_haende_loeschen,
    sicherung_anlegen,
    sicherungen_liste,
    spieler_loeschen,
    spieler_loeschvorschau,
    spieler_uebersicht,
)


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def spiele_hand(db, namen):
    """Eine fertige Hand: alle folden zum Big Blind."""
    abend = tisch.neuer_abend(db, namen, {n: 1000 for n in namen}, 10, 20)
    tisch.starte_naechste_hand(db, abend)
    while tisch.phase(abend) == "aktion":
        tisch.aktion(db, abend, "fold")
    tisch.abrechnen_ohne_showdown(db, abend)
    return abend


# ---------- Sicherung ----------


def test_sicherung_anlegen(tmp_path):
    pfad = tmp_path / "heimrunde.db"
    verbindung = oeffne_datenbank(str(pfad))
    verbindung.execute("INSERT INTO spieler (name) VALUES ('Anna')")
    verbindung.commit()
    kopie = sicherung_anlegen(str(pfad))
    assert kopie.exists() and kopie.parent.name == "sicherungen"
    # Die Kopie ist eine vollstaendige Datenbank
    assert spieler_namen(oeffne_datenbank(str(kopie))) == ["Anna"]
    assert sicherungen_liste(str(pfad))[0]["name"] == kopie.name
    verbindung.close()


def test_nur_die_neuesten_sicherungen_bleiben(tmp_path):
    pfad = tmp_path / "heimrunde.db"
    oeffne_datenbank(str(pfad)).close()
    start = datetime(2026, 10, 1, 20, 0, 0)
    for i in range(5):
        sicherung_anlegen(str(pfad), jetzt=start + timedelta(days=i), behalten=3)
    namen = [s["name"] for s in sicherungen_liste(str(pfad))]
    assert namen == ["heimrunde_2026-10-05_20-00-00.db", "heimrunde_2026-10-04_20-00-00.db",
                     "heimrunde_2026-10-03_20-00-00.db"]


def test_keine_sicherung_ohne_datei(tmp_path):
    assert sicherung_anlegen(":memory:") is None
    assert sicherung_anlegen(str(tmp_path / "gibtsnicht.db")) is None


# ---------- Spieler loeschen ----------


def test_spieler_loeschen_mit_haenden(db):
    spiele_hand(db, ["Anna", "Test", "Ben"])
    spiele_hand(db, ["Anna", "Ben"])
    vorschau = spieler_loeschvorschau(db, "Test")
    assert vorschau["haende"] == 1 and vorschau["mitspieler"] == ["Anna", "Ben"]
    assert spieler_loeschen(db, "Test") == 1
    assert "Test" not in spieler_namen(db)
    # Die Hand mit "Test" ist ganz weg, die andere bleibt
    assert berechne_statistik(db, "Anna")["haende"] == 1


def test_spieler_in_abend_erst_abend_loeschen(db):
    c = kasse.neues_cashgame(db)
    kasse.cash_buyin(db, c, "Test")
    assert spieler_loeschvorschau(db, "Test")["abende"][0]["id"] == c
    with pytest.raises(ValueError):
        spieler_loeschen(db, "Test")
    abend_loeschen(db, c)
    spieler_loeschen(db, "Test")
    assert "Test" not in spieler_namen(db)


def test_spieler_am_live_tisch_nicht_loeschen(db):
    spiele_hand(db, ["Anna", "Ben"])
    with pytest.raises(ValueError):
        spieler_loeschen(db, "Anna", live_spieler=["Anna", "Ben"])


def test_unbekannter_spieler(db):
    with pytest.raises(ValueError):
        spieler_loeschen(db, "Niemand")


# ---------- Abende und abgebrochene Haende ----------


def test_abend_loeschen_entfernt_buchungen(db):
    t = kasse.neues_turnier(db, 1000)
    kasse.turnier_buchen(db, t, "Anna", "buyin")
    abend_loeschen(db, t)
    assert kasse.abende_liste(db) == []
    assert db.execute("SELECT COUNT(*) FROM buchungen").fetchone()[0] == 0
    with pytest.raises(ValueError):
        abend_loeschen(db, t)


def test_abgebrochene_haende_loeschen(db):
    spiele_hand(db, ["Anna", "Ben"])
    abend = tisch.neuer_abend(db, ["Anna", "Ben"], {"Anna": 1000, "Ben": 1000}, 10, 20)
    tisch.starte_naechste_hand(db, abend)
    tisch.hand_abbrechen(abend)                       # abgebrochen
    tisch.starte_naechste_hand(db, abend)             # laeuft gerade
    laufend = abend["hand"]["zustand"]["hand_id"]
    assert anzahl_abgebrochene(db) == 2
    assert abgebrochene_haende_loeschen(db, ausser_hand_id=laufend) == 1
    assert anzahl_abgebrochene(db) == 1               # nur die laufende ist noch da
    assert berechne_statistik(db, "Anna")["haende"] == 1


def test_spieler_uebersicht(db):
    spiele_hand(db, ["Anna", "Ben"])
    c = kasse.neues_cashgame(db)
    kasse.cash_buyin(db, c, "Anna")
    uebersicht = {s["name"]: s for s in spieler_uebersicht(db)}
    assert uebersicht["Anna"] == {"name": "Anna", "haende": 1, "abende": 1}
    assert uebersicht["Ben"]["abende"] == 0
