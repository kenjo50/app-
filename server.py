"""Web-Server fuer das iPhone: Turnier-Timer, Clock und Kasse.

Start:  python server.py                 (Datenbank heimrunde.db, Port 8000)
        python server.py test.db         (andere Datenbank)
        python server.py test.db --entwicklung
                                         Entwicklungsmodus: Server startet bei
                                         geaenderten .py-Dateien neu, die Seite im
                                         Browser laedt bei Aenderungen selbst neu
Dann auf dem iPhone im selben WLAN: http://<IP-des-PCs>:8000

Der Server ist nur die Bruecke zwischen Web-App und Python-Kern:
- Timer- und Clock-Zustand liegen im Arbeitsspeicher (ein Turnier zur Zeit).
- Der Live-Abend (Haende mitschreiben, poker/tisch.py) liegt im Arbeitsspeicher
  und zusaetzlich in der Datenbank, damit er einen Neustart uebersteht.
  Betraege kommen von der App in Euro und werden hier in Cent umgerechnet.
- Kasse und Blind-Vorlagen liegen in der SQLite-Datenbank.
- Ansagen aus dem Kern bekommen eine laufende Nummer (id). Die Web-App fragt
  regelmaessig "alles nach id X" ab und liest neue Ansagen vor.
"""

import os
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
from poker import analyse as analysemodul
from poker import berater
from poker import tisch as tischmodul
from poker import wartung
from poker.deck import lies_karten
from poker.profile import anzahl_abgebrochene, oeffne_datenbank, spieler_namen

STANDARD_DATENBANK = "heimrunde.db"
PROJEKT_ORDNER = Path(__file__).parent
WEB_ORDNER = PROJEKT_ORDNER / "web"
START_ZEIT = time.time()  # aendert sich bei jedem (Neu-)Start des Servers
MAX_ANSAGEN = 200  # so viele Ansagen merkt sich der Server


