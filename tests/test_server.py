"""Tests fuer server.py: Die Web-Schnittstelle ruft den Kern richtig auf.

Die Uhr wird durch eine Variable ersetzt, damit wir die Zeit "vorspulen" koennen.
"""

import pytest
from fastapi.testclient import TestClient

from server import erstelle_app


class FalscheUhr:
    def __init__(self):
        self.zeit = 1000.0

    def __call__(self):
        return self.zeit


@pytest.fixture
def uhr():
    return FalscheUhr()


@pytest.fixture
def client(tmp_path, uhr):
    return TestClient(erstelle_app(str(tmp_path / "test.db"), uhr))


def test_startseite(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Heimrunde" in antwort.text


def test_timer_ablauf_mit_ansagen(client, uhr):
    assert client.get("/api/status").json()["timer"] is None
    client.post("/api/timer/laden", json={"vorlage": "Schnelles Turnier"})
    client.post("/api/timer/start")
    status = client.get("/api/status").json()
    assert status["timer"]["nummer"] == 1
    assert status["ansagen"][-1]["text"] == "Level 1. Blinds 25 und 50."

    uhr.zeit += 12 * 60  # 12 Minuten spaeter
    status = client.get("/api/status", params={"nach_id": status["letzte_id"]}).json()
    assert [a["text"] for a in status["ansagen"]] == [
        "Noch eine Minute in diesem Level.", "Level 2. Blinds 50 und 100."]
    assert status["timer"]["big_blind"] == 100


def test_timer_steuerung(client, uhr):
    client.post("/api/timer/laden", json={"vorlage": "Langer Abend"})
    client.post("/api/timer/start")
    client.post("/api/timer/plus")
    assert client.get("/api/status").json()["timer"]["restzeit"] == 21 * 60
    client.post("/api/timer/naechstes")
    assert client.get("/api/status").json()["timer"]["nummer"] == 2
    antwort = client.post("/api/timer/quatsch")
    assert antwort.status_code == 400


def test_fehler_ohne_struktur(client):
    antwort = client.post("/api/timer/start")
    assert antwort.status_code == 400
    assert "Blindstruktur" in antwort.json()["detail"]


def test_eigene_vorlage(client):
    levels = [{"small_blind": 25, "big_blind": 50, "ante": 0, "minuten": 5},
              {"pause": True, "minuten": 5},
              {"small_blind": 50, "big_blind": 100, "ante": 0, "minuten": 5}]
    assert client.post("/api/vorlagen", json={"name": "Test", "levels": levels}).status_code == 200
    assert "Test" in client.get("/api/vorlagen").json()["namen"]
    assert client.get("/api/vorlagen/Test").json()["levels"] == levels
    kaputt = [{"small_blind": 30, "big_blind": 60, "minuten": 5}]
    assert client.post("/api/vorlagen", json={"name": "X", "levels": kaputt}).status_code == 400


def test_clock_laeuft_neben_timer(client, uhr):
    client.post("/api/timer/laden", json={"vorlage": "Schnelles Turnier"})
    client.post("/api/timer/start")
    client.post("/api/clock/start", json={"sekunden": 30})
    letzte = client.get("/api/status").json()["letzte_id"]
    uhr.zeit += 30
    status = client.get("/api/status", params={"nach_id": letzte}).json()
    arten = [(a["text"], a["art"]) for a in status["ansagen"]]
    assert arten == [("20", "sprache"), ("10", "sprache"), ("3", "sprache"),
                     ("2", "sprache"), ("1", "sprache"), ("", "piep")]
    assert status["timer"]["laeuft"]   # Turnier-Timer laeuft weiter
    assert not status["clock"]["laeuft"]


def test_turnier_kasse(client):
    t = client.post("/api/turnier", json={"buyin": "10", "auszahlung": [70, 30]}).json()["id"]
    for name in ["Anna", "Ben", "Clara"]:
        client.post(f"/api/turnier/{t}/buchen", json={"name": name, "art": "buyin"})
    u = client.post(f"/api/turnier/{t}/buchen", json={"name": "Ben", "art": "rebuy"}).json()
    assert u["preisgeld_cent"] == 4000 and u["eintraege"] == 4
    client.post(f"/api/turnier/{t}/aus", json={"name": "Clara"})
    client.post(f"/api/turnier/{t}/aus", json={"name": "Ben"})
    u = client.post(f"/api/turnier/{t}/abschliessen").json()
    assert u["auszahlung"][0] == {"platz": 1, "prozent": 70, "betrag_cent": 2800, "name": "Anna"}
    bilanz = {e["name"]: e["saldo_cent"] for e in client.get("/api/bilanz").json()["bilanz"]}
    assert bilanz == {"Anna": 1800, "Ben": -800, "Clara": -1000}


def test_cash_game(client):
    c = client.post("/api/cash", json={"name": "Samstag"}).json()["id"]
    client.post(f"/api/cash/{c}/buyin", json={"name": "Anna"})                  # Standard 10 Euro
    client.post(f"/api/cash/{c}/buyin", json={"name": "Ben", "betrag": "10,00"})
    client.post(f"/api/cash/{c}/cashout", json={"name": "Anna", "betrag": "12,50"})
    u = client.post(f"/api/cash/{c}/cashout", json={"name": "Ben", "betrag": "7"}).json()
    assert u["differenz_cent"] == -50 and not u["stimmt"]
    assert client.post("/api/chipwert", json={"10": 5, "100": 7}).json()["cent"] == 750
    u = client.post(f"/api/cash/{c}/cashout", json={"name": "Ben", "betrag": "7,50"}).json()
    assert u["stimmt"]
    assert client.get("/api/spieler").json()["namen"] == ["Anna", "Ben"]


def test_ungueltiger_betrag(client):
    c = client.post("/api/cash", json={}).json()["id"]
    antwort = client.post(f"/api/cash/{c}/buyin", json={"name": "Anna", "betrag": "viel"})
    assert antwort.status_code == 400
