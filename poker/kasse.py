"""Kasse: Buy-ins, Rebuys, Add-ons und Auszahlungen fuer Turnier und Cash Game.

Alle Geldbetraege sind ganze Zahlen in Cent (10 Euro = 1000). Mit Kommazahlen
wuerde z. B. 0.1 + 0.2 nicht genau 0.3 ergeben, und die Kontrollrechnung
im Cash Game ginge nie exakt auf.

Spieler werden ueber ihren Namen mit den Spielerprofilen verknuepft
(Tabelle `spieler`, siehe poker/profile.py). Jeder Abend (Turnier oder
Cash Game) wird dauerhaft gespeichert, damit es eine Bilanz ueber viele
Abende gibt.
"""

import json
from datetime import datetime

from poker.profile import spieler_id

# Unsere Cash-Game-Chips: 10 ct, 25 ct, 50 ct, 1 Euro. Buy-in 10 Euro.
CASH_CHIPS_CENT = [10, 25, 50, 100]
CASH_BUYIN_CENT = 1000

STANDARD_AUSZAHLUNG = [60, 30, 10]
TURNIER_ARTEN = ["buyin", "rebuy", "addon"]


def _jetzt_text(zeitpunkt):
    if zeitpunkt is None:
        return datetime.now().isoformat(timespec="seconds")
    return zeitpunkt


# ---------------- Hilfen fuer Betraege ----------------


def euro_zu_cent(text):
    """Macht aus "10", "10,50" oder "10.5" den Betrag in Cent (1050)."""
    text = str(text).strip().replace("€", "").replace(",", ".").strip()
    try:
        euro = float(text)
    except ValueError:
        raise ValueError(f"'{text}' ist kein Geldbetrag")
    cent = round(euro * 100)
    if abs(euro * 100 - cent) > 1e-6:
        raise ValueError("Mehr als zwei Nachkommastellen gehen nicht")
    return cent


def chips_wert_cent(anzahlen, chip_werte=CASH_CHIPS_CENT):
    """Zaehlt Chips: {10: 5, 100: 3} -> 5 x 10 ct + 3 x 1 Euro = 350 Cent."""
    summe = 0
    for wert, anzahl in anzahlen.items():
        if wert not in chip_werte:
            raise ValueError(f"Einen Chip mit Wert {wert} gibt es nicht")
        if anzahl < 0:
            raise ValueError("Die Anzahl darf nicht negativ sein")
        summe = summe + wert * anzahl
    return summe


def pruefe_auszahlung(prozente):
    """Auszahlungsstruktur: ganze Prozentzahlen > 0, zusammen genau 100."""
    if len(prozente) == 0:
        raise ValueError("Mindestens ein Platz muss bezahlt werden")
    for p in prozente:
        if p <= 0 or int(p) != p:
            raise ValueError("Prozente muessen ganze Zahlen groesser 0 sein")
    if sum(prozente) != 100:
        raise ValueError(f"Die Prozente ergeben {sum(prozente)} statt 100")


def berechne_auszahlung(preisgeld_cent, prozente, rundung_cent=100):
    """Teilt das Preisgeld nach Prozenten auf (Platz 1 zuerst).

    Jeder Platz wird auf `rundung_cent` abgerundet (Standard: ganze Euro).
    Was dabei uebrig bleibt, bekommt Platz 1. So ergibt die Summe immer
    genau das Preisgeld.
    """
    pruefe_auszahlung(prozente)
    betraege = []
    for p in prozente:
        betrag = preisgeld_cent * p // 100
        betrag = betrag // rundung_cent * rundung_cent
        betraege.append(betrag)
    betraege[0] = betraege[0] + preisgeld_cent - sum(betraege)
    return betraege


# ---------------- Abende allgemein ----------------


