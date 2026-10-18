"""Hand-Analyse: gespeicherte Haende im Nachhinein durchrechnen, plus Odds-Rechner.

Pro Strasse (Preflop, Flop, Turn, River) fuer jeden Spieler mit bekannten Karten:
- "wirklich":  Equity gegen die echten Karten der Gegner - nur wenn alle noch
               aktiven Gegner ihre Karten gezeigt haben (am Lerntisch immer)
- "zufall":    Equity gegen zufaellige Haende (was man am Tisch ganz grob schaetzt)
- "bereich":   Equity gegen den geschaetzten Handbereich jedes Gegners (wie die KI:
               aus Spielertyp und seinen Aktionen in der Hand)
Dazu Outs (welche Karten noch helfen) und bei jeder Entscheidung, bei der Geld
zu bezahlen war, die Pot Odds: Hat sich der Call gelohnt?

Ab dem Flop wird "wirklich" exakt ausgezaehlt (alle moeglichen Turn-/River-Karten),
preflop per Monte-Carlo. Fester Zufalls-Startwert pro Hand -> gleiche Zahlen bei
jedem Aufruf.
"""

import itertools
import random

from poker.bewertung import (DRILLING, HANDART_NAMEN, HOECHSTE_KARTE, PAAR, VIERLING,
                             ZWEI_PAARE, bewerte_hand, finde_gewinner)
from poker.deck import erzeuge_deck, zaehle_raenge
from poker.equity import equity_gegen_bereiche, equity_gegen_zufall
from poker.ki import erkenne_typ, schaetze_bereich
from poker.profile import berechne_statistik, text_zu_karten

BOARD_AUF_STRASSE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
STRASSEN = ["preflop", "flop", "turn", "river"]
PREFLOP_DURCHLAEUFE = 5000   # "wirklich" vor dem Flop (danach exakt)
SCHAETZ_DURCHLAEUFE = 1500   # "zufall" und "bereich"


# ---------------- Equity und Outs ----------------


def _restdeck(bekannte):
    bekannt = set(bekannte)
    return [karte for karte in erzeuge_deck() if karte not in bekannt]


def equity_bekannt(haende, board, zufall=random, durchlaeufe=PREFLOP_DURCHLAEUFE):
    """Equity bekannter Haende gegeneinander (Split Pot anteilig).

    Fehlen hoechstens 2 Board-Karten, wird jede Moeglichkeit ausgezaehlt (exakt),
    sonst per Monte-Carlo.
    """
    if len(haende) < 2:
        raise ValueError("Es braucht mindestens zwei Haende")
    bekannte = list(board) + [karte for hand in haende for karte in hand]
    if len(set(bekannte)) != len(bekannte):
        raise ValueError("Eine Karte ist doppelt vergeben")
    rest = _restdeck(bekannte)
    fehlende = 5 - len(board)
    if fehlende <= 2:
        moeglichkeiten = itertools.combinations(rest, fehlende)
    else:
        moeglichkeiten = (zufall.sample(rest, fehlende) for _ in range(durchlaeufe))
    punkte = [0.0] * len(haende)
    anzahl = 0
    for dazu in moeglichkeiten:
        komplett = list(board) + list(dazu)
        gewinner = finde_gewinner([bewerte_hand(hand + komplett) for hand in haende])
        for position in gewinner:
            punkte[position] += 1 / len(gewinner)
        anzahl += 1
    return [p / anzahl for p in punkte]


def _kategorie(karten):
    """Handart von 4 bis 7 Karten (bei 4 Karten nur Paare/Drilling/Vierling moeglich)."""
    if len(karten) >= 5:
        return bewerte_hand(karten)[0]
    anzahlen = sorted(zaehle_raenge(karten).values(), reverse=True)
    if anzahlen[0] == 4:
        return VIERLING
    if anzahlen[0] == 3:
        return DRILLING
    if anzahlen[0] == 2:
        return ZWEI_PAARE if len(anzahlen) > 1 and anzahlen[1] == 2 else PAAR
    return HOECHSTE_KARTE


