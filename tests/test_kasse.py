"""Tests fuer poker/kasse.py. Alle Betraege in Cent."""

import pytest

from poker.kasse import (
    ausscheiden,
    ausscheiden_rueckgaengig,
    auszahlung_aendern,
    berechne_auszahlung,
    bilanz,
    buchung_loeschen,
    cash_abschliessen,
    cash_buyin,
    cash_out,
    cash_uebersicht,
    chips_wert_cent,
    euro_zu_cent,
    gemeinsamer_ausgleich,
    neues_cashgame,
    neues_turnier,
    turnier_abschliessen,
    turnier_buchen,
    turnier_uebersicht,
)
from poker.profile import oeffne_datenbank, spieler_id


@pytest.fixture
def db():
    verbindung = oeffne_datenbank(":memory:")
    yield verbindung
    verbindung.close()


# ---------- Betraege ----------


def test_euro_zu_cent():
    assert euro_zu_cent("10") == 1000
    assert euro_zu_cent("10,50") == 1050
    assert euro_zu_cent("0.1") == 10
    assert euro_zu_cent("12,35 €") == 1235
    for falsch in ["zehn", "1,234"]:
        with pytest.raises(ValueError):
            euro_zu_cent(falsch)


def test_chips_zaehlen():
    # 7 x 10 ct, 4 x 25 ct, 3 x 50 ct, 12 x 1 Euro = 0,70 + 1,00 + 1,50 + 12 = 15,20
    assert chips_wert_cent({10: 7, 25: 4, 50: 3, 100: 12}) == 1520
    with pytest.raises(ValueError):
        chips_wert_cent({20: 1})


# ---------- Preisgeld ----------


def test_auszahlung_60_30_10():
    assert berechne_auszahlung(10000, [60, 30, 10]) == [6000, 3000, 1000]


def test_auszahlung_rundet_auf_euro_rest_an_platz_1():
    # 7 x 15 Euro = 105 Euro: 63 / 31,50 / 10,50 -> 31 und 10, Rest an Platz 1
    betraege = berechne_auszahlung(10500, [60, 30, 10])
    assert betraege == [6400, 3100, 1000]
    assert sum(betraege) == 10500


def test_auszahlung_pruefen():
    for falsch in [[], [60, 30], [50, 50, 0], [70, 30.5]]:
        with pytest.raises(ValueError):
            berechne_auszahlung(10000, falsch)


# ---------- Turnier ----------


def turnier_mit_vier(db):
    """4 Spieler a 10 Euro, Auszahlung 70/30."""
    t = neues_turnier(db, 1000, [70, 30])
    for name in ["Anna", "Ben", "Clara", "Dave"]:
        turnier_buchen(db, t, name, "buyin")
    return t


def test_turnier_uebersicht(db):
    t = turnier_mit_vier(db)
    turnier_buchen(db, t, "Ben", "rebuy")
    turnier_buchen(db, t, "Anna", "addon")
    u = turnier_uebersicht(db, t)
    assert u["eintraege"] == 5        # 4 Buy-ins + 1 Rebuy
    assert u["addons"] == 1
    assert u["preisgeld_cent"] == 6000
    assert u["im_spiel"] == 4
    assert [p["betrag_cent"] for p in u["auszahlung"]] == [4200, 1800]


def test_eigene_betraege_fuer_rebuy_und_addon(db):
    t = neues_turnier(db, 1000, rebuy_cent=500, addon_cent=2000)
    turnier_buchen(db, t, "Anna", "buyin")
    turnier_buchen(db, t, "Anna", "rebuy")
    turnier_buchen(db, t, "Anna", "addon")
    assert turnier_uebersicht(db, t)["preisgeld_cent"] == 3500


def test_turnier_buchungsregeln(db):
    t = turnier_mit_vier(db)
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "Anna", "buyin")    # zweites Buy-in -> Rebuy nehmen
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "Erik", "rebuy")    # nicht angemeldet
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "Anna", "spende")   # unbekannte Art
    ausscheiden(db, t, "Dave")
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "Dave", "addon")    # ausgeschieden


def test_ausscheiden_und_plaetze(db):
    t = turnier_mit_vier(db)
    assert ausscheiden(db, t, "Dave") == 4
    assert ausscheiden(db, t, "Clara") == 3
    assert ausscheiden(db, t, "Ben") == 2
    u = turnier_uebersicht(db, t)
    plaetze = {s["name"]: s["platz"] for s in u["spieler"]}
    assert plaetze == {"Anna": 1, "Ben": 2, "Clara": 3, "Dave": 4}
    assert u["im_spiel"] == 0
    assert u["auszahlung"][0]["name"] == "Anna"
    with pytest.raises(ValueError):
        ausscheiden(db, t, "Ben")


