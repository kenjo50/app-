"""Analyse-Modus: Was lief gut, was lief schlecht? (Reiter "Analyse" in der Web-App)

Alles zaehlt nur abgeschlossene Haende mit Ergebnis. Gewinne und Verluste
werden in Big Blinds gerechnet, damit Abende mit anderen Blinds vergleichbar sind.

- verlauf_pro_abend: Kennzahlen pro Kalendertag (ein Abend = ein Datum)
- gewinnkurve:       aufsummierte Big Blinds nach jeder Hand
- ki_auswertung:     Wie oft wurde die KI-Empfehlung befolgt, und wie lief es?
- fehlentscheidungen: Entscheidungen gegen die Empfehlung, teuerste zuerst
- teuerste_haende:   die groessten Verluste mit Karten und Verlauf
- gegner_uebersicht: alle anderen Spieler mit Typ und Tipps dagegen
"""

from poker.ki import TYP_NAMEN, erkenne_typ
from poker.profile import (FREIWILLIG, AGGRESSIV, berechne_statistik, lade_aktionen,
                           text_zu_karten)

# Wie viele Board-Karten liegen auf welcher Strasse?
BOARD_AUF_STRASSE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}

# Was hilft gegen welchen Typ? Kurz und konkret fuer den Tisch.
ANPASSUNG = {
    "felsen": [
        "Seine Blinds oft angreifen - er gibt viel zu oft auf.",
        "Erhoeht er, hat er meistens wirklich etwas: mittlere Haende weglegen.",
        "Kleine Bluffs funktionieren gut - ohne starke Hand gibt er auf.",
    ],
    "station": [
        "Nicht bluffen - er bezahlt fast alles.",
        "Gute Haende gross setzen (Value Bets), er zahlt sie aus.",
        "Callt er nur, ist seine Hand oft mittelmaessig.",
    ],
    "maniac": [
        "Starke Haende spielen und ihn selbst setzen lassen.",
        "Mit guten Haenden eher callen als folden - er blufft viel.",
        "Keine Bluffs gegen ihn, er geht ohnehin weiter.",
    ],
    "tag": [
        "Der staerkste Typ: grosse Pots nur mit sehr guten Haenden.",
        "Seine Erhoehungen ernst nehmen, er spielt ausgewaehlt und druckvoll.",
        "Lieber gegen schwaechere Spieler am Tisch Chips holen.",
    ],
    "unbekannt": [
        "Noch zu wenig Haende (unter 20) - erst einmal normal spielen und beobachten.",
    ],
}


def _spieler_id(verbindung, name):
    zeile = verbindung.execute("SELECT id FROM spieler WHERE name = ?", (name,)).fetchone()
    if zeile is None:
        raise ValueError(f"Unbekannter Spieler: {name}")
    return zeile[0]


def _haende_mit_ergebnis(verbindung, sid):
    """Alle abgeschlossenen Haende des Spielers mit Ergebnis, aelteste zuerst."""
    haende = []
    for hand_id, zeitpunkt, big_blind, board, handkarten, investiert, gewonnen in verbindung.execute(
        "SELECT h.id, h.zeitpunkt, h.big_blind, h.board, t.handkarten, t.investiert, t.gewonnen "
        "FROM teilnehmer t JOIN haende h ON t.hand_id = h.id "
        "WHERE t.spieler_id = ? AND h.abgeschlossen = 1 AND t.gewonnen IS NOT NULL "
        "ORDER BY h.id", (sid,)
    ):
        haende.append({
            "hand_id": hand_id,
            "datum": zeitpunkt[:10],
            "bb": (gewonnen - investiert) / big_blind,
            "board": text_zu_karten(board) or [],
            "handkarten": text_zu_karten(handkarten),
        })
    return haende


def _preflop_aktionen(verbindung, sid):
    """{hand_id: [aktion, ...]} der preflop-Aktionen des Spielers."""
    preflop = {}
    for hand_id, aktion in verbindung.execute(
        "SELECT hand_id, aktion FROM aktionen WHERE spieler_id = ? AND strasse = 'preflop'",
        (sid,),
    ):
        preflop.setdefault(hand_id, []).append(aktion)
    return preflop


def _pro_100(summe_bb, haende):
    return summe_bb / haende * 100 if haende else None


