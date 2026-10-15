"""Wartung: Datenbank sichern und Testdaten aufraeumen.

Sicherung: eine Kopie der Datenbank-Datei mit Datum und Uhrzeit im Namen,
im Ordner "sicherungen" neben der Datenbank. Es bleiben die neuesten 30.
Kopiert wird mit der Sicherungs-Funktion von SQLite (backup), die auch bei
geoeffneter Datenbank eine saubere Kopie erzeugt.

Aufraeumen:
- einzelne Spieler mit allen ihren Haenden (die ganzen Haende, auch fuer die
  Mitspieler - halbe Haende wuerden die Statistik verfaelschen)
- einzelne Abende (Turnier/Cash Game samt Buchungen)
- abgebrochene Haende
"""

import sqlite3
from datetime import datetime
from pathlib import Path

SICHERUNGEN_BEHALTEN = 30


# ---------------- Sicherung ----------------


def sicherungs_ordner(datenbank_pfad):
    return Path(datenbank_pfad).resolve().parent / "sicherungen"


def sicherung_anlegen(datenbank_pfad, jetzt=None, behalten=SICHERUNGEN_BEHALTEN):
    """Legt eine Kopie der Datenbank an und raeumt alte Kopien weg.

    Gibt den Pfad der Kopie zurueck, oder None, wenn es (noch) keine Datei gibt.
    """
    quelle = Path(datenbank_pfad)
    if str(datenbank_pfad) == ":memory:" or not quelle.exists():
        return None
    if jetzt is None:
        jetzt = datetime.now()
    ordner = sicherungs_ordner(datenbank_pfad)
    ordner.mkdir(exist_ok=True)
    ziel = ordner / f"{quelle.stem}_{jetzt.strftime('%Y-%m-%d_%H-%M-%S')}.db"
    nummer = 2
    while ziel.exists():  # zwei Sicherungen in derselben Sekunde
        ziel = ordner / f"{quelle.stem}_{jetzt.strftime('%Y-%m-%d_%H-%M-%S')}_{nummer}.db"
        nummer += 1

    von = sqlite3.connect(quelle)
    nach = sqlite3.connect(ziel)
    try:
        von.backup(nach)
    finally:
        nach.close()
        von.close()

    # Nur die neuesten `behalten` Sicherungen dieser Datenbank aufheben
    alle = sorted(ordner.glob(f"{quelle.stem}_*.db"))
    for alte in alle[:-behalten]:
        alte.unlink()
    return ziel


def sicherungen_liste(datenbank_pfad):
    """Alle Sicherungen dieser Datenbank, neueste zuerst."""
    ordner = sicherungs_ordner(datenbank_pfad)
    if not ordner.exists():
        return []
    ergebnis = []
    for datei in sorted(ordner.glob(f"{Path(datenbank_pfad).stem}_*.db"), reverse=True):
        ergebnis.append({"name": datei.name, "groesse": datei.stat().st_size})
    return ergebnis


# ---------------- Aufraeumen ----------------


def _hand_ids_von(verbindung, sid):
    ids = []
    for (hand_id,) in verbindung.execute(
        "SELECT hand_id FROM teilnehmer WHERE spieler_id = ?", (sid,)
    ):
        ids.append(hand_id)
    return ids


def _haende_loeschen(verbindung, hand_ids):
    for hand_id in hand_ids:
        verbindung.execute("DELETE FROM empfehlungen WHERE hand_id = ?", (hand_id,))
        verbindung.execute("DELETE FROM aktionen WHERE hand_id = ?", (hand_id,))
        verbindung.execute("DELETE FROM teilnehmer WHERE hand_id = ?", (hand_id,))
        verbindung.execute("DELETE FROM haende WHERE id = ?", (hand_id,))


def _spieler_zeile(verbindung, name):
    zeile = verbindung.execute("SELECT id FROM spieler WHERE name = ?", (name,)).fetchone()
    if zeile is None:
        raise ValueError(f"Einen Spieler '{name}' gibt es nicht")
    return zeile[0]