def _lade_abend(verbindung, abend_id, art):
    zeile = verbindung.execute(
        "SELECT art, beendet, buyin_cent, rebuy_cent, addon_cent, auszahlung "
        "FROM abende WHERE id = ?", (abend_id,)
    ).fetchone()
    if zeile is None:
        raise ValueError(f"Abend {abend_id} gibt es nicht")
    if zeile[0] != art:
        raise ValueError(f"Abend {abend_id} ist kein {art}")
    return {"art": zeile[0], "beendet": bool(zeile[1]), "buyin_cent": zeile[2],
            "rebuy_cent": zeile[3], "addon_cent": zeile[4],
            "auszahlung": None if zeile[5] is None else json.loads(zeile[5])}


def _pruefe_offen(abend):
    if abend["beendet"]:
        raise ValueError("Dieser Abend ist schon abgeschlossen")


def _platz(verbindung, abend_id, sid):
    """Platz eines Spielers; 'fehlt' wenn er nicht dabei ist."""
    zeile = verbindung.execute(
        "SELECT platz FROM abend_spieler WHERE abend_id = ? AND spieler_id = ?",
        (abend_id, sid),
    ).fetchone()
    if zeile is None:
        return "fehlt"
    return zeile[0]


def _buche(verbindung, abend_id, sid, art, betrag_cent, zeitpunkt):
    verbindung.execute(
        "INSERT INTO buchungen (abend_id, spieler_id, art, betrag_cent, zeitpunkt) "
        "VALUES (?, ?, ?, ?, ?)",
        (abend_id, sid, art, betrag_cent, _jetzt_text(zeitpunkt)),
    )


def abende_liste(verbindung):
    """Alle Abende, neueste zuerst."""
    ergebnis = []
    for abend_id, art, zeitpunkt, name, beendet in verbindung.execute(
        "SELECT id, art, zeitpunkt, name, beendet FROM abende ORDER BY id DESC"
    ):
        ergebnis.append({"id": abend_id, "art": art, "zeitpunkt": zeitpunkt,
                         "name": name, "beendet": bool(beendet)})
    return ergebnis


def buchung_loeschen(verbindung, buchung_id):
    """Loescht eine falsch eingetragene Buchung (nur bei offenen Abenden)."""
    zeile = verbindung.execute(
        "SELECT a.beendet FROM buchungen b JOIN abende a ON b.abend_id = a.id "
        "WHERE b.id = ?", (buchung_id,)
    ).fetchone()
    if zeile is None:
        raise ValueError(f"Buchung {buchung_id} gibt es nicht")
    if zeile[0]:
        raise ValueError("Dieser Abend ist schon abgeschlossen")
    verbindung.execute("DELETE FROM buchungen WHERE id = ?", (buchung_id,))
    verbindung.commit()


# ---------------- Turnier ----------------


def neues_turnier(verbindung, buyin_cent, auszahlung=None, rebuy_cent=None,
                  addon_cent=None, name="", zeitpunkt=None):
    """Legt ein Turnier an. Rebuy und Add-on kosten ohne Angabe so viel wie das Buy-in.

    Gibt die abend_id zurueck.
    """
    if auszahlung is None:
        auszahlung = list(STANDARD_AUSZAHLUNG)
    if buyin_cent <= 0:
        raise ValueError("Das Buy-in muss groesser als 0 sein")
    pruefe_auszahlung(auszahlung)
    if rebuy_cent is None:
        rebuy_cent = buyin_cent
    if addon_cent is None:
        addon_cent = buyin_cent
    if rebuy_cent <= 0 or addon_cent <= 0:
        raise ValueError("Rebuy und Add-on muessen groesser als 0 sein")
    cursor = verbindung.execute(
        "INSERT INTO abende (art, zeitpunkt, name, buyin_cent, rebuy_cent, addon_cent, "
        "auszahlung) VALUES ('turnier', ?, ?, ?, ?, ?, ?)",
        (_jetzt_text(zeitpunkt), name, buyin_cent, rebuy_cent, addon_cent,
         json.dumps(auszahlung)),
    )
    verbindung.commit()
    return cursor.lastrowid


def auszahlung_aendern(verbindung, abend_id, auszahlung):
    """Aendert die Auszahlungsstruktur eines laufenden Turniers."""
    _pruefe_offen(_lade_abend(verbindung, abend_id, "turnier"))
    pruefe_auszahlung(auszahlung)
    verbindung.execute("UPDATE abende SET auszahlung = ? WHERE id = ?",
                       (json.dumps(auszahlung), abend_id))
    verbindung.commit()


