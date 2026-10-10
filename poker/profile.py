"""Spielerprofile: Haende und Aktionen in SQLite speichern, Statistiken berechnen.

Jede Funktion bekommt eine offene Datenbank-Verbindung uebergeben.
So koennen Tests eine Datenbank im Arbeitsspeicher (":memory:") nutzen
und die echte Datei bleibt unberuehrt.

Tabellen:
- spieler:     ein Eintrag pro Person (Name ist eindeutig)
- haende:      ein Eintrag pro gespielter Hand (Blinds, Board, Zeitpunkt)
- teilnehmer:  wer bei welcher Hand dabei war (Sitzplatz, Handkarten falls bekannt,
               Stack zu Beginn der Hand, wie viel er insgesamt gesetzt und
               wie viel er gewonnen hat)
- aktionen:    jede einzelne Aktion: Strasse, Art, Betrag, in Reihenfolge
"""

import json
import sqlite3
from datetime import datetime

STRASSEN = ["preflop", "flop", "turn", "river"]
AKTIONEN = ["fold", "check", "call", "bet", "raise"]

# Aktionen, mit denen ein Spieler freiwillig Geld setzt bzw. Druck macht.
FREIWILLIG = ["call", "bet", "raise"]
AGGRESSIV = ["bet", "raise"]

TABELLEN_SQL = """
CREATE TABLE IF NOT EXISTS spieler (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS haende (
    id           INTEGER PRIMARY KEY,
    zeitpunkt    TEXT NOT NULL,
    small_blind  REAL NOT NULL,
    big_blind    REAL NOT NULL,
    board        TEXT
);
CREATE TABLE IF NOT EXISTS teilnehmer (
    hand_id     INTEGER NOT NULL REFERENCES haende(id),
    spieler_id  INTEGER NOT NULL REFERENCES spieler(id),
    sitzplatz   INTEGER NOT NULL,
    handkarten  TEXT,
    stack       REAL,
    investiert  REAL,
    gewonnen    REAL,
    PRIMARY KEY (hand_id, spieler_id)
);
CREATE TABLE IF NOT EXISTS aktionen (
    id          INTEGER PRIMARY KEY,
    hand_id     INTEGER NOT NULL REFERENCES haende(id),
    spieler_id  INTEGER NOT NULL REFERENCES spieler(id),
    strasse     TEXT NOT NULL,
    aktion      TEXT NOT NULL,
    betrag      REAL NOT NULL DEFAULT 0
);
"""


# Spalten, die spaeter dazugekommen sind. Aeltere Datenbank-Dateien
# bekommen sie beim Oeffnen automatisch nachgeruestet.
NEUE_SPALTEN = [
    ("teilnehmer", "investiert", "REAL"),
    ("teilnehmer", "gewonnen", "REAL"),
    ("teilnehmer", "stack", "REAL"),
]


def oeffne_datenbank(pfad):
    """Oeffnet (oder erstellt) die Datenbank und legt fehlende Tabellen an."""
    verbindung = sqlite3.connect(pfad)
    verbindung.execute("PRAGMA foreign_keys = ON")
    verbindung.executescript(TABELLEN_SQL)
    for tabelle, spalte, typ in NEUE_SPALTEN:
        vorhandene = []
        for zeile in verbindung.execute(f"PRAGMA table_info({tabelle})"):
            vorhandene.append(zeile[1])  # zeile[1] ist der Spaltenname
        if spalte not in vorhandene:
            verbindung.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
    verbindung.commit()
    return verbindung


def karten_zu_text(karten):
    """Speicherformat fuer Karten: JSON-Text, z. B. '[[14, "Pik"], [13, "Herz"]]'."""
    return json.dumps(karten)


def text_zu_karten(text):
    """Gegenstueck zu karten_zu_text: macht wieder eine Liste von Tupeln daraus."""
    if text is None:
        return None
    karten = []
    for rang, farbe in json.loads(text):
        karten.append((rang, farbe))
    return karten