def outs(hand, board, gegner_haende=None):
    """Welche naechste Karte hilft? (nur auf Flop und Turn)

    Mit bekannten Gegnerhaenden: Liegst du hinten, sind Outs die Karten, mit
    denen du danach vorne liegst. Liegst du vorne, werden die Karten gezeigt,
    mit denen du ueberholt wirst ("gefaehrlich").
    Ohne Gegnerhaende: Karten, die deine Handart verbessern - aber nur, wenn die
    Verbesserung von deinen Karten kommt (nicht nur vom Board).
    Rueckgabe: {"art": "outs"/"gefaehrlich"/"verbesserung", "anzahl", "gruppen":
               [{"handart", "karten"}]} oder None (Preflop/River); bei "gefaehrlich"
               gibt es nur eine Gruppe mit handart None.
    """
    if len(board) not in (3, 4):
        return None
    gegner_haende = gegner_haende or []
    bekannte = list(hand) + list(board) + [k for g in gegner_haende for k in g]
    rest = _restdeck(bekannte)
    gruppen = {}

    if gegner_haende:
        def bin_vorne(karten_board):
            mein = bewerte_hand(hand + karten_board)
            bester = max(bewerte_hand(g + karten_board) for g in gegner_haende)
            return mein > bester

        vorne = bin_vorne(list(board))
        for karte in rest:
            neu = list(board) + [karte]
            danach = bin_vorne(neu)
            if danach != vorne:
                name = HANDART_NAMEN[bewerte_hand(hand + neu)[0]]
                gruppen.setdefault(name, []).append(karte)
        art = "gefaehrlich" if vorne else "outs"
        if vorne:
            # Gefaehrliche Karten: die eigene Handart danach sagt nichts aus
            gruppen = {None: [k for karten in gruppen.values() for k in karten]}
    else:
        jetzt = bewerte_hand(hand + list(board))[0]
        for karte in rest:
            neu = list(board) + [karte]
            danach = bewerte_hand(hand + neu)[0]
            if danach > jetzt and danach > _kategorie(neu):
                gruppen.setdefault(HANDART_NAMEN[danach], []).append(karte)
        art = "verbesserung"

    liste = [{"handart": name, "karten": karten} for name, karten in gruppen.items()]
    liste.sort(key=lambda g: -len(g["karten"]))
    return {"art": art, "anzahl": sum(len(g["karten"]) for g in liste), "gruppen": liste}


# ---------------- Gespeicherte Hand nachrechnen ----------------


def _erkennung(name, datenbanken):
    """Typ-Erkennung eines Spielers aus der ersten Datenbank, die ihn kennt."""
    for db in datenbanken:
        try:
            return erkenne_typ(berechne_statistik(db, name))
        except ValueError:
            continue
    return {"typ": "unbekannt", "sicherheit": 0.0, "haende": 0, "abstaende": {}}


def lade_hand(verbindung, hand_id):
    """Rohdaten einer gespeicherten Hand."""
    zeile = verbindung.execute(
        "SELECT zeitpunkt, small_blind, big_blind, board, abgeschlossen FROM haende WHERE id = ?",
        (hand_id,)).fetchone()
    if zeile is None:
        raise ValueError(f"Hand {hand_id} gibt es nicht")
    zeitpunkt, small_blind, big_blind, board, abgeschlossen = zeile
    spieler = []
    for name, karten, stack, investiert, gewonnen in verbindung.execute(
        "SELECT s.name, t.handkarten, t.stack, t.investiert, t.gewonnen FROM teilnehmer t "
        "JOIN spieler s ON t.spieler_id = s.id WHERE t.hand_id = ? ORDER BY t.sitzplatz",
        (hand_id,)
    ):
        spieler.append({"name": name, "karten": text_zu_karten(karten), "stack": stack,
                        "ergebnis": None if gewonnen is None else gewonnen - investiert})
    aktionen = [{"name": n, "strasse": s, "aktion": a, "betrag": b} for n, s, a, b in
                verbindung.execute(
                    "SELECT s.name, a.strasse, a.aktion, a.betrag FROM aktionen a "
                    "JOIN spieler s ON a.spieler_id = s.id WHERE a.hand_id = ? ORDER BY a.id",
                    (hand_id,))]
    return {"hand_id": hand_id, "zeitpunkt": zeitpunkt, "small_blind": small_blind,
            "big_blind": big_blind, "board": text_zu_karten(board) or [],
            "abgeschlossen": bool(abgeschlossen), "spieler": spieler, "aktionen": aktionen}