def turnier_buchen(verbindung, abend_id, name, art, zeitpunkt=None):
    """Bucht ein Buy-in, Rebuy oder Add-on. Der Betrag kommt aus dem Turnier.

    - buyin: einmal pro Spieler, meldet ihn zum Turnier an
    - rebuy: nur wer schon angemeldet ist; wer ausgeschieden war, ist wieder dabei
    - addon: nur wer noch im Spiel ist
    """
    if art not in TURNIER_ARTEN:
        raise ValueError(f"Unbekannte Buchungsart: {art}")
    abend = _lade_abend(verbindung, abend_id, "turnier")
    _pruefe_offen(abend)
    sid = spieler_id(verbindung, name)
    platz = _platz(verbindung, abend_id, sid)

    if art == "buyin":
        if platz != "fehlt":
            raise ValueError(f"{name} hat schon ein Buy-in, bitte Rebuy buchen")
        verbindung.execute(
            "INSERT INTO abend_spieler (abend_id, spieler_id) VALUES (?, ?)", (abend_id, sid)
        )
    elif platz == "fehlt":
        raise ValueError(f"{name} ist noch nicht angemeldet, bitte zuerst Buy-in buchen")
    elif art == "rebuy":
        if platz == 1:
            raise ValueError(f"{name} hat das Turnier schon gewonnen")
        if platz is not None:  # war ausgeschieden: Rebuy holt ihn zurueck
            _ausscheiden_zuruecknehmen(verbindung, abend_id, sid, platz)
    elif art == "addon" and platz is not None:
        raise ValueError(f"{name} ist schon ausgeschieden")

    _buche(verbindung, abend_id, sid, art, abend[art + "_cent"], zeitpunkt)
    verbindung.commit()


def _im_spiel(verbindung, abend_id):
    """spieler_ids aller Spieler, die noch keinen Platz haben."""
    ids = []
    for (sid,) in verbindung.execute(
        "SELECT spieler_id FROM abend_spieler WHERE abend_id = ? AND platz IS NULL",
        (abend_id,),
    ):
        ids.append(sid)
    return ids


def ausscheiden(verbindung, abend_id, name):
    """Ein Spieler scheidet aus. Gibt seinen Platz zurueck.

    Bei 5 Spielern im Spiel wird der Ausscheidende Fuenfter. Bleibt danach nur
    noch einer uebrig, ist er automatisch Erster.
    """
    _pruefe_offen(_lade_abend(verbindung, abend_id, "turnier"))
    sid = spieler_id(verbindung, name)
    im_spiel = _im_spiel(verbindung, abend_id)
    if sid not in im_spiel:
        raise ValueError(f"{name} ist nicht (mehr) im Spiel")
    if len(im_spiel) == 1:
        raise ValueError(f"{name} ist als Letzter uebrig und hat gewonnen")
    platz = len(im_spiel)
    verbindung.execute(
        "UPDATE abend_spieler SET platz = ? WHERE abend_id = ? AND spieler_id = ?",
        (platz, abend_id, sid),
    )
    if len(im_spiel) == 2:
        im_spiel.remove(sid)
        verbindung.execute(
            "UPDATE abend_spieler SET platz = 1 WHERE abend_id = ? AND spieler_id = ?",
            (abend_id, im_spiel[0]),
        )
    verbindung.commit()
    return platz