def erstelle_app(datenbank_pfad, uhr=time.time, entwicklung=False):
    """Baut die App. `uhr` liefert die aktuelle Zeit (in Tests austauschbar).

    entwicklung: zusaetzlicher Endpunkt /api/entwicklung/stand, ueber den die
    Web-App merkt, dass sich Dateien geaendert haben, und sich neu laedt.
    """
    app = FastAPI(title="Poker-Heimrunde")
    sperre = threading.Lock()  # Anfragen kommen gleichzeitig, der Zustand nur einmal
    tisch = {
        "timer": None,
        "vorlage": None,
        "clock": clockmodul.neue_clock(),
        "ansagen": [],
        "naechste_id": 1,
        "abend": None,
    }

    def datenbank():
        return oeffne_datenbank(datenbank_pfad)

    # Bei jedem Start eine Sicherung der Datenbank anlegen (die letzten 30 bleiben)
    wartung.sicherung_anlegen(datenbank_pfad)

    # Einen gespeicherten Abend nach einem Neustart wieder aufnehmen
    db = datenbank()
    tisch["abend"] = tischmodul.lade_abend(db)
    db.close()

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

    # ---------------- Live-Abend (Haende mitschreiben) ----------------

    def abend():
        if tisch["abend"] is None:
            raise ValueError("Es laeuft kein Abend - bitte zuerst einen Abend starten")
        return tisch["abend"]

    def live_antwort(**zusatz):
        """Aktueller Stand fuer die App, optional mit Zusatzdaten (z. B. Ergebnis)."""
        antwort = {"abend": None if tisch["abend"] is None
                   else tischmodul.anzeige(tisch["abend"])}
        antwort.update(zusatz)
        return antwort

    def live(funktion, *argumente):
        """Kern-Funktion mit Datenbank aufrufen; nur eine Anfrage gleichzeitig."""
        with sperre:
            db = datenbank()
            try:
                return funktion(db, *argumente)
            finally:
                db.close()

    def gezeigte_karten(daten):
        """{"Ben": "Kh Qc", "Clara": ""} -> {"Ben": [(13, "Herz"), (12, "Kreuz")]}"""
        gezeigte = {}
        for name, text in (daten.get("gezeigte") or {}).items():
            if text and text.strip():
                gezeigte[name] = lies_karten(text)
        return gezeigte

    @app.get("/api/abend")
    def abend_zeigen():
        return live_antwort()

    @app.post("/api/abend")
    def abend_starten(daten: dict = Body(...)):
        """{"spieler": [...], "stacks": {name: "10"}, "small_blind": "0,10", "big_blind": "0,20"}"""
        stacks = {}
        for name, betrag in (daten.get("stacks") or {}).items():
            stacks[name] = kasse.euro_zu_cent(betrag)
        if tisch["abend"] is not None and tisch["abend"]["hand"] is not None:
            raise ValueError("Es laeuft noch eine Hand - bitte erst abschliessen oder abbrechen")
        tisch["abend"] = live(tischmodul.neuer_abend, daten.get("spieler", []), stacks,
                              kasse.euro_zu_cent(daten.get("small_blind", "0")),
                              kasse.euro_zu_cent(daten.get("big_blind", "0")))
        return live_antwort()

    @app.delete("/api/abend")
    def abend_beenden():
        live(tischmodul.beende_abend)
        tisch["abend"] = None
        return live_antwort()

    @app.post("/api/abend/hand")
    def hand_starten():
        live(tischmodul.starte_naechste_hand, abend())
        return live_antwort()

    @app.post("/api/abend/aktion")
    def hand_aktion(daten: dict = Body(...)):
        """{"aktion": "raise", "betrag": "1,50"}; Betrag nur bei raise."""
        betrag = daten.get("betrag")
        betrag = None if betrag in [None, ""] else kasse.euro_zu_cent(betrag)
        live(tischmodul.aktion, abend(), daten.get("aktion"), betrag)
        return live_antwort()

    @app.post("/api/abend/karten")
    def hand_karten(daten: dict = Body(...)):
        """{"karten": "Ks 9h 4d"}"""
        live(tischmodul.board_karten, abend(), lies_karten(daten.get("karten", "")))
        return live_antwort()

    @app.post("/api/abend/rueckgaengig")
    def hand_rueckgaengig():
        live(tischmodul.rueckgaengig, abend())
        return live_antwort()

    @app.post("/api/abend/abbrechen")
    def hand_abbrechen():
        with sperre:
            tischmodul.hand_abbrechen(abend())
        return live_antwort()

    @app.post("/api/abend/gewonnen")
    def hand_gewonnen():
        ergebnis = live(tischmodul.abrechnen_ohne_showdown, abend())
        return live_antwort(ergebnis=ergebnis)

    @app.post("/api/abend/showdown/vorschau")
    def showdown_vorschau(daten: dict = Body(...)):
        """{"gezeigte": {"Ben": "Kh Qc", "Clara": ""}} -> wer gewinnt welchen Pot"""
        with sperre:
            return tischmodul.showdown_vorschau(abend(), gezeigte_karten(daten))

    @app.post("/api/abend/showdown")
    def showdown_abrechnen(daten: dict = Body(...)):
        """{"gezeigte": {...}, "gewinner_von_hand": {"0": ["Anna"]}}"""
        ergebnis = live(tischmodul.showdown_abrechnen, abend(), gezeigte_karten(daten),
                        daten.get("gewinner_von_hand"))
        return live_antwort(ergebnis=ergebnis)

    @app.post("/api/abend/nachkauf")
    def abend_nachkauf(daten: dict = Body(...)):
        live(tischmodul.nachkauf, abend(), daten.get("name"),
             kasse.euro_zu_cent(daten.get("betrag", "0")))
        return live_antwort()

    @app.post("/api/abend/aussetzen")
    def abend_aussetzen(daten: dict = Body(...)):
        """{"name": "Ben", "aussetzen": true}"""
        live(tischmodul.setze_aus, abend(), daten.get("name"), bool(daten.get("aussetzen", True)))
        return live_antwort()

    @app.post("/api/abend/dazu")
    def abend_dazu(daten: dict = Body(...)):
        live(tischmodul.spieler_dazu, abend(), daten.get("name", ""),
             kasse.euro_zu_cent(daten.get("stack", "0")))
        return live_antwort()

    @app.post("/api/abend/held")
    def abend_held(daten: dict = Body(...)):
        """{"name": "Ben"} oder {"name": null}: fuer wen die KI Empfehlungen gibt"""
        live(tischmodul.setze_held, abend(), daten.get("name"))
        return live_antwort()

    @app.post("/api/abend/held/karten")
    def abend_held_karten(daten: dict = Body(...)):
        """{"karten": "As Kd"}"""
        with sperre:
            tischmodul.setze_held_karten(abend(), lies_karten(daten.get("karten", "")))
        return live_antwort()

    @app.get("/api/abend/empfehlung")
    def abend_empfehlung():
        return live(berater.empfehlung, abend())

    @app.get("/api/abend/statistik/{name}")
    def abend_statistik(name: str):
        db = datenbank()
        try:
            return tischmodul.spieler_statistik(db, name)
        finally:
            db.close()

    # ---------------- Wartung: Sicherung und Aufraeumen ----------------

    def laufende_hand_id():
        if tisch["abend"] is None or tisch["abend"]["hand"] is None:
            return None
        return tisch["abend"]["hand"]["zustand"]["hand_id"]

    def wartung_uebersicht(db):
        abgebrochene = anzahl_abgebrochene(db) - (1 if laufende_hand_id() else 0)
        return {
            "sicherungen": wartung.sicherungen_liste(datenbank_pfad),
            "spieler": wartung.spieler_uebersicht(db),
            "abende": kasse.abende_liste(db),
            "abgebrochene": abgebrochene,
        }

    # ---------------- Analyse ----------------

    @app.get("/api/analyse/{name}")
    def analyse_zeigen(name: str):
        return mit_db(analysemodul.analyse, name)

    @app.get("/api/wartung")
    def wartung_zeigen():
        return mit_db(wartung_uebersicht)

    @app.post("/api/wartung/sicherung")
    def wartung_sichern():
        kopie = wartung.sicherung_anlegen(datenbank_pfad)
        return {"name": None if kopie is None else kopie.name}

    @app.get("/api/wartung/spieler/{name}")
    def wartung_spieler_vorschau(name: str):
        return mit_db(wartung.spieler_loeschvorschau, name)

    @app.delete("/api/wartung/spieler/{name}")
    def wartung_spieler_loeschen(name: str):
        live_spieler = [] if tisch["abend"] is None else tisch["abend"]["spieler"]
        with sperre:
            wartung.sicherung_anlegen(datenbank_pfad)   # vor dem Loeschen immer sichern
            haende = mit_db(wartung.spieler_loeschen, name, live_spieler)
        return {"geloescht_haende": haende, "wartung": mit_db(wartung_uebersicht)}

    @app.delete("/api/wartung/abend/{abend_id}")
    def wartung_abend_loeschen(abend_id: int):
        with sperre:
            wartung.sicherung_anlegen(datenbank_pfad)
            mit_db(wartung.abend_loeschen, abend_id)
        return {"wartung": mit_db(wartung_uebersicht)}

    @app.delete("/api/wartung/abgebrochene")
    def wartung_abgebrochene_loeschen():
        with sperre:
            wartung.sicherung_anlegen(datenbank_pfad)
            anzahl = mit_db(wartung.abgebrochene_haende_loeschen, laufende_hand_id())
        return {"geloescht_haende": anzahl, "wartung": mit_db(wartung_uebersicht)}

    # ---------------- Entwicklungsmodus ----------------

    if entwicklung:
        @app.get("/api/entwicklung/stand")
        def entwicklung_stand():
            """Startzeit des Servers und letzte Aenderung in web/.

            Aendert sich einer der Werte, laedt die Web-App die Seite neu.
            """
            letzte_aenderung = 0.0
            for datei in WEB_ORDNER.iterdir():
                if datei.is_file():
                    letzte_aenderung = max(letzte_aenderung, datei.stat().st_mtime)
            return {"start": START_ZEIT, "web": letzte_aenderung}

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