def _equity_werte(name, karten, aktiv, bekannt, board, verlauf, strasse, erkennungen, zufall):
    """Die drei Equity-Werte eines Spielers (wirklich ist None, wenn Karten fehlen)."""
    gegner = [n for n in aktiv if n != name]
    werte = {"wirklich": None, "zufall": None, "bereich": None}
    if not gegner:
        return werte
    if all(n in bekannt for n in gegner):
        haende = [karten] + [bekannt[n] for n in gegner]
        werte["wirklich"] = equity_bekannt(haende, board, zufall)[0]
    werte["zufall"] = equity_gegen_zufall(karten, board, len(gegner), SCHAETZ_DURCHLAEUFE, zufall)
    bereiche = [schaetze_bereich(erkennungen[n], verlauf, n, strasse) for n in gegner]
    werte["bereich"] = equity_gegen_bereiche(karten, board, bereiche, SCHAETZ_DURCHLAEUFE, zufall)
    werte["bereiche"] = dict(zip(gegner, bereiche))
    return werte


def _urteil(aktion, equity, pot_odds):
    """Kurze Einschaetzung einer Entscheidung, bei der Geld zu bezahlen war."""
    if equity is None or pot_odds is None:
        return None
    if aktion == "call":
        return "lohnend" if equity >= pot_odds else "zu teuer"
    if aktion == "fold":
        return "Fold zu vorsichtig?" if equity >= pot_odds + 0.1 else "Fold ok"
    return None


def analysiere_hand(verbindung, hand_id, profil_dbs=()):
    """Rechnet eine gespeicherte Hand Strasse fuer Strasse durch.

    profil_dbs: weitere Datenbanken fuer die Gegnerprofile (z. B. die Heimrunde
    fuer den Lerntisch); zuerst wird dort gesucht, dann in `verbindung`.
    Rueckgabe: {"hand_id", "datum", "small_blind", "big_blind", "namen", "karten",
                "board", "ergebnis", "strassen": [{"strasse", "board", "pot", "aktiv",
                "equity": {name: {...}}, "outs": {name: {...}}, "entscheidungen": [...]}]}
    """
    hand = lade_hand(verbindung, hand_id)
    zufall = random.Random(f"handanalyse-{hand_id}")
    namen = [s["name"] for s in hand["spieler"]]
    bekannt = {s["name"]: s["karten"] for s in hand["spieler"] if s["karten"]}
    stack = {s["name"]: s["stack"] if s["stack"] is not None else float("inf")
             for s in hand["spieler"]}
    datenbanken = list(profil_dbs) + [verbindung]
    erkennungen = {n: _erkennung(n, datenbanken) for n in namen}

    # Blinds: Platz 0 Small Blind, Platz 1 Big Blind
    einsatz = {n: 0 for n in namen}
    einsatz[namen[0]] = min(hand["small_blind"], stack[namen[0]])
    einsatz[namen[1]] = min(hand["big_blind"], stack[namen[1]])
    investiert_vorher = {n: 0 for n in namen}   # aus frueheren Strassen
    aktiv = list(namen)
    verlauf = []
    strassen = []
    aktionen = list(hand["aktionen"])

    for strasse in STRASSEN:
        board = hand["board"][:BOARD_AUF_STRASSE[strasse]]
        if len(board) < BOARD_AUF_STRASSE[strasse] or len(aktiv) < 2:
            break
        if strasse != "preflop":
            for n in namen:
                investiert_vorher[n] += einsatz[n]
                einsatz[n] = 0
        hoechster = max(einsatz.values())
        abschnitt = {"strasse": strasse, "board": board, "aktiv": list(aktiv),
                     "pot": sum(investiert_vorher.values()) + sum(einsatz.values()),
                     "equity": {}, "outs": {}, "entscheidungen": []}
        for name in aktiv:
            if name in bekannt:
                abschnitt["equity"][name] = _equity_werte(
                    name, bekannt[name], aktiv, bekannt, board, verlauf, strasse,
                    erkennungen, zufall)
                gegner_karten = [bekannt[n] for n in aktiv if n != name and n in bekannt]
                alle_bekannt = len(gegner_karten) == len(aktiv) - 1
                abschnitt["outs"][name] = outs(bekannt[name], board,
                                              gegner_karten if alle_bekannt else None)

        while aktionen and aktionen[0]["strasse"] == strasse:
            a = aktionen.pop(0)
            name = a["name"]
            rest = stack[name] - investiert_vorher[name] - einsatz[name]
            zu_callen = min(hoechster - einsatz[name], rest)
            pot = sum(investiert_vorher.values()) + sum(einsatz.values())
            entscheidung = {"name": name, "aktion": a["aktion"], "betrag": a["betrag"],
                            "pot": pot, "zu_callen": zu_callen, "pot_odds": None,
                            "equity": None, "urteil": None}
            if zu_callen > 0 and name in bekannt:
                entscheidung["pot_odds"] = zu_callen / (pot + zu_callen)
                werte = _equity_werte(name, bekannt[name], aktiv, bekannt, board, verlauf,
                                      strasse, erkennungen, zufall)
                entscheidung["equity"] = werte
                massstab = werte["wirklich"] if werte["wirklich"] is not None else werte["bereich"]
                entscheidung["urteil"] = _urteil(a["aktion"], massstab, entscheidung["pot_odds"])
            elif zu_callen > 0:
                entscheidung["pot_odds"] = zu_callen / (pot + zu_callen)
            abschnitt["entscheidungen"].append(entscheidung)

            if a["aktion"] == "fold":
                aktiv.remove(name)
            elif a["betrag"]:
                einsatz[name] = a["betrag"]
                hoechster = max(hoechster, a["betrag"])
            verlauf.append(dict(a))
        strassen.append(abschnitt)

    return {
        "hand_id": hand_id,
        "datum": hand["zeitpunkt"][:16].replace("T", " "),
        "small_blind": hand["small_blind"],
        "big_blind": hand["big_blind"],
        "namen": namen,
        "karten": bekannt,
        "board": hand["board"],
        "ergebnis": {s["name"]: s["ergebnis"] for s in hand["spieler"]},
        "abgeschlossen": hand["abgeschlossen"],
        "strassen": strassen,
    }