def _ausscheiden_zuruecknehmen(verbindung, abend_id, sid, platz):
    """Hilfsfunktion: holt einen ausgeschiedenen Spieler zurueck ins Spiel.

    Alle, die nach ihm ausgeschieden sind (kleinere Platzzahl), rutschen einen
    Platz nach hinten, denn er wird ja erst spaeter wieder ausscheiden.
    Beispiel: Anna wird 6., Ben 5., dann macht Anna einen Rebuy -> Ben ist 6.
    Steht schon ein Sieger fest, geht das nur fuer den Zweiten (Sieger und
    Zweiter sind dann beide wieder im Spiel).
    """
    sieger = verbindung.execute(
        "SELECT spieler_id FROM abend_spieler WHERE abend_id = ? AND platz = 1",
        (abend_id,),
    ).fetchone()
    if sieger is not None:
        if platz != 2:
            raise ValueError("Das Turnier ist schon entschieden")
        verbindung.execute(
            "UPDATE abend_spieler SET platz = NULL WHERE abend_id = ? AND platz = 1",
            (abend_id,),
        )
    verbindung.execute(
        "UPDATE abend_spieler SET platz = NULL WHERE abend_id = ? AND spieler_id = ?",
        (abend_id, sid),
    )
    verbindung.execute(
        "UPDATE abend_spieler SET platz = platz + 1 "
        "WHERE abend_id = ? AND platz > 1 AND platz < ?",
        (abend_id, platz),
    )


def ausscheiden_rueckgaengig(verbindung, abend_id, name):
    """Nimmt ein Ausscheiden zurueck (z. B. nach einem Tippfehler)."""
    _pruefe_offen(_lade_abend(verbindung, abend_id, "turnier"))
    sid = spieler_id(verbindung, name)
    platz = _platz(verbindung, abend_id, sid)
    if platz in ["fehlt", None]:
        raise ValueError(f"{name} ist gar nicht ausgeschieden")
    if platz == 1:
        raise ValueError("Bitte den Zweitplatzierten zuruecknehmen")
    _ausscheiden_zuruecknehmen(verbindung, abend_id, sid, platz)
    verbindung.commit()


def turnier_uebersicht(verbindung, abend_id):
    """Alles fuer die Anzeige: Eintraege, Preisgeld, Spieler im Spiel, Auszahlung."""
    abend = _lade_abend(verbindung, abend_id, "turnier")
    anzahl = {"buyin": 0, "rebuy": 0, "addon": 0}
    preisgeld = 0
    for art, betrag in verbindung.execute(
        "SELECT art, betrag_cent FROM buchungen WHERE abend_id = ?", (abend_id,)
    ):
        if art in anzahl:
            anzahl[art] += 1
            preisgeld += betrag

    spieler = []
    namen_nach_platz = {}
    for sid, name, platz in verbindung.execute(
        "SELECT s.id, s.name, a.platz FROM abend_spieler a JOIN spieler s "
        "ON a.spieler_id = s.id WHERE a.abend_id = ? ORDER BY s.name", (abend_id,)
    ):
        eingezahlt, ausgezahlt = _summen(verbindung, abend_id, sid)
        spieler.append({"name": name, "platz": platz, "eingezahlt_cent": eingezahlt,
                        "ausgezahlt_cent": ausgezahlt})
        if platz is not None:
            namen_nach_platz[platz] = name

    betraege = berechne_auszahlung(preisgeld, abend["auszahlung"])
    auszahlung = []
    for i in range(len(betraege)):
        auszahlung.append({"platz": i + 1, "prozent": abend["auszahlung"][i],
                           "betrag_cent": betraege[i],
                           "name": namen_nach_platz.get(i + 1)})

    im_spiel = 0
    for s in spieler:
        if s["platz"] is None:
            im_spiel += 1
    return {
        "id": abend_id,
        "beendet": abend["beendet"],
        "buyin_cent": abend["buyin_cent"],
        "rebuy_cent": abend["rebuy_cent"],
        "addon_cent": abend["addon_cent"],
        "buyins": anzahl["buyin"],
        "rebuys": anzahl["rebuy"],
        "addons": anzahl["addon"],
        "eintraege": anzahl["buyin"] + anzahl["rebuy"],
        "preisgeld_cent": preisgeld,
        "spieler_gesamt": len(spieler),
        "im_spiel": im_spiel,
        "spieler": spieler,
        "auszahlung": auszahlung,
    }


