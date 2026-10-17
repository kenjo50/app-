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


# ---------- Live-Abend (Haende mitschreiben) ----------


def abend_starten(client):
    antwort = client.post("/api/abend", json={
        "spieler": ["Anna", "Ben", "Clara"],
        "stacks": {"Anna": "10", "Ben": "10", "Clara": "10"},
        "small_blind": "0,10", "big_blind": "0,20"})
    assert antwort.status_code == 200
    return antwort.json()["abend"]


def test_abend_starten_und_hand_spielen(client):
    assert client.get("/api/abend").json()["abend"] is None
    abend = abend_starten(client)
    assert abend["stacks"]["Anna"] == 1000          # Euro -> Cent
    assert abend["phase"] == "keine_hand"

    hand = client.post("/api/abend/hand").json()["abend"]["hand"]
    assert hand["am_zug"] == "Clara"
    assert hand["erlaubt"] == ["fold", "call", "raise"]
    assert hand["raise"]["mindest"] == 40

    client.post("/api/abend/aktion", json={"aktion": "raise", "betrag": "0,60"})
    client.post("/api/abend/aktion", json={"aktion": "fold"})
    a = client.post("/api/abend/aktion", json={"aktion": "fold"}).json()["abend"]
    assert a["phase"] == "gewonnen"
    antwort = client.post("/api/abend/gewonnen").json()
    assert antwort["ergebnis"] == {"Anna": -10, "Ben": -20, "Clara": 30}
    assert antwort["abend"]["spieler"] == ["Ben", "Clara", "Anna"]   # Button wandert


