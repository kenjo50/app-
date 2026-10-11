"""Tests fuer poker/turnier.py. Zeit wird als Zahl uebergeben, nichts wartet wirklich."""

import pytest

from poker.profile import oeffne_datenbank
from poker.turnier import (
    STANDARD_VORLAGEN,
    anzeige,
    aktualisiere,
    ansage_text,
    level,
    level_nummer,
    naechstes_level,
    neuer_timer,
    pause,
    pausiere,
    pruefe_struktur,
    restzeit,
    starte,
    vorheriges_level,
    vorlage_laden,
    vorlage_loeschen,
    vorlage_speichern,
    vorlagen_namen,
    zeit_anpassen,
    zeit_bis_pause,
)

# 2 Levels a 10 Minuten, 5 Minuten Pause, dann 2 Levels a 10 Minuten
STRUKTUR = [
    level(25, 50, 10),
    level(50, 100, 10),
    pause(5),
    level(100, 200, 10, ante=25),
    level(200, 400, 10, ante=50),
]
START = 1000.0  # beliebiger Startzeitpunkt in Sekunden


def texte(ansagen):
    ergebnis = []
    for a in ansagen:
        ergebnis.append(a["text"])
    return ergebnis


# ---------- Blindstruktur ----------


def test_level_nummern_ohne_pausen():
    assert level_nummer(STRUKTUR, 0) == 1
    assert level_nummer(STRUKTUR, 1) == 2
    assert level_nummer(STRUKTUR, 2) is None  # Pause
    assert level_nummer(STRUKTUR, 3) == 3


def test_ansage_texte():
    assert ansage_text(STRUKTUR, 0) == "Level 1. Blinds 25 und 50."
    assert ansage_text(STRUKTUR, 2) == "Pause. 5 Minuten."
    assert ansage_text(STRUKTUR, 4) == "Level 4. Blinds 200 und 400, Ante 50."


def test_struktur_pruefen():
    pruefe_struktur(STRUKTUR)
    for vorlage in STANDARD_VORLAGEN.values():
        pruefe_struktur(vorlage)
    for falsch in [
        [],
        [pause(5), level(25, 50, 10)],      # beginnt mit Pause
        [level(50, 25, 10)],                # SB groesser als BB
        [level(25, 50, 0)],                 # keine Dauer
        [level(30, 60, 10)],                # mit 25er-Chips nicht zahlbar
        [level(25, 50, 10, ante=10)],       # Ante nicht zahlbar
    ]:
        with pytest.raises(ValueError):
            pruefe_struktur(falsch)


# ---------- Timer: Start, Restzeit, Levelwechsel ----------


def test_start_sagt_level_1_an():
    t = neuer_timer(STRUKTUR)
    assert restzeit(t, START) == 600
    assert texte(starte(t, START)) == ["Level 1. Blinds 25 und 50."]
    assert restzeit(t, START + 1) == 599


def test_restzeit_aus_zeitstempel():
    # Auch nach einer langen Luecke (Handy im Hintergrund) stimmt die Zeit.
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    assert restzeit(t, START + 123.5) == pytest.approx(476.5)


def test_minuten_hinweis_und_levelwechsel():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    assert aktualisiere(t, START + 539) == []
    hinweis = aktualisiere(t, START + 540)
    assert texte(hinweis) == ["Noch eine Minute in diesem Level."]
    assert hinweis[0]["zeit"] == START + 540
    assert aktualisiere(t, START + 599) == []  # nicht doppelt
    wechsel = aktualisiere(t, START + 600)
    assert texte(wechsel) == ["Level 2. Blinds 50 und 100."]
    assert t["index"] == 1
    assert restzeit(t, START + 600) == 600


def test_hinweis_vor_der_pause_und_pause():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    aktualisiere(t, START + 600)
    assert texte(aktualisiere(t, START + 1140)) == ["Noch eine Minute bis zur Pause."]
    assert texte(aktualisiere(t, START + 1200)) == ["Pause. 5 Minuten."]
    assert anzeige(t, START + 1200)["pause"] is True


def test_mehrere_levelwechsel_nach_hintergrund():
    # 25 Minuten nicht nachgeschaut: Level 1 und 2 vorbei, 5 Minuten Pause vorbei.
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    ansagen = aktualisiere(t, START + 25 * 60 + 30)
    assert t["index"] == 3
    assert restzeit(t, START + 25 * 60 + 30) == 570
    # Jede Ansage hat ihren eigentlichen Zeitpunkt
    assert ansagen[-1]["text"] == "Level 3. Blinds 100 und 200, Ante 25."
    assert ansagen[-1]["zeit"] == START + 25 * 60