def test_rebuy_holt_zurueck_und_plaetze_rutschen(db):
    t = turnier_mit_vier(db)
    ausscheiden(db, t, "Dave")   # 4.
    ausscheiden(db, t, "Clara")  # 3.
    turnier_buchen(db, t, "Dave", "rebuy")  # Dave ist wieder dabei
    u = turnier_uebersicht(db, t)
    plaetze = {s["name"]: s["platz"] for s in u["spieler"]}
    assert plaetze == {"Anna": None, "Ben": None, "Clara": 4, "Dave": None}
    assert ausscheiden(db, t, "Dave") == 3


def test_ausscheiden_rueckgaengig_nach_sieg(db):
    t = turnier_mit_vier(db)
    ausscheiden(db, t, "Dave")
    ausscheiden(db, t, "Clara")
    ausscheiden(db, t, "Ben")    # Anna automatisch Erste
    ausscheiden_rueckgaengig(db, t, "Ben")
    assert turnier_uebersicht(db, t)["im_spiel"] == 2
    with pytest.raises(ValueError):
        ausscheiden_rueckgaengig(db, t, "Anna")  # ist gar nicht ausgeschieden


def test_turnier_abschliessen(db):
    t = turnier_mit_vier(db)
    with pytest.raises(ValueError):
        turnier_abschliessen(db, t)  # noch kein Sieger
    for name in ["Dave", "Clara", "Ben"]:
        ausscheiden(db, t, name)
    u = turnier_abschliessen(db, t)
    ergebnis = {s["name"]: s["ausgezahlt_cent"] - s["eingezahlt_cent"] for s in u["spieler"]}
    assert ergebnis == {"Anna": 1800, "Ben": 200, "Clara": -1000, "Dave": -1000}
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "Erik", "buyin")  # abgeschlossen


def test_auszahlung_aendern(db):
    t = turnier_mit_vier(db)
    auszahlung_aendern(db, t, [100])
    assert turnier_uebersicht(db, t)["auszahlung"][0]["betrag_cent"] == 4000
    with pytest.raises(ValueError):
        auszahlung_aendern(db, t, [50, 40])


def test_spieler_mit_profil_verknuepft(db):
    t = turnier_mit_vier(db)
    # Dieselbe id wie im Spielerprofil (Tabelle spieler)
    zeile = db.execute("SELECT spieler_id FROM abend_spieler WHERE abend_id = ?",
                       (t,)).fetchall()
    assert spieler_id(db, "Anna") in [z[0] for z in zeile]


# ---------- Cash Game ----------