def spieler_id(verbindung, name):
    """Gibt die id eines Spielers zurueck. Unbekannte Namen werden angelegt."""
    zeile = verbindung.execute(
        "SELECT id FROM spieler WHERE name = ?", (name,)
    ).fetchone()
    if zeile is not None:
        return zeile[0]
    cursor = verbindung.execute("INSERT INTO spieler (name) VALUES (?)", (name,))
    verbindung.commit()
    return cursor.lastrowid


def neue_hand(verbindung, namen, small_blind, big_blind, stacks=None, zeitpunkt=None):
    """Legt eine neue Hand an. `namen` in Sitzreihenfolge. Gibt die hand_id zurueck.

    stacks: optional {name: chips zu Beginn der Hand}
    """
    if len(namen) < 2:
        raise ValueError("Eine Hand braucht mindestens zwei Spieler")
    if len(set(namen)) != len(namen):
        raise ValueError("Ein Spieler ist doppelt eingetragen")
    if zeitpunkt is None:
        zeitpunkt = datetime.now().isoformat(timespec="seconds")

    cursor = verbindung.execute(
        "INSERT INTO haende (zeitpunkt, small_blind, big_blind) VALUES (?, ?, ?)",
        (zeitpunkt, small_blind, big_blind),
    )
    hand_id = cursor.lastrowid
    for sitzplatz in range(len(namen)):
        name = namen[sitzplatz]
        stack = None if stacks is None else stacks[name]
        verbindung.execute(
            "INSERT INTO teilnehmer (hand_id, spieler_id, sitzplatz, stack) "
            "VALUES (?, ?, ?, ?)",
            (hand_id, spieler_id(verbindung, name), sitzplatz, stack),
        )
    verbindung.commit()
    return hand_id


def _teilnehmer_id(verbindung, hand_id, name):
    """Hilfsfunktion: id des Spielers, aber nur wenn er an der Hand teilnimmt."""
    zeile = verbindung.execute(
        "SELECT s.id FROM spieler s JOIN teilnehmer t ON t.spieler_id = s.id "
        "WHERE t.hand_id = ? AND s.name = ?",
        (hand_id, name),
    ).fetchone()
    if zeile is None:
        raise ValueError(f"{name} spielt bei Hand {hand_id} nicht mit")
    return zeile[0]


def aktion_speichern(verbindung, hand_id, name, strasse, aktion, betrag=0):
    """Speichert eine Aktion. Die Reihenfolge ergibt sich aus der Speicher-Reihenfolge."""
    if strasse not in STRASSEN:
        raise ValueError(f"Unbekannte Strasse: {strasse}")
    if aktion not in AKTIONEN:
        raise ValueError(f"Unbekannte Aktion: {aktion}")
    if aktion in ["fold", "check"] and betrag != 0:
        raise ValueError(f"{aktion} hat keinen Betrag")
    if aktion in ["call", "bet", "raise"] and betrag <= 0:
        raise ValueError(f"{aktion} braucht einen Betrag groesser 0")

    verbindung.execute(
        "INSERT INTO aktionen (hand_id, spieler_id, strasse, aktion, betrag) "
        "VALUES (?, ?, ?, ?, ?)",
        (hand_id, _teilnehmer_id(verbindung, hand_id, name), strasse, aktion, betrag),
    )
    verbindung.commit()


def board_speichern(verbindung, hand_id, board):
    """Speichert die Board-Karten (bis zu 5) einer Hand."""
    verbindung.execute(
        "UPDATE haende SET board = ? WHERE id = ?", (karten_zu_text(board), hand_id)
    )
    verbindung.commit()


def handkarten_speichern(verbindung, hand_id, name, karten):
    """Speichert die Handkarten eines Spielers (z. B. nach dem Showdown)."""
    verbindung.execute(
        "UPDATE teilnehmer SET handkarten = ? WHERE hand_id = ? AND spieler_id = ?",
        (karten_zu_text(karten), hand_id, _teilnehmer_id(verbindung, hand_id, name)),
    )
    verbindung.commit()