def test_letztes_level_endet():
    t = neuer_timer([level(25, 50, 1)])
    starte(t, START)
    assert texte(aktualisiere(t, START + 60)) == ["Das letzte Level ist abgelaufen."]
    assert t["vorbei"] and not t["laeuft"]
    assert restzeit(t, START + 100) == 0


def test_kurzes_level_ohne_minuten_hinweis():
    t = neuer_timer([level(25, 50, 1), level(50, 100, 1)])
    starte(t, START)
    assert texte(aktualisiere(t, START + 60)) == ["Level 2. Blinds 50 und 100."]


# ---------- Steuerung ----------


def test_pause_und_fortsetzen():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    pausiere(t, START + 100)
    assert restzeit(t, START + 5000) == 500  # angehalten: Zeit steht
    assert starte(t, START + 5000) == []     # Fortsetzen ohne erneute Ansage
    assert restzeit(t, START + 5010) == 490


def test_naechstes_und_vorheriges_level():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    assert texte(naechstes_level(t, START + 100)) == ["Level 2. Blinds 50 und 100."]
    assert restzeit(t, START + 100) == 600  # neues Level startet mit voller Zeit
    assert texte(vorheriges_level(t, START + 200)) == ["Level 1. Blinds 25 und 50."]
    with pytest.raises(ValueError):
        vorheriges_level(t, START + 200)


def test_naechstes_level_im_angehaltenen_timer():
    t = neuer_timer(STRUKTUR)
    naechstes_level(t, START)
    assert t["index"] == 1 and restzeit(t, START) == 600


def test_zeit_anpassen():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    zeit_anpassen(t, START, 60)
    assert restzeit(t, START) == 660
    zeit_anpassen(t, START, -120)
    assert restzeit(t, START) == 540
    zeit_anpassen(t, START, -10000)
    assert restzeit(t, START) == 0
    assert texte(aktualisiere(t, START)) == ["Level 2. Blinds 50 und 100."]


def test_zeit_anpassen_minuten_hinweis_kommt_wieder():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    aktualisiere(t, START + 540)          # Hinweis kam schon
    zeit_anpassen(t, START + 540, 60)     # wieder 2 Minuten
    assert texte(aktualisiere(t, START + 600)) == ["Noch eine Minute in diesem Level."]


def test_zeit_anpassen_angehalten():
    t = neuer_timer(STRUKTUR)
    zeit_anpassen(t, START, -60)
    assert restzeit(t, START) == 540


# ---------- Anzeige ----------


def test_anzeige():
    t = neuer_timer(STRUKTUR)
    starte(t, START)
    a = anzeige(t, START + 60)
    assert a["nummer"] == 1
    assert (a["small_blind"], a["big_blind"], a["ante"]) == (25, 50, 0)
    assert a["restzeit"] == 540
    assert a["naechstes"]["big_blind"] == 100
    assert a["naechstes"]["nummer"] == 2
    assert a["zeit_bis_pause"] == 540 + 600


def test_zeit_bis_pause_keine_mehr():
    t = neuer_timer(STRUKTUR)
    naechstes_level(t, START)
    naechstes_level(t, START)
    assert zeit_bis_pause(t, START) is None  # gerade Pause
    naechstes_level(t, START)
    assert zeit_bis_pause(t, START) is None  # danach keine Pause mehr


# ---------- Vorlagen ----------


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


def test_standard_vorlagen_sind_da(db):
    assert "Schnelles Turnier" in vorlagen_namen(db)
    assert vorlage_laden(db, "Langer Abend")[0]["big_blind"] == 50


def test_vorlage_speichern_und_laden(db):
    vorlage_speichern(db, "Mini", STRUKTUR)
    assert vorlage_laden(db, "Mini") == STRUKTUR
    assert "Mini" in vorlagen_namen(db)
    vorlage_loeschen(db, "Mini")
    with pytest.raises(ValueError):
        vorlage_laden(db, "Mini")


def test_ungueltige_vorlage_wird_nicht_gespeichert(db):
    with pytest.raises(ValueError):
        vorlage_speichern(db, "Kaputt", [level(30, 60, 10)])
    with pytest.raises(ValueError):
        vorlage_speichern(db, "  ", STRUKTUR)