def turnier_abschliessen(verbindung, abend_id, zeitpunkt=None):
    """Bucht die Auszahlungen nach Platzierung und schliesst das Turnier ab.

    Geht erst, wenn ein Sieger feststeht. Gibt die Uebersicht zurueck.
    """
    abend = _lade_abend(verbindung, abend_id, "turnier")
    _pruefe_offen(abend)
    uebersicht = turnier_uebersicht(verbindung, abend_id)
    if uebersicht["im_spiel"] > 0:
        raise ValueError("Es sind noch Spieler im Spiel, erst muss ein Sieger feststehen")
    if len(uebersicht["auszahlung"]) > uebersicht["spieler_gesamt"]:
        raise ValueError("Es werden mehr Plaetze bezahlt als Spieler mitgespielt haben")
    for platz in uebersicht["auszahlung"]:
        sid = spieler_id(verbindung, platz["name"])
        _buche(verbindung, abend_id, sid, "auszahlung", platz["betrag_cent"], zeitpunkt)
    verbindung.execute("UPDATE abende SET beendet = 1 WHERE id = ?", (abend_id,))
    verbindung.commit()
    return turnier_uebersicht(verbindung, abend_id)


# ---------------- Cash Game ----------------


def neues_cashgame(verbindung, name="", zeitpunkt=None):
    """Legt ein Cash Game an und gibt die abend_id zurueck."""
    cursor = verbindung.execute(
        "INSERT INTO abende (art, zeitpunkt, name) VALUES ('cash', ?, ?)",
        (_jetzt_text(zeitpunkt), name),
    )
    verbindung.commit()
    return cursor.lastrowid


def cash_buyin(verbindung, abend_id, name, betrag_cent=CASH_BUYIN_CENT, zeitpunkt=None):
    """Bucht ein Buy-in bzw. einen Nachkauf (beliebig oft, mit Uhrzeit)."""
    _pruefe_offen(_lade_abend(verbindung, abend_id, "cash"))
    if betrag_cent <= 0:
        raise ValueError("Der Betrag muss groesser als 0 sein")
    sid = spieler_id(verbindung, name)
    if _platz(verbindung, abend_id, sid) == "fehlt":
        verbindung.execute(
            "INSERT INTO abend_spieler (abend_id, spieler_id) VALUES (?, ?)", (abend_id, sid)
        )
    _buche(verbindung, abend_id, sid, "buyin", betrag_cent, zeitpunkt)
    verbindung.commit()


def cash_out(verbindung, abend_id, name, betrag_cent, zeitpunkt=None):
    """Traegt den Cash-out eines Spielers ein (ersetzt einen frueheren Eintrag)."""
    _pruefe_offen(_lade_abend(verbindung, abend_id, "cash"))
    if betrag_cent < 0:
        raise ValueError("Der Cash-out darf nicht negativ sein")
    sid = spieler_id(verbindung, name)
    if _platz(verbindung, abend_id, sid) == "fehlt":
        raise ValueError(f"{name} hat in diesem Cash Game kein Buy-in")
    verbindung.execute(
        "DELETE FROM buchungen WHERE abend_id = ? AND spieler_id = ? AND art = 'cashout'",
        (abend_id, sid),
    )
    _buche(verbindung, abend_id, sid, "cashout", betrag_cent, zeitpunkt)
    verbindung.commit()