def test_cash_kontrollrechnung_stimmt(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna", zeitpunkt="2026-10-10T20:00:00")
    cash_buyin(db, c, "Ben")
    cash_buyin(db, c, "Ben", 500)        # Nachkauf 5 Euro
    cash_out(db, c, "Anna", 2150)
    cash_out(db, c, "Ben", 350)
    u = cash_uebersicht(db, c)
    assert u["summe_buyins_cent"] == 2500
    assert u["summe_cashouts_cent"] == 2500
    assert u["differenz_cent"] == 0 and u["stimmt"]
    ergebnis = {s["name"]: s["ergebnis_cent"] for s in u["spieler"]}
    assert ergebnis == {"Anna": 1150, "Ben": -1150}
    anna = u["spieler"][0]
    assert anna["buyins"][0]["zeitpunkt"] == "2026-10-10T20:00:00"


def test_cash_kontrollrechnung_differenz(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    cash_buyin(db, c, "Ben")
    cash_out(db, c, "Anna", 1200)
    cash_out(db, c, "Ben", 750)     # 50 Cent zu wenig gezaehlt
    u = cash_uebersicht(db, c)
    assert u["differenz_cent"] == -50
    assert not u["stimmt"]


def test_cash_out_fehlt(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    u = cash_uebersicht(db, c)
    assert u["offen"] == ["Anna"] and not u["stimmt"]
    with pytest.raises(ValueError):
        cash_abschliessen(db, c)
    with pytest.raises(ValueError):
        cash_out(db, c, "Zoe", 100)  # ohne Buy-in


def test_cash_out_ersetzen(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    cash_out(db, c, "Anna", 800)
    cash_out(db, c, "Anna", 1000)   # verzaehlt, korrigiert
    assert cash_uebersicht(db, c)["summe_cashouts_cent"] == 1000


def test_buchung_loeschen(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    cash_buyin(db, c, "Anna")   # versehentlich doppelt
    buchung = cash_uebersicht(db, c)["spieler"][0]["buyins"][1]["id"]
    buchung_loeschen(db, buchung)
    assert cash_uebersicht(db, c)["summe_buyins_cent"] == 1000


# ---------- Bilanz ----------


def test_bilanz_ueber_mehrere_abende(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    cash_buyin(db, c, "Ben")
    cash_out(db, c, "Anna", 1500)
    cash_out(db, c, "Ben", 500)
    cash_abschliessen(db, c)

    t = turnier_mit_vier(db)
    for name in ["Dave", "Clara", "Anna"]:
        ausscheiden(db, t, name)
    turnier_abschliessen(db, t)   # Ben gewinnt 28, Anna 12

    offen = neues_cashgame(db)    # noch nicht abgeschlossen -> zaehlt nicht
    cash_buyin(db, offen, "Anna", 5000)

    b = {e["name"]: e for e in bilanz(db)}
    assert b["Anna"]["saldo_cent"] == 500 + 200
    assert b["Ben"]["saldo_cent"] == -500 + 1800
    assert b["Anna"]["abende"] == 2
    assert bilanz(db)[0]["name"] == "Ben"   # bester Saldo zuerst
    assert {e["name"]: e["saldo_cent"] for e in bilanz(db, "cash")} == {"Anna": 500, "Ben": -500}


# ---------- Wer zahlt wem? ----------


def test_ausgleich_einfach():
    from poker.kasse import ausgleichszahlungen
    a = ausgleichszahlungen({"Anna": 1000, "Ben": -1000})
    assert a == {"zahlungen": [{"von": "Ben", "an": "Anna", "betrag_cent": 1000}], "rest_cent": 0}


def test_ausgleich_mehrere_spieler_wenige_zahlungen():
    from poker.kasse import ausgleichszahlungen
    ergebnisse = {"Anna": 1500, "Ben": -1000, "Clara": -800, "Dave": 500, "Erik": -200}
    a = ausgleichszahlungen(ergebnisse)
    assert a["rest_cent"] == 0
    assert len(a["zahlungen"]) <= len(ergebnisse) - 1
    # Nach allen Zahlungen steht jeder bei 0
    stand = dict(ergebnisse)
    for z in a["zahlungen"]:
        stand[z["von"]] += z["betrag_cent"]
        stand[z["an"]] -= z["betrag_cent"]
        assert z["betrag_cent"] > 0
    assert all(betrag == 0 for betrag in stand.values())


def test_ausgleich_alle_bei_null():
    from poker.kasse import ausgleichszahlungen
    assert ausgleichszahlungen({"Anna": 0, "Ben": 0}) == {"zahlungen": [], "rest_cent": 0}


def test_ausgleich_wenn_geld_fehlt():
    from poker.kasse import ausgleichszahlungen
    # Kontrollrechnung stimmt nicht: Gewinner +1000, Verlierer nur -950
    a = ausgleichszahlungen({"Anna": 1000, "Ben": -950})
    assert a["zahlungen"] == [{"von": "Ben", "an": "Anna", "betrag_cent": 950}]
    assert a["rest_cent"] == 50


def test_cash_uebersicht_mit_ausgleich(db):
    c = neues_cashgame(db)
    for name in ["Anna", "Ben", "Clara"]:
        cash_buyin(db, c, name)
    cash_out(db, c, "Anna", 2200)
    cash_out(db, c, "Ben", 0)
    assert cash_uebersicht(db, c)["ausgleich"] is None      # Clara fehlt noch
    cash_out(db, c, "Clara", 800)
    a = cash_uebersicht(db, c)["ausgleich"]
    assert a["zahlungen"] == [
        {"von": "Ben", "an": "Anna", "betrag_cent": 1000},
        {"von": "Clara", "an": "Anna", "betrag_cent": 200},
    ]


def test_turnier_ausgleich_nach_abschluss(db):
    t = turnier_mit_vier(db)                  # 4 x 10 Euro, Auszahlung 70/30
    turnier_buchen(db, t, "Dave", "rebuy")    # Dave zahlt 20 Euro insgesamt
    for name in ["Dave", "Clara", "Ben"]:
        ausscheiden(db, t, name)
    assert turnier_uebersicht(db, t)["ausgleich"] is None   # noch nicht abgeschlossen
    a = turnier_abschliessen(db, t)["ausgleich"]
    # Preisgeld 50: Anna 35 (+25), Ben 15 (+5), Clara -10, Dave -20
    assert a["rest_cent"] == 0
    assert a["zahlungen"] == [
        {"von": "Dave", "an": "Anna", "betrag_cent": 2000},
        {"von": "Clara", "an": "Anna", "betrag_cent": 500},
        {"von": "Clara", "an": "Ben", "betrag_cent": 500},
    ]


def test_cash_rebuy_mit_anderer_schreibweise(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Ben")
    cash_buyin(db, c, "ben ")           # Rebuy, nur anders geschrieben
    cash_buyin(db, c, "  BEN")
    u = cash_uebersicht(db, c)
    assert [s["name"] for s in u["spieler"]] == ["Ben"]
    assert u["spieler"][0]["summe_buyins_cent"] == 3000
    assert len(u["spieler"][0]["buyins"]) == 3


def test_cash_buyin_ohne_namen(db):
    c = neues_cashgame(db)
    with pytest.raises(ValueError):
        cash_buyin(db, c, "   ")


def test_turnier_rebuy_mit_anderer_schreibweise(db):
    t = neues_turnier(db, 1000, rebuy_cent=1000)
    turnier_buchen(db, t, "Anna", "buyin")
    turnier_buchen(db, t, "anna", "rebuy")
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "ANNA", "buyin")   # schon angemeldet
    u = turnier_uebersicht(db, t)
    assert u["rebuys"] == 1 and len(u["spieler"]) == 1


def test_gemeinsamer_ausgleich_turnier_und_cash(db):
    t = turnier_mit_vier(db)                  # 4 x 10 Euro, Auszahlung 70/30
    for name in ["Dave", "Clara", "Ben"]:
        ausscheiden(db, t, name)
    turnier_abschliessen(db, t)               # Anna +18, Ben +2, Clara -10, Dave -10
    c = neues_cashgame(db)
    for name in ["Anna", "Ben", "Clara"]:
        cash_buyin(db, c, name)
    cash_out(db, c, "Anna", 0)                # Anna -10
    cash_out(db, c, "Ben", 500)               # Ben -5
    cash_out(db, c, "Clara", 2500)            # Clara +15
    cash_abschliessen(db, c)

    g = gemeinsamer_ausgleich(db, [t, c])
    gesamt = {s["name"]: s["gesamt_cent"] for s in g["spieler"]}
    assert gesamt == {"Anna": 800, "Ben": -300, "Clara": 500, "Dave": -1000}
    ben = next(s for s in g["spieler"] if s["name"] == "Ben")
    assert ben["pro_abend"] == {t: 200, c: -500}
    assert g["ausgleich"]["rest_cent"] == 0
    # Insgesamt fliesst nur so viel, wie die Verlierer zusammen verloren haben
    assert sum(z["betrag_cent"] for z in g["ausgleich"]["zahlungen"]) == 1300
    assert len(g["ausgleich"]["zahlungen"]) <= 3
    assert [a["art"] for a in g["abende"]] == ["turnier", "cash"]


def test_gemeinsamer_ausgleich_nur_abgeschlossene(db):
    c = neues_cashgame(db)
    cash_buyin(db, c, "Anna")
    with pytest.raises(ValueError):
        gemeinsamer_ausgleich(db, [c])
    with pytest.raises(ValueError):
        gemeinsamer_ausgleich(db, [])
    with pytest.raises(ValueError):
        gemeinsamer_ausgleich(db, [999])


def test_spaeter_buyin_verschiebt_plaetze(db):
    t = neues_turnier(db, 1000, [50, 30, 20])
    for name in ["A", "B", "C", "D", "E"]:
        turnier_buchen(db, t, name, "buyin")
    ausscheiden(db, t, "E")                   # E wird 5.
    turnier_buchen(db, t, "F", "buyin")       # F kommt spaet -> E rutscht auf 6
    turnier_buchen(db, t, "G", "buyin")       # G auch -> E 7
    for name in ["D", "C", "G", "B", "F"]:
        ausscheiden(db, t, name)
    u = turnier_uebersicht(db, t)
    plaetze = {s["name"]: s["platz"] for s in u["spieler"]}
    assert plaetze == {"A": 1, "F": 2, "B": 3, "G": 4, "C": 5, "D": 6, "E": 7}
    assert [p["name"] for p in u["auszahlung"]] == ["A", "F", "B"]
    turnier_abschliessen(db, t)


def test_kein_buyin_nach_turnierende(db):
    t = neues_turnier(db, 1000, [100])
    for name in ["A", "B"]:
        turnier_buchen(db, t, name, "buyin")
    ausscheiden(db, t, "B")
    with pytest.raises(ValueError):
        turnier_buchen(db, t, "C", "buyin")


def test_abschliessen_prueft_plaetze(db):
    t = turnier_mit_vier(db)
    for name in ["Dave", "Clara", "Ben"]:
        ausscheiden(db, t, name)
    # Kaputte Daten wie aus einer alten Version: Platz 4 doppelt, 3 fehlt
    db.execute("UPDATE abend_spieler SET platz = 4 WHERE platz = 3 AND abend_id = ?", (t,))
    with pytest.raises(ValueError, match="doppelt"):
        turnier_abschliessen(db, t)