def test_rueckgaengig_ueber_server(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    client.post("/api/abend/aktion", json={"aktion": "call"})
    hand = client.post("/api/abend/rueckgaengig").json()["abend"]["hand"]
    assert hand["am_zug"] == "Clara"
    assert hand["kann_rueckgaengig"] is False


def test_karten_und_showdown_ueber_server(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    for aktion in ["call", "call", "check"]:
        client.post("/api/abend/aktion", json={"aktion": aktion})
    for karten in ["Ks 9h 4d", "2c", "7s"]:
        a = client.post("/api/abend/karten", json={"karten": karten}).json()["abend"]
        for i in range(3):
            a = client.post("/api/abend/aktion", json={"aktion": "check"}).json()["abend"]
    assert a["phase"] == "showdown"
    gezeigte = {"Anna": "Kh Qc", "Ben": "9s 9c", "Clara": ""}
    vorschau = client.post("/api/abend/showdown/vorschau", json={"gezeigte": gezeigte}).json()
    assert vorschau["pots"][0]["gewinner"] == ["Ben"]
    assert vorschau["handarten"]["Ben"] == "Drilling"
    antwort = client.post("/api/abend/showdown", json={"gezeigte": gezeigte}).json()
    assert antwort["ergebnis"]["Ben"] == 40


def test_falsche_eingaben_ueber_server(client):
    assert client.post("/api/abend/hand").status_code == 400          # kein Abend
    abend_starten(client)
    client.post("/api/abend/hand")
    antwort = client.post("/api/abend/aktion", json={"aktion": "check"})
    assert antwort.status_code == 400 and "checken" in antwort.json()["detail"]
    assert client.post("/api/abend/karten", json={"karten": "Ks"}).status_code == 400
    assert client.post("/api/abend/rueckgaengig").status_code == 400  # nichts zu tun
    # Waehrend der Hand kein neuer Abend und kein Nachkauf
    assert client.post("/api/abend/nachkauf",
                       json={"name": "Anna", "betrag": "5"}).status_code == 400


def test_abgebrochene_hand_ueber_server(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    client.post("/api/abend/aktion", json={"aktion": "raise", "betrag": "0,60"})
    a = client.post("/api/abend/abbrechen").json()["abend"]
    assert a["phase"] == "keine_hand"
    assert a["stacks"]["Clara"] == 1000
    assert client.get("/api/abend/statistik/Clara").json()["haende"] == 0


def test_zwischen_den_haenden_ueber_server(client):
    abend_starten(client)
    a = client.post("/api/abend/nachkauf", json={"name": "Anna", "betrag": "5"}).json()["abend"]
    assert a["stacks"]["Anna"] == 1500
    a = client.post("/api/abend/aussetzen", json={"name": "Ben", "aussetzen": True}).json()["abend"]
    assert a["naechste_hand"] == ["Anna", "Clara"]
    a = client.post("/api/abend/dazu", json={"name": "Dave", "stack": "10"}).json()["abend"]
    assert "Dave" in a["spieler"]


def test_abend_uebersteht_neustart(tmp_path, uhr):
    pfad = str(tmp_path / "neustart.db")
    erster = TestClient(erstelle_app(pfad, uhr))
    abend_starten(erster)
    erster.post("/api/abend/hand")
    # "Neustart": neue App mit derselben Datenbank
    zweiter = TestClient(erstelle_app(pfad, uhr))
    a = zweiter.get("/api/abend").json()["abend"]
    assert a["spieler"] == ["Anna", "Ben", "Clara"]
    assert a["phase"] == "keine_hand"    # die laufende Hand wurde verworfen
    zweiter.delete("/api/abend")
    assert zweiter.get("/api/abend").json()["abend"] is None


def test_statistik_mit_typ(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    client.post("/api/abend/aktion", json={"aktion": "fold"})
    client.post("/api/abend/aktion", json={"aktion": "fold"})
    client.post("/api/abend/gewonnen")
    s = client.get("/api/abend/statistik/Clara").json()
    assert s["haende"] == 1 and s["typ"] == "unbekannt"
    assert client.get("/api/abend/statistik/Niemand").status_code == 400


# ---------- KI-Berater ----------


def test_berater_ueber_server(client):
    abend_starten(client)
    a = client.post("/api/abend/held", json={"name": "Clara"}).json()["abend"]
    assert a["held"] == "Clara"
    client.post("/api/abend/hand")
    assert client.get("/api/abend/empfehlung").status_code == 400     # Karten fehlen
    hand = client.post("/api/abend/held/karten", json={"karten": "As Ah"}).json()["abend"]["hand"]
    assert hand["held_dran"] is True
    assert hand["held_karten"] == [[14, "Pik"], [14, "Herz"]]
    e = client.get("/api/abend/empfehlung").json()
    assert e["aktion"] == "raise" and e["betrag"] % 10 == 0
    assert len(e["gruende"]) >= 2
    # Uebernehmen = ganz normal als Aktion eintragen
    hand = client.post("/api/abend/aktion", json={
        "aktion": "raise", "betrag": f"{e['betrag'] / 100:.2f}"}).json()["abend"]["hand"]
    assert hand["am_zug"] == "Anna" and hand["held_dran"] is False
    assert client.get("/api/abend/empfehlung").status_code == 400     # Clara nicht dran


def test_berater_fehler_ueber_server(client):
    abend_starten(client)
    assert client.post("/api/abend/held", json={"name": "Zoe"}).status_code == 400
    client.post("/api/abend/hand")
    assert client.post("/api/abend/held/karten", json={"karten": "As"}).status_code == 400


# ---------- Entwicklungsmodus ----------


def test_entwicklungsmodus_nur_wenn_eingeschaltet(tmp_path, uhr):
    normal = TestClient(erstelle_app(str(tmp_path / "a.db"), uhr))
    assert normal.get("/api/entwicklung/stand").status_code == 404
    entwicklung = TestClient(erstelle_app(str(tmp_path / "b.db"), uhr, entwicklung=True))
    stand = entwicklung.get("/api/entwicklung/stand").json()
    assert stand["start"] > 0 and stand["web"] > 0


# ---------- Wartung: Sicherung und Aufraeumen ----------


def test_sicherung_beim_start_und_manuell(tmp_path, uhr):
    pfad = tmp_path / "heim.db"
    erster = TestClient(erstelle_app(str(pfad), uhr))     # legt die Datei erst an
    erster.post("/api/cash", json={"name": "x"})
    zweiter = TestClient(erstelle_app(str(pfad), uhr))    # Start mit vorhandener Datei
    assert len(zweiter.get("/api/wartung").json()["sicherungen"]) == 1
    assert zweiter.post("/api/wartung/sicherung").json()["name"].startswith("heim_")


def test_testspieler_aufraeumen(client):
    c = client.post("/api/cash", json={}).json()["id"]
    client.post(f"/api/cash/{c}/buyin", json={"name": "Test"})
    vorschau = client.get("/api/wartung/spieler/Test").json()
    assert vorschau["abende"][0]["id"] == c
    antwort = client.delete("/api/wartung/spieler/Test")
    assert antwort.status_code == 400 and "Abend" in antwort.json()["detail"]
    client.delete(f"/api/wartung/abend/{c}")
    w = client.delete("/api/wartung/spieler/Test").json()["wartung"]
    assert [s["name"] for s in w["spieler"]] == []
    assert w["abende"] == []


def test_abgebrochene_haende_ueber_server(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    client.post("/api/abend/abbrechen")
    client.post("/api/abend/hand")                    # laeuft gerade
    assert client.get("/api/wartung").json()["abgebrochene"] == 1
    antwort = client.delete("/api/wartung/abgebrochene").json()
    assert antwort["geloescht_haende"] == 1
    # Die laufende Hand ist noch spielbar
    assert client.post("/api/abend/aktion", json={"aktion": "fold"}).status_code == 200


def test_live_spieler_nicht_loeschen(client):
    abend_starten(client)
    assert client.delete("/api/wartung/spieler/Anna").status_code == 400


def test_statistik_mit_showdown_werten(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    for aktion in ["fold", "fold"]:
        client.post("/api/abend/aktion", json={"aktion": aktion})
    client.post("/api/abend/gewonnen")
    s = client.get("/api/abend/statistik/Clara").json()
    assert s["wtsd"] is None and s["wsd"] is None and s["bluff_anteil"] is None
    assert s["river_bets"] == 0


# ---------- Analyse ----------


def test_analyse_ueber_server(client):
    abend_starten(client)
    client.post("/api/abend/hand")
    client.post("/api/abend/aktion", json={"aktion": "fold"})
    client.post("/api/abend/aktion", json={"aktion": "fold"})
    client.post("/api/abend/gewonnen")
    a = client.get("/api/analyse/Clara").json()
    assert len(a["kurve"]) == 1 and len(a["abende"]) == 1
    assert {g["name"] for g in a["gegner"]} == {"Anna", "Ben"}
    assert client.get("/api/analyse/Niemand").status_code == 400


# ---------- Lerntisch ----------


def test_lerntisch_ueber_server(client, tmp_path):
    abend_starten(client)   # legt Anna, Ben, Clara in der Heimrunde-Datenbank an
    assert client.get("/api/lerntisch").json()["spiel"] is None
    antwort = client.post("/api/lerntisch", json={
        "held": "Oliver", "gegner": [{"spieler": "Ben"}, {"typ": "maniac"}]})
    assert antwort.status_code == 200
    spiel = antwort.json()["spiel"]
    assert spiel["held"] == "Oliver" and spiel["hand"] is not None
    assert list(spiel["hand"]["karten"]) == ["Oliver"]

    # Bots Schritt fuer Schritt, du checkst/callst, bis die Hand vorbei ist
    for _ in range(200):
        if spiel["phase"] == "ende":
            break
        if spiel["phase"] == "held":
            aktion = "check" if "check" in spiel["hand"]["erlaubt"] else "call"
            antwort = client.post("/api/lerntisch/aktion", json={"aktion": aktion}).json()
            assert antwort["tipp"]["du"] in ["check", "call"]
        else:
            antwort = client.post("/api/lerntisch/schritt").json()
        spiel = antwort["spiel"]
    assert spiel["phase"] == "ende"
    assert spiel["hand"]["ergebnis"]["gewinner"]

    spiel = client.post("/api/lerntisch/hand").json()["spiel"]
    assert spiel["phase"] in ["held", "bots"]
    ende = client.post("/api/lerntisch/ende").json()
    assert ende["zusammenfassung"]["haende"] == 1
    assert client.get("/api/lerntisch").json()["spiel"] is None
    # Eigene Datenbank neben der echten
    assert any(p.name.endswith("_lerntisch.db") for p in tmp_path.iterdir())


def test_lerntisch_fehler(client):
    assert client.post("/api/lerntisch", json={"held": "Oliver", "gegner": []}).status_code == 400
    assert client.post("/api/lerntisch/schritt").status_code == 400
    assert client.post("/api/lerntisch/ende").status_code == 400