def cash_uebersicht(verbindung, abend_id):
    """Buy-ins, Cash-outs, Gewinn/Verlust pro Spieler und die Kontrollrechnung.

    Kontrollrechnung: Summe aller Cash-outs minus Summe aller Buy-ins muss 0 sein.
    "stimmt" ist nur True, wenn alle einen Cash-out haben und die Differenz 0 ist.
    """
    abend = _lade_abend(verbindung, abend_id, "cash")
    spieler = []
    offen = []
    summe_buyins = 0
    summe_cashouts = 0
    for sid, name in verbindung.execute(
        "SELECT s.id, s.name FROM abend_spieler a JOIN spieler s ON a.spieler_id = s.id "
        "WHERE a.abend_id = ? ORDER BY s.name", (abend_id,)
    ).fetchall():
        buyins = []
        cashout = None
        for buchung_id, art, betrag, zeitpunkt in verbindung.execute(
            "SELECT id, art, betrag_cent, zeitpunkt FROM buchungen "
            "WHERE abend_id = ? AND spieler_id = ? ORDER BY id", (abend_id, sid)
        ):
            if art == "buyin":
                buyins.append({"id": buchung_id, "betrag_cent": betrag, "zeitpunkt": zeitpunkt})
            elif art == "cashout":
                cashout = betrag
        summe = 0
        for b in buyins:
            summe += b["betrag_cent"]
        summe_buyins += summe
        ergebnis = None
        if cashout is None:
            offen.append(name)
        else:
            summe_cashouts += cashout
            ergebnis = cashout - summe
        spieler.append({"name": name, "buyins": buyins, "summe_buyins_cent": summe,
                        "cashout_cent": cashout, "ergebnis_cent": ergebnis})

    differenz = summe_cashouts - summe_buyins
    return {
        "id": abend_id,
        "beendet": abend["beendet"],
        "spieler": spieler,
        "summe_buyins_cent": summe_buyins,
        "summe_cashouts_cent": summe_cashouts,
        "differenz_cent": differenz,
        "offen": offen,
        "stimmt": len(offen) == 0 and differenz == 0,
    }


def cash_abschliessen(verbindung, abend_id):
    """Schliesst das Cash Game ab. Alle brauchen einen Cash-out.

    Eine Differenz in der Kontrollrechnung verhindert den Abschluss nicht
    (die Oberflaeche warnt), damit man den Abend trotzdem speichern kann.
    """
    _pruefe_offen(_lade_abend(verbindung, abend_id, "cash"))
    uebersicht = cash_uebersicht(verbindung, abend_id)
    if uebersicht["offen"]:
        raise ValueError(f"Cash-out fehlt noch bei: {', '.join(uebersicht['offen'])}")
    verbindung.execute("UPDATE abende SET beendet = 1 WHERE id = ?", (abend_id,))
    verbindung.commit()
    return cash_uebersicht(verbindung, abend_id)


# ---------------- Bilanz ueber alle Abende ----------------


def _summen(verbindung, abend_id, sid):
    """(eingezahlt, ausgezahlt) eines Spielers an einem Abend, in Cent."""
    eingezahlt = 0
    ausgezahlt = 0
    for art, betrag in verbindung.execute(
        "SELECT art, betrag_cent FROM buchungen WHERE abend_id = ? AND spieler_id = ?",
        (abend_id, sid),
    ):
        if art in ["buyin", "rebuy", "addon"]:
            eingezahlt += betrag
        else:
            ausgezahlt += betrag
    return eingezahlt, ausgezahlt


def bilanz(verbindung, art=None):
    """Bilanz pro Spieler ueber alle abgeschlossenen Abende.

    art: None (alle), "turnier" oder "cash".
    Rueckgabe: Liste {name, abende, eingezahlt_cent, ausgezahlt_cent, saldo_cent},
    bester Saldo zuerst.
    """
    sql = ("SELECT s.name, b.abend_id, b.art, b.betrag_cent FROM buchungen b "
           "JOIN abende a ON b.abend_id = a.id JOIN spieler s ON b.spieler_id = s.id "
           "WHERE a.beendet = 1")
    parameter = ()
    if art is not None:
        sql = sql + " AND a.art = ?"
        parameter = (art,)

    werte = {}
    for name, abend_id, buchungsart, betrag in verbindung.execute(sql, parameter):
        if name not in werte:
            werte[name] = {"name": name, "abende": set(), "eingezahlt_cent": 0,
                           "ausgezahlt_cent": 0}
        werte[name]["abende"].add(abend_id)
        if buchungsart in ["buyin", "rebuy", "addon"]:
            werte[name]["eingezahlt_cent"] += betrag
        else:
            werte[name]["ausgezahlt_cent"] += betrag

    ergebnis = []
    for eintrag in werte.values():
        eintrag["abende"] = len(eintrag["abende"])
        eintrag["saldo_cent"] = eintrag["ausgezahlt_cent"] - eintrag["eingezahlt_cent"]
        ergebnis.append(eintrag)
    ergebnis.sort(key=lambda e: e["saldo_cent"], reverse=True)
    return ergebnis