def hand_liste(verbindung, name=None, anzahl=50):
    """Abgeschlossene Haende mit mindestens einer bekannten Hand, neueste zuerst.

    name: nur Haende, in denen dieser Spieler dabei war.
    """
    sql = ("SELECT h.id, h.zeitpunkt, h.big_blind, h.board FROM haende h "
           "WHERE h.abgeschlossen = 1 AND EXISTS (SELECT 1 FROM teilnehmer t "
           "WHERE t.hand_id = h.id AND t.handkarten IS NOT NULL)")
    parameter = []
    if name:
        sql += (" AND EXISTS (SELECT 1 FROM teilnehmer t JOIN spieler s ON t.spieler_id = s.id "
                "WHERE t.hand_id = h.id AND s.name = ?)")
        parameter.append(name)
    sql += " ORDER BY h.id DESC LIMIT ?"
    parameter.append(anzahl)
    liste = []
    for hand_id, zeitpunkt, big_blind, board in verbindung.execute(sql, parameter).fetchall():
        teilnehmer = verbindung.execute(
            "SELECT s.name, t.handkarten, t.investiert, t.gewonnen FROM teilnehmer t "
            "JOIN spieler s ON t.spieler_id = s.id WHERE t.hand_id = ? ORDER BY t.sitzplatz",
            (hand_id,)).fetchall()
        eintrag = {"hand_id": hand_id, "datum": zeitpunkt[:16].replace("T", " "),
                   "big_blind": big_blind, "board": text_zu_karten(board) or [],
                   "namen": [t[0] for t in teilnehmer],
                   "bekannt": [t[0] for t in teilnehmer if t[1]],
                   "pot": sum(t[2] or 0 for t in teilnehmer),
                   "gewinner": [t[0] for t in teilnehmer if (t[3] or 0) > 0],
                   "ergebnis": None, "karten": None}
        for n, karten, investiert, gewonnen in teilnehmer:
            if n == name:
                eintrag["karten"] = text_zu_karten(karten)
                if gewonnen is not None:
                    eintrag["ergebnis"] = gewonnen - investiert
        liste.append(eintrag)
    return liste


# ---------------- Odds-Rechner (freie Eingabe) ----------------


def odds_rechner(haende, board, zufalls_gegner=1, seed=0):
    """Equity und Outs fuer frei eingegebene Haende.

    Eine Hand: gegen `zufalls_gegner` zufaellige Haende. Zwei oder mehr Haende:
    gegeneinander (wirklich).
    Rueckgabe: {"haende": [{"karten", "equity", "handart", "outs"}], "art"}.
    """
    if not 1 <= len(haende) <= 9:
        raise ValueError("Bitte 1 bis 9 Haende eingeben")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("Das Board hat 0, 3, 4 oder 5 Karten")
    for hand in haende:
        if len(hand) != 2:
            raise ValueError("Jede Hand braucht genau 2 Karten")
    alle = list(board) + [k for hand in haende for k in hand]
    if len(set(alle)) != len(alle):
        raise ValueError("Eine Karte ist doppelt vergeben")
    zufall = random.Random(seed)
    ergebnis = []
    if len(haende) == 1:
        if not 1 <= zufalls_gegner <= 8:
            raise ValueError("Bitte 1 bis 8 zufaellige Gegner")
        equity = [equity_gegen_zufall(haende[0], board, zufalls_gegner, 5000, zufall)]
        art = "zufall"
    else:
        equity = equity_bekannt(haende, board, zufall, 10000)
        art = "wirklich"
    for i, hand in enumerate(haende):
        andere = [h for j, h in enumerate(haende) if j != i]
        ergebnis.append({
            "karten": hand,
            "equity": equity[i],
            "handart": HANDART_NAMEN[bewerte_hand(hand + list(board))[0]] if len(board) >= 3 else None,
            "outs": outs(hand, board, andere or None),
        })
    return {"art": art, "haende": ergebnis}