def entwicklungs_app():
    """App fuer den Entwicklungsmodus. uvicorn ruft diese Funktion nach jedem
    Neustart selbst auf; die Datenbank kommt deshalb ueber eine Umgebungsvariable."""
    return erstelle_app(os.environ.get("POKER_DATENBANK", STANDARD_DATENBANK), entwicklung=True)


if __name__ == "__main__":
    import uvicorn

    argumente = [a for a in sys.argv[1:] if a != "--entwicklung"]
    pfad = argumente[0] if argumente else STANDARD_DATENBANK
    print(f"Datenbank: {pfad}")
    print("Am PC oeffnen:       http://localhost:8000")
    print(f"Auf dem iPhone:      http://{eigene_ip()}:8000")

    if "--entwicklung" in sys.argv:
        print("Entwicklungsmodus: Aenderungen werden automatisch geladen. Beenden mit Strg+C.")
        os.environ["POKER_DATENBANK"] = pfad
        # reload=True: uvicorn beobachtet die .py-Dateien und startet bei Aenderungen neu.
        # Dafuer braucht es die App als Text ("server:entwicklungs_app"), nicht als Objekt.
        uvicorn.run("server:entwicklungs_app", factory=True, reload=True,
                    reload_dirs=[str(PROJEKT_ORDNER)], host="0.0.0.0", port=8000,
                    log_level="warning")
    else:
        uvicorn.run(erstelle_app(pfad), host="0.0.0.0", port=8000, log_level="warning")