def verlauf_pro_abend(verbindung, name):
    """Kennzahlen pro Datum, aelteste zuerst.

    Rueckgabe: Liste von {"datum", "haende", "vpip", "pfr", "bb", "bb_pro_100"}
    (bb = Gewinn/Verlust an diesem Tag in Big Blinds).
    """
    sid = _spieler_id(verbindung, name)
    preflop = _preflop_aktionen(verbindung, sid)
    tage = {}
    for hand in _haende_mit_ergebnis(verbindung, sid):
        tag = tage.setdefault(hand["datum"], {"haende": 0, "vpip": 0, "pfr": 0, "bb": 0.0})
        aktionen = preflop.get(hand["hand_id"], [])
        tag["haende"] += 1
        tag["bb"] += hand["bb"]
        if any(a in FREIWILLIG for a in aktionen):
            tag["vpip"] += 1
        if any(a in AGGRESSIV for a in aktionen):
            tag["pfr"] += 1
    ergebnis = []
    for datum in sorted(tage):
        tag = tage[datum]
        ergebnis.append({
            "datum": datum,
            "haende": tag["haende"],
            "vpip": tag["vpip"] / tag["haende"],
            "pfr": tag["pfr"] / tag["haende"],
            "bb": tag["bb"],
            "bb_pro_100": _pro_100(tag["bb"], tag["haende"]),
        })
    return ergebnis


def gewinnkurve(verbindung, name):
    """Aufsummierter Gewinn in Big Blinds nach jeder Hand.

    Rueckgabe: Liste von {"nr", "hand_id", "datum", "bb"}; nr zaehlt ab 1.
    """
    sid = _spieler_id(verbindung, name)
    kurve = []
    summe = 0.0
    for nr, hand in enumerate(_haende_mit_ergebnis(verbindung, sid), start=1):
        summe += hand["bb"]
        kurve.append({"nr": nr, "hand_id": hand["hand_id"], "datum": hand["datum"],
                      "bb": round(summe, 2)})
    return kurve


def _empfehlungen(verbindung, sid):
    """Alle protokollierten Empfehlungen des Spielers in abgeschlossenen Haenden."""
    zeilen = []
    for (eid, hand_id, strasse, empfohlen, empfohlen_betrag, gespielt, gespielt_betrag,
         befolgt, equity, pot_odds) in verbindung.execute(
        "SELECT e.id, e.hand_id, e.strasse, e.empfohlen, e.empfohlen_betrag, e.gespielt, "
        "e.gespielt_betrag, e.befolgt, e.equity, e.pot_odds "
        "FROM empfehlungen e JOIN haende h ON e.hand_id = h.id "
        "WHERE e.spieler_id = ? AND h.abgeschlossen = 1 ORDER BY e.id", (sid,)
    ):
        zeilen.append({"id": eid, "hand_id": hand_id, "strasse": strasse,
                       "empfohlen": empfohlen, "empfohlen_betrag": empfohlen_betrag,
                       "gespielt": gespielt, "gespielt_betrag": gespielt_betrag,
                       "befolgt": bool(befolgt), "equity": equity, "pot_odds": pot_odds})
    return zeilen


def ki_auswertung(verbindung, name):
    """Wie oft wurde die KI befolgt, und wie viel brachte das?

    Eine Hand gilt als "befolgt", wenn jede protokollierte Entscheidung der
    Empfehlung entsprach, sonst als "abgewichen". Haende ohne Empfehlung
    stehen unter "ohne_ki".

    Rueckgabe: {"entscheidungen", "befolgt", "quote",
                "gruppen": {"befolgt"/"abgewichen"/"ohne_ki": {"haende", "bb", "bb_pro_100"}}}
    """
    sid = _spieler_id(verbindung, name)
    empfehlungen = _empfehlungen(verbindung, sid)
    hand_befolgt = {}   # hand_id -> alle Entscheidungen befolgt?
    for e in empfehlungen:
        hand_befolgt[e["hand_id"]] = hand_befolgt.get(e["hand_id"], True) and e["befolgt"]

    gruppen = {g: {"haende": 0, "bb": 0.0} for g in ["befolgt", "abgewichen", "ohne_ki"]}
    for hand in _haende_mit_ergebnis(verbindung, sid):
        if hand["hand_id"] not in hand_befolgt:
            gruppe = "ohne_ki"
        elif hand_befolgt[hand["hand_id"]]:
            gruppe = "befolgt"
        else:
            gruppe = "abgewichen"
        gruppen[gruppe]["haende"] += 1
        gruppen[gruppe]["bb"] += hand["bb"]
    for werte in gruppen.values():
        werte["bb_pro_100"] = _pro_100(werte["bb"], werte["haende"])

    anzahl_befolgt = sum(1 for e in empfehlungen if e["befolgt"])
    return {
        "entscheidungen": len(empfehlungen),
        "befolgt": anzahl_befolgt,
        "quote": anzahl_befolgt / len(empfehlungen) if empfehlungen else None,
        "gruppen": gruppen,
    }


