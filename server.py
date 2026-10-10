"""Web-Server fuer das iPhone: Turnier-Timer, Clock und Kasse.

Start:  python server.py                 (Datenbank heimrunde.db, Port 8000)
        python server.py test.db         (andere Datenbank)
Dann auf dem iPhone im selben WLAN: http://<IP-des-PCs>:8000

Der Server ist nur die Bruecke zwischen Web-App und Python-Kern:
- Timer- und Clock-Zustand liegen im Arbeitsspeicher (ein Turnier zur Zeit).
- Kasse und Blind-Vorlagen liegen in der SQLite-Datenbank.
- Ansagen aus dem Kern bekommen eine laufende Nummer (id). Die Web-App fragt
  regelmaessig "alles nach id X" ab und liest neue Ansagen vor.
"""

import socket
import sys
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from poker import clock as clockmodul
from poker import kasse, turnier
from poker.profile import oeffne_datenbank, spieler_namen

STANDARD_DATENBANK = "heimrunde.db"
WEB_ORDNER = Path(__file__).parent / "web"
MAX_ANSAGEN = 200  # so viele Ansagen merkt sich der Server


def erstelle_app(datenbank_pfad, uhr=time.time):
    """Baut die App. `uhr` liefert die aktuelle Zeit (in Tests austauschbar)."""
    app = FastAPI(title="Poker-Heimrunde")
    sperre = threading.Lock()  # Anfragen kommen gleichzeitig, der Zustand nur einmal
    tisch = {
        "timer": None,
        "vorlage": None,
        "clock": clockmodul.neue_clock(),
        "ansagen": [],
        "naechste_id": 1,
    }

    def datenbank():
        return oeffne_datenbank(datenbank_pfad)

    def merke(ansagen):
        """Gibt Ansagen aus dem Kern eine Nummer und merkt sie sich."""
        for ansage in ansagen:
            eintrag = dict(ansage)
            eintrag["id"] = tisch["naechste_id"]
            tisch["naechste_id"] += 1
            tisch["ansagen"].append(eintrag)
        del tisch["ansagen"][:-MAX_ANSAGEN]

    def aktualisiere(jetzt):
        if tisch["timer"] is not None:
            merke(turnier.aktualisiere(tisch["timer"], jetzt))
        merke(clockmodul.aktualisiere_clock(tisch["clock"], jetzt))

    @app.exception_handler(ValueError)
    def fehler_anzeigen(request: Request, fehler: ValueError):
        # Fehler aus dem Kern (z. B. "Es gibt kein weiteres Level") an die App melden
        return JSONResponse(status_code=400, content={"detail": str(fehler)})

    # ---------------- Status ----------------

    @app.get("/api/status")
    def status(nach_id: int = 0):
        with sperre:
            jetzt = uhr()
            aktualisiere(jetzt)
            neue = []
            for ansage in tisch["ansagen"]:
                if ansage["id"] > nach_id:
                    neue.append(ansage)
            timer_daten = None
            if tisch["timer"] is not None:
                timer_daten = turnier.anzeige(tisch["timer"], jetzt)
            return {
                "jetzt": jetzt,
                "timer": timer_daten,
                "vorlage": tisch["vorlage"],
                "struktur": None if tisch["timer"] is None else tisch["timer"]["struktur"],
                "clock": clockmodul.clock_anzeige(tisch["clock"], jetzt),
                "ansagen": neue,
                "letzte_id": tisch["naechste_id"] - 1,
            }

    # ---------------- Turnier-Timer ----------------

    @app.post("/api/timer/laden")
    def timer_laden(daten: dict = Body(...)):
        """Laedt eine Vorlage ({"vorlage": name}) oder eine Struktur ({"levels": [...]})."""
        with sperre:
            if "levels" in daten:
                struktur = daten["levels"]
                name = daten.get("name") or "Eigene Struktur"
            else:
                db = datenbank()
                try:
                    struktur = turnier.vorlage_laden(db, daten["vorlage"])
                finally:
                    db.close()
                name = daten["vorlage"]
            tisch["timer"] = turnier.neuer_timer(struktur)
            tisch["vorlage"] = name
            return {"ok": True}

    @app.post("/api/timer/{aktion}")
    def timer_steuern(aktion: str):
        with sperre:
            timer = tisch["timer"]
            if timer is None:
                raise ValueError("Zuerst eine Blindstruktur laden")
            jetzt = uhr()
            aktualisiere(jetzt)
            if aktion == "start":
                merke(turnier.starte(timer, jetzt))
            elif aktion == "pause":
                merke(turnier.pausiere(timer, jetzt))
            elif aktion == "naechstes":
                merke(turnier.naechstes_level(timer, jetzt))
            elif aktion == "vorheriges":
                merke(turnier.vorheriges_level(timer, jetzt))
            elif aktion == "plus":
                merke(turnier.zeit_anpassen(timer, jetzt, 60))
            elif aktion == "minus":
                merke(turnier.zeit_anpassen(timer, jetzt, -60))
            else:
                raise ValueError(f"Unbekannte Aktion: {aktion}")
            return {"ok": True}

    @app.get("/api/vorlagen")
    def vorlagen():
        db = datenbank()
        try:
            return {"namen": turnier.vorlagen_namen(db),
                    "standard": list(turnier.STANDARD_VORLAGEN.keys())}
        finally:
            db.close()

    @app.get("/api/vorlagen/{name}")
    def vorlage(name: str):
        db = datenbank()
        try:
            return {"name": name, "levels": turnier.vorlage_laden(db, name)}
        finally:
            db.close()

    @app.post("/api/vorlagen")
    def vorlage_speichern(daten: dict = Body(...)):
        db = datenbank()
        try:
            turnier.vorlage_speichern(db, daten.get("name", ""), daten.get("levels", []))
            return {"ok": True}
        finally:
            db.close()

    @app.delete("/api/vorlagen/{name}")
    def vorlage_loeschen(name: str):
        db = datenbank()
        try:
            turnier.vorlage_loeschen(db, name)
            return {"ok": True}
        finally:
            db.close()

    # ---------------- Clock ----------------

    @app.post("/api/clock/start")
    def clock_start(daten: dict = Body(default={})):
        with sperre:
            sekunden = daten.get("sekunden", clockmodul.STANDARD_SEKUNDEN)
            merke(clockmodul.starte_clock(tisch["clock"], uhr(), sekunden,
                                          daten.get("spieler")))
            return {"ok": True}

    @app.post("/api/clock/stop")
    def clock_stop():
        with sperre:
            clockmodul.stoppe_clock(tisch["clock"])
            return {"ok": True}

    # ---------------- Kasse ----------------

    def mit_db(funktion, *argumente):
        """Hilfsfunktion: Datenbank oeffnen, Funktion aufrufen, schliessen."""
        db = datenbank()
        try:
            return funktion(db, *argumente)
        finally:
            db.close()

    def cent(daten, schluessel, standard=None):
        """Liest einen Euro-Betrag aus der Anfrage und macht Cent daraus."""
        wert = daten.get(schluessel)
        if wert is None or str(wert).strip() == "":
            return standard
        return kasse.euro_zu_cent(wert)

    @app.get("/api/spieler")
    def spieler():
        return {"namen": mit_db(spieler_namen)}

    @app.get("/api/abende")
    def abende():
        return {"abende": mit_db(kasse.abende_liste)}

    @app.get("/api/bilanz")
    def bilanz(art: str = ""):
        return {"bilanz": mit_db(kasse.bilanz, art or None)}

    @app.post("/api/chipwert")
    def chipwert(daten: dict = Body(...)):
        """{"10": 3, "100": 5} -> Wert in Cent (Cash-Game-Chips zaehlen)."""
        anzahlen = {}
        for wert, anzahl in daten.items():
            anzahlen[int(wert)] = int(anzahl or 0)
        return {"cent": kasse.chips_wert_cent(anzahlen)}

    @app.delete("/api/buchung/{buchung_id}")
    def buchung_loeschen(buchung_id: int):
        mit_db(kasse.buchung_loeschen, buchung_id)
        return {"ok": True}

    @app.post("/api/turnier")
    def turnier_neu(daten: dict = Body(...)):
        db = datenbank()
        try:
            abend_id = kasse.neues_turnier(
                db, cent(daten, "buyin"), daten.get("auszahlung"),
                cent(daten, "rebuy"), cent(daten, "addon"), daten.get("name", ""),
            )
            return {"id": abend_id}
        finally:
            db.close()

    @app.get("/api/turnier/{abend_id}")
    def turnier_zeigen(abend_id: int):
        return mit_db(kasse.turnier_uebersicht, abend_id)

    @app.post("/api/turnier/{abend_id}/buchen")
    def turnier_buchen(abend_id: int, daten: dict = Body(...)):
        mit_db(kasse.turnier_buchen, abend_id, daten.get("name", "").strip(), daten.get("art"))
        return mit_db(kasse.turnier_uebersicht, abend_id)

    @app.post("/api/turnier/{abend_id}/aus")
    def turnier_aus(abend_id: int, daten: dict = Body(...)):
        mit_db(kasse.ausscheiden, abend_id, daten.get("name"))
        return mit_db(kasse.turnier_uebersicht, abend_id)

    @app.post("/api/turnier/{abend_id}/zurueck")
    def turnier_zurueck(abend_id: int, daten: dict = Body(...)):
        mit_db(kasse.ausscheiden_rueckgaengig, abend_id, daten.get("name"))
        return mit_db(kasse.turnier_uebersicht, abend_id)

    @app.post("/api/turnier/{abend_id}/auszahlung")
    def turnier_auszahlung(abend_id: int, daten: dict = Body(...)):
        mit_db(kasse.auszahlung_aendern, abend_id, daten.get("auszahlung", []))
        return mit_db(kasse.turnier_uebersicht, abend_id)

    @app.post("/api/turnier/{abend_id}/abschliessen")
    def turnier_abschliessen(abend_id: int):
        return mit_db(kasse.turnier_abschliessen, abend_id)

    @app.post("/api/cash")
    def cash_neu(daten: dict = Body(default={})):
        return {"id": mit_db(kasse.neues_cashgame, daten.get("name", ""))}

    @app.get("/api/cash/{abend_id}")
    def cash_zeigen(abend_id: int):
        return mit_db(kasse.cash_uebersicht, abend_id)

    @app.post("/api/cash/{abend_id}/buyin")
    def cash_buyin(abend_id: int, daten: dict = Body(...)):
        betrag = cent(daten, "betrag", kasse.CASH_BUYIN_CENT)
        mit_db(kasse.cash_buyin, abend_id, daten.get("name", "").strip(), betrag)
        return mit_db(kasse.cash_uebersicht, abend_id)

    @app.post("/api/cash/{abend_id}/cashout")
    def cash_cashout(abend_id: int, daten: dict = Body(...)):
        mit_db(kasse.cash_out, abend_id, daten.get("name"), cent(daten, "betrag"))
        return mit_db(kasse.cash_uebersicht, abend_id)

    @app.post("/api/cash/{abend_id}/abschliessen")
    def cash_abschliessen(abend_id: int):
        return mit_db(kasse.cash_abschliessen, abend_id)

    # Die Web-App selbst (index.html, app.js, ...) - muss als Letztes kommen
    app.mount("/", StaticFiles(directory=WEB_ORDNER, html=True), name="web")
    return app


def eigene_ip():
    """IP-Adresse dieses PCs im Heim-WLAN (fuer die Anzeige beim Start)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # es wird nichts gesendet, nur die Route bestimmt
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn

    pfad = sys.argv[1] if len(sys.argv) > 1 else STANDARD_DATENBANK
    print(f"Datenbank: {pfad}")
    print(f"Auf dem iPhone oeffnen: http://{eigene_ip()}:8000")
    uvicorn.run(erstelle_app(pfad), host="0.0.0.0", port=8000, log_level="warning")