# ---------------- Tisch-Rechner: Equity Strasse fuer Strasse ----------------


def equity_gemischt(haende, board, zufalls_gegner=0, zufall=random, durchlaeufe=5000):
    """Equity bekannter Haende, wenn zusaetzlich `zufalls_gegner` Spieler mit
    unbekannten Karten dabei sind (deren Karten werden in jedem Durchlauf zufaellig
    ausgeteilt). Ohne unbekannte Gegner wie equity_bekannt (ab dem Flop exakt).

    Rueckgabe: (equity pro bekannter Hand, equity aller Unbekannten zusammen).
    """
    if zufalls_gegner == 0:
        return equity_bekannt(haende, board, zufall, durchlaeufe), 0.0
    bekannte = list(board) + [k for hand in haende for k in hand]
    if len(set(bekannte)) != len(bekannte):
        raise ValueError("Eine Karte ist doppelt vergeben")
    rest = _restdeck(bekannte)
    fehlende = 5 - len(board)
    punkte = [0.0] * (len(haende) + 1)   # letzter Eintrag: alle Unbekannten
    for _ in range(durchlaeufe):
        gezogen = zufall.sample(rest, 2 * zufalls_gegner + fehlende)
        komplett = list(board) + gezogen[2 * zufalls_gegner:]
        werte = [bewerte_hand(hand + komplett) for hand in haende]
        werte += [bewerte_hand(gezogen[2 * i:2 * i + 2] + komplett) for i in range(zufalls_gegner)]
        gewinner = finde_gewinner(werte)
        for position in gewinner:
            punkte[min(position, len(haende))] += 1 / len(gewinner)
    return [p / durchlaeufe for p in punkte[:-1]], punkte[-1] / durchlaeufe


def odds_verlauf(haende, board, zufalls_gegner=0, seed=0):
    """Equity aller Haende Strasse fuer Strasse: Preflop, dann mit Flop, Turn, River
    (so weit das Board eingegeben ist).

    haende: bekannte Haende (je 2 Karten), zufalls_gegner: Spieler ohne bekannte Karten.
    Rueckgabe: {"strassen": [{"strasse", "board", "zufall_equity",
                "haende": [{"equity", "handart", "outs"}]}]}
    """
    if not haende:
        raise ValueError("Bitte mindestens einer Hand Karten geben")
    if len(haende) + zufalls_gegner < 2:
        raise ValueError("Es braucht mindestens zwei Spieler")
    if len(haende) + zufalls_gegner > 9:
        raise ValueError("Hoechstens 9 Spieler")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("Das Board hat 0, 3, 4 oder 5 Karten")
    for hand in haende:
        if len(hand) != 2:
            raise ValueError("Jede Hand braucht genau 2 Karten")
    alle = list(board) + [k for hand in haende for k in hand]
    if len(set(alle)) != len(alle):
        raise ValueError("Eine Karte ist doppelt vergeben")

    zufall = random.Random(seed)
    strassen = []
    for strasse in STRASSEN:
        anzahl = BOARD_AUF_STRASSE[strasse]
        if anzahl > len(board):
            break
        teil = list(board[:anzahl])
        equity, zufall_equity = equity_gemischt(haende, teil, zufalls_gegner, zufall)
        eintraege = []
        for i, hand in enumerate(haende):
            andere = [h for j, h in enumerate(haende) if j != i]
            eintraege.append({
                "equity": equity[i],
                "handart": HANDART_NAMEN[bewerte_hand(hand + teil)[0]] if teil else None,
                # Gegen bekannte Gegner nur, wenn keiner unbekannt ist
                "outs": outs(hand, teil, andere if andere and not zufalls_gegner else None),
            })
        strassen.append({"strasse": strasse, "board": teil, "zufall_equity": zufall_equity,
                         "haende": eintraege})
    return {"strassen": strassen}