def fehlentscheidungen(verbindung, name, anzahl=10):
    """Entscheidungen gegen die KI-Empfehlung, die teuersten Haende zuerst.

    Jeder Eintrag: die Empfehlungs-Zeile plus "datum", "handkarten",
    "board" (so viele Karten, wie auf dieser Strasse lagen) und
    "ergebnis_bb" (Ergebnis der ganzen Hand).
    """
    sid = _spieler_id(verbindung, name)
    haende = {h["hand_id"]: h for h in _haende_mit_ergebnis(verbindung, sid)}
    liste = []
    for e in _empfehlungen(verbindung, sid):
        hand = haende.get(e["hand_id"])
        if e["befolgt"] or hand is None:
            continue
        eintrag = dict(e)
        eintrag["datum"] = hand["datum"]
        eintrag["handkarten"] = hand["handkarten"]
        eintrag["board"] = hand["board"][:BOARD_AUF_STRASSE[e["strasse"]]]
        eintrag["ergebnis_bb"] = hand["bb"]
        liste.append(eintrag)
    liste.sort(key=lambda eintrag: eintrag["ergebnis_bb"])
    return liste[:anzahl]


def teuerste_haende(verbindung, name, anzahl=10):
    """Die groessten Verluste (in Big Blinds) mit Karten, Board und Verlauf.

    Jeder Eintrag: {"hand_id", "datum", "bb", "handkarten", "board",
                    "gewinner": [namen], "verlauf": [{"name", "strasse", "aktion", "betrag"}]}
    """
    sid = _spieler_id(verbindung, name)
    verluste = [h for h in _haende_mit_ergebnis(verbindung, sid) if h["bb"] < 0]
    verluste.sort(key=lambda hand: hand["bb"])
    ergebnis = []
    for hand in verluste[:anzahl]:
        eintrag = dict(hand)
        eintrag["gewinner"] = [n for (n,) in verbindung.execute(
            "SELECT s.name FROM teilnehmer t JOIN spieler s ON t.spieler_id = s.id "
            "WHERE t.hand_id = ? AND t.gewonnen > 0 ORDER BY t.sitzplatz", (hand["hand_id"],))]
        eintrag["verlauf"] = [
            {"name": n, "strasse": strasse, "aktion": aktion, "betrag": betrag}
            for n, strasse, aktion, betrag in lade_aktionen(verbindung, hand["hand_id"])
        ]
        ergebnis.append(eintrag)
    return ergebnis


def gegner_uebersicht(verbindung, ohne=None):
    """Alle Spieler (ausser `ohne`) mit abgeschlossenen Haenden: Typ und Tipps.

    Sortiert nach Anzahl Haende, die meisten zuerst.
    """
    liste = []
    for (name,) in verbindung.execute("SELECT name FROM spieler ORDER BY name").fetchall():
        if name == ohne:
            continue
        statistik = berechne_statistik(verbindung, name)
        if statistik["haende"] == 0:
            continue
        erkennung = erkenne_typ(statistik)
        liste.append({
            "name": name,
            "haende": statistik["haende"],
            "vpip": statistik["vpip"],
            "pfr": statistik["pfr"],
            "af": statistik["af"],
            "bb_pro_100": statistik["bb_pro_100"],
            "typ": erkennung["typ"],
            "typ_name": TYP_NAMEN[erkennung["typ"]],
            "sicherheit": erkennung["sicherheit"],
            "tipps": ANPASSUNG[erkennung["typ"]],
        })
    liste.sort(key=lambda g: -g["haende"])
    return liste


def analyse(verbindung, name):
    """Alles fuer den Analyse-Reiter in einem Paket."""
    return {
        "name": name,
        "statistik": berechne_statistik(verbindung, name),
        "abende": verlauf_pro_abend(verbindung, name),
        "kurve": gewinnkurve(verbindung, name),
        "ki": ki_auswertung(verbindung, name),
        "fehler": fehlentscheidungen(verbindung, name),
        "teuerste": teuerste_haende(verbindung, name),
        "gegner": gegner_uebersicht(verbindung, ohne=name),
    }