def ergebnis_speichern(verbindung, hand_id, name, investiert, gewonnen):
    """Speichert, wie viel ein Spieler in der Hand gesetzt und gewonnen hat."""
    verbindung.execute(
        "UPDATE teilnehmer SET investiert = ?, gewonnen = ? "
        "WHERE hand_id = ? AND spieler_id = ?",
        (investiert, gewonnen, hand_id, _teilnehmer_id(verbindung, hand_id, name)),
    )
    verbindung.commit()


def lade_aktionen(verbindung, hand_id):
    """Gibt alle Aktionen einer Hand in Reihenfolge zurueck.

    Ergebnis: Liste von Tupeln (name, strasse, aktion, betrag).
    """
    return verbindung.execute(
        "SELECT s.name, a.strasse, a.aktion, a.betrag "
        "FROM aktionen a JOIN spieler s ON a.spieler_id = s.id "
        "WHERE a.hand_id = ? ORDER BY a.id",
        (hand_id,),
    ).fetchall()


def berechne_statistik(verbindung, name):
    """Berechnet die Kennzahlen eines Spielers ueber alle gespeicherten Haende.

    Rueckgabe: Dictionary mit
    - "haende": Anzahl Haende, bei denen er dabei war
    - "vpip":   Anteil Haende, in denen er preflop freiwillig Geld setzt (call/bet/raise)
    - "pfr":    Anteil Haende, in denen er preflop erhoeht (bet/raise)
    - "af":     Aggressionsfaktor nach dem Flop: (bets + raises) / calls
    - "bb_pro_100": Gewinn in Big Blinds pro 100 Haende
                  (nur Haende, deren Ergebnis gespeichert ist)

    Werte, die sich (noch) nicht berechnen lassen, sind None.
    """
    zeile = verbindung.execute("SELECT id FROM spieler WHERE name = ?", (name,)).fetchone()
    if zeile is None:
        raise ValueError(f"Unbekannter Spieler: {name}")
    sid = zeile[0]

    haende = verbindung.execute(
        "SELECT COUNT(*) FROM teilnehmer WHERE spieler_id = ?", (sid,)
    ).fetchone()[0]

    # Pro Hand die preflop-Aktionen sammeln: {hand_id: [aktion, ...]}
    preflop = {}
    for hand_id, aktion in verbindung.execute(
        "SELECT hand_id, aktion FROM aktionen WHERE spieler_id = ? AND strasse = 'preflop'",
        (sid,),
    ):
        if hand_id not in preflop:
            preflop[hand_id] = []
        preflop[hand_id].append(aktion)

    vpip_haende = 0
    pfr_haende = 0
    for aktionen in preflop.values():
        if any(a in FREIWILLIG for a in aktionen):
            vpip_haende = vpip_haende + 1
        if any(a in AGGRESSIV for a in aktionen):
            pfr_haende = pfr_haende + 1

    # Aggressionsfaktor nach dem Flop
    aggressiv = 0
    calls = 0
    for (aktion,) in verbindung.execute(
        "SELECT aktion FROM aktionen WHERE spieler_id = ? AND strasse != 'preflop'",
        (sid,),
    ):
        if aktion in AGGRESSIV:
            aggressiv = aggressiv + 1
        elif aktion == "call":
            calls = calls + 1

    # Gewinn/Verlust in Big Blinds, nur abgerechnete Haende
    abgerechnet = 0
    summe_bb = 0.0
    for investiert, gewonnen, big_blind in verbindung.execute(
        "SELECT t.investiert, t.gewonnen, h.big_blind "
        "FROM teilnehmer t JOIN haende h ON t.hand_id = h.id "
        "WHERE t.spieler_id = ? AND t.gewonnen IS NOT NULL",
        (sid,),
    ):
        abgerechnet = abgerechnet + 1
        summe_bb = summe_bb + (gewonnen - investiert) / big_blind

    statistik = {"haende": haende, "vpip": None, "pfr": None, "af": None,
                 "bb_pro_100": None}
    if haende > 0:
        statistik["vpip"] = vpip_haende / haende
        statistik["pfr"] = pfr_haende / haende
    if calls > 0:
        statistik["af"] = aggressiv / calls
    if abgerechnet > 0:
        statistik["bb_pro_100"] = summe_bb / abgerechnet * 100
    return statistik