def spieler_loeschvorschau(verbindung, name):
    """Was wuerde beim Loeschen eines Spielers alles verschwinden?

    Rueckgabe: {"name", "haende", "mitspieler": [...], "abende": [...]}
    abende: Turniere/Cash Games, in denen er steht - die muessen zuerst weg.
    """
    sid = _spieler_zeile(verbindung, name)
    hand_ids = _hand_ids_von(verbindung, sid)
    mitspieler = set()
    for hand_id in hand_ids:
        for (anderer,) in verbindung.execute(
            "SELECT s.name FROM teilnehmer t JOIN spieler s ON t.spieler_id = s.id "
            "WHERE t.hand_id = ? AND s.id != ?", (hand_id, sid)
        ):
            mitspieler.add(anderer)
    abende = []
    for abend_id, art, zeitpunkt, abend_name in verbindung.execute(
        "SELECT a.id, a.art, a.zeitpunkt, a.name FROM abende a "
        "JOIN abend_spieler s ON s.abend_id = a.id WHERE s.spieler_id = ? ORDER BY a.id",
        (sid,),
    ):
        abende.append({"id": abend_id, "art": art, "zeitpunkt": zeitpunkt, "name": abend_name})
    return {"name": name, "haende": len(hand_ids), "mitspieler": sorted(mitspieler),
            "abende": abende}


def spieler_loeschen(verbindung, name, live_spieler=()):
    """Loescht einen Spieler mit allen Haenden, in denen er mitgespielt hat.

    live_spieler: Namen am gerade laufenden Live-Abend - die duerfen nicht weg.
    Steht der Spieler noch in einem Turnier/Cash Game, muss erst der Abend weg.
    Gibt die Anzahl geloeschter Haende zurueck.
    """
    if name in live_spieler:
        raise ValueError(f"{name} sitzt am laufenden Live-Abend - bitte erst den Abend beenden")
    vorschau = spieler_loeschvorschau(verbindung, name)
    if vorschau["abende"]:
        erster = vorschau["abende"][0]
        raise ValueError(f"{name} steht noch in einem Abend ({erster['zeitpunkt'][:10]}) - "
                         "bitte zuerst diesen Abend loeschen")
    sid = _spieler_zeile(verbindung, name)
    _haende_loeschen(verbindung, _hand_ids_von(verbindung, sid))
    verbindung.execute("DELETE FROM spieler WHERE id = ?", (sid,))
    verbindung.commit()
    return vorschau["haende"]


def abend_loeschen(verbindung, abend_id):
    """Loescht ein Turnier oder Cash Game samt allen Buchungen."""
    if verbindung.execute("SELECT id FROM abende WHERE id = ?", (abend_id,)).fetchone() is None:
        raise ValueError(f"Abend {abend_id} gibt es nicht")
    verbindung.execute("DELETE FROM buchungen WHERE abend_id = ?", (abend_id,))
    verbindung.execute("DELETE FROM abend_spieler WHERE abend_id = ?", (abend_id,))
    verbindung.execute("DELETE FROM abende WHERE id = ?", (abend_id,))
    verbindung.commit()


def abgebrochene_haende_loeschen(verbindung, ausser_hand_id=None):
    """Loescht alle nicht abgeschlossenen Haende (ausser der gerade laufenden).

    Gibt die Anzahl geloeschter Haende zurueck.
    """
    ids = []
    for (hand_id,) in verbindung.execute("SELECT id FROM haende WHERE abgeschlossen = 0"):
        if hand_id != ausser_hand_id:
            ids.append(hand_id)
    _haende_loeschen(verbindung, ids)
    verbindung.commit()
    return len(ids)


def spieler_uebersicht(verbindung):
    """Alle Spieler mit Anzahl abgeschlossener Haende und Abende (fuer die Aufraeum-Liste)."""
    ergebnis = []
    for sid, name in verbindung.execute("SELECT id, name FROM spieler ORDER BY name").fetchall():
        haende = verbindung.execute(
            "SELECT COUNT(*) FROM teilnehmer t JOIN haende h ON t.hand_id = h.id "
            "WHERE t.spieler_id = ? AND h.abgeschlossen = 1", (sid,)).fetchone()[0]
        abende = verbindung.execute(
            "SELECT COUNT(*) FROM abend_spieler WHERE spieler_id = ?", (sid,)).fetchone()[0]
        ergebnis.append({"name": name, "haende": haende, "abende": abende})
    return ergebnis
