"""Lerntisch: digital ueben gegen Bots, die echte Mitspieler nachahmen.

- Gegner: echte Spieler aus der Heimrunde-Datenbank oder Typ-Bots (Felsen, ...).
  Ein echter Spieler mit mindestens 20 Haenden wird mit seinen eigenen Werten
  nachgeahmt (VPIP, PFR, Aggression); mit weniger Haenden spielt sein Bot wie
  der naechstliegende Typ.
- Gespielt wird mit Spielgeld nach den Regeln aus live.py, gespeichert in einer
  eigenen Datenbank (lerntisch.db) - die echten Statistiken bleiben sauber.
- Die Bots handeln Schritt fuer Schritt (schritt), damit die Oberflaeche
  jede Aktion einzeln zeigen kann.
- KI-Tipp erst NACH der eigenen Entscheidung: Vor dem Ausfuehren wird berechnet,
  was die KI getan haette, gezeigt wird es danach (gleich oder anders).

Der Spielzustand ist ein Dictionary (wie der Live-Abend in tisch.py); die
Bots werden bei Bedarf aus ihren gespeicherten Werten neu gebaut.
"""

from poker import live
from poker.berater import bewerte_situation
from poker.bewertung import bewerte_hand, handart_name
from poker.bots import erstelle_sicht
from poker.deck import austeilen, erzeuge_deck
from poker.ki import (MINDEST_HAENDE, TYP_NAMEN, abstand, aggressions_anteil, erkenne_typ,
                      prototypen_fuer)
from poker.profile import berechne_statistik, empfehlung_speichern, handkarten_speichern
from poker.tisch import befolgt, raise_vorschlaege
from poker.typen import GRUNDTYPEN, bot_aus_werten

SMALL_BLIND = 10      # Cent
BIG_BLIND = 10        # Cent (in der Heimrunde 10/10)
STARTSTACK = 1000     # 10 Euro Spielgeld; wer pleite ist, bekommt neue 10 Euro
MAX_GEGNER = 8
TIPP_DURCHLAEUFE = 1000


def _begrenze(wert, minimum, maximum):
    return max(minimum, min(maximum, wert))


# ---------------- Bots, die echte Spieler nachahmen ----------------


def naechster_typ(statistik):
    """Der Grundtyp, der am besten passt - auch bei wenigen Haenden (ohne Sicherheit)."""
    if statistik["haende"] == 0 or statistik["vpip"] is None:
        return "tag"
    werte = (statistik["vpip"], statistik["pfr"], aggressions_anteil(statistik))
    prototypen = prototypen_fuer(statistik.get("tischgroessen"))
    return min(prototypen, key=lambda typ: abstand(werte, prototypen[typ]))


def nachahmer_werte(statistik):
    """Typ-Bot-Werte, mit denen ein Bot einen echten Spieler nachspielt.

    Rueckgabe: (typ, werte, nachgeahmt). nachgeahmt = False heisst: zu wenige
    Haende, der Bot spielt genau wie der Grundtyp.
    """
    if statistik["haende"] < MINDEST_HAENDE or statistik["vpip"] is None:
        typ = naechster_typ(statistik)
        return typ, dict(GRUNDTYPEN[typ]), False

    erkennung = erkenne_typ(statistik)
    typ = erkennung["typ"]
    grund = GRUNDTYPEN[typ]
    prototyp = erkennung["prototyp"]
    werte = dict(grund)
    # Die Bot-Einstellung "vpip" ist ein Handbereich, gemessen kommt etwas weniger
    # heraus (z. B. Bereich 10 % -> gemessen 9 %). Darum mit dem Verhaeltnis
    # Einstellung / Messung des Typs umrechnen.
    werte["vpip"] = _begrenze(statistik["vpip"] * grund["vpip"] / prototyp[0], 3, 95)
    werte["pfr"] = _begrenze(statistik["pfr"] * grund["pfr"] / max(prototyp[1], 0.01),
                             1, werte["vpip"])
    aggression = aggressions_anteil(statistik)
    if aggression is not None and prototyp[2] > 0:
        faktor = aggression / prototyp[2]
        werte["aggression"] = _begrenze(grund["aggression"] * faktor, 0, 1)
        werte["bluff"] = _begrenze(grund["bluff"] * faktor, 0, 1)
    return typ, werte, True


def bot_fuer_spieler(echt_db, name):
    """Beschreibung eines Bots, der den echten Spieler `name` nachahmt."""
    statistik = berechne_statistik(echt_db, name)
    typ, werte, nachgeahmt = nachahmer_werte(statistik)
    if nachgeahmt:
        info = f"spielt wie {name} ({statistik['haende']} Haende, {TYP_NAMEN[typ]})"
    else:
        info = f"erst {statistik['haende']} Haende - spielt wie ein {TYP_NAMEN[typ]}"
    return {"name": name, "vorbild": name, "typ": typ, "werte": werte, "info": info}


def bot_fuer_typ(typ, nummer):
    """Beschreibung eines reinen Typ-Bots (z. B. "Felsen-Bot 1")."""
    if typ not in GRUNDTYPEN:
        raise ValueError(f"Unbekannter Typ: {typ}")
    return {"name": f"{TYP_NAMEN[typ]}-Bot {nummer}", "vorbild": None, "typ": typ,
            "werte": dict(GRUNDTYPEN[typ]), "info": f"Typ-Bot {TYP_NAMEN[typ]}"}


# ---------------- Spiel anlegen ----------------


def neues_spiel(echt_db, held, gegner):
    """Legt einen Lerntisch an.

    held: dein Name. gegner: Liste von {"spieler": name} (echter Spieler) oder
    {"typ": "felsen"/...} (Typ-Bot), 1 bis 8 Eintraege.
    """
    held = (held or "").strip()
    if not held:
        raise ValueError("Bitte deinen Namen angeben")
    if not 1 <= len(gegner) <= MAX_GEGNER:
        raise ValueError(f"Bitte 1 bis {MAX_GEGNER} Gegner auswaehlen")
    bots = []
    typ_nummer = {}
    for eintrag in gegner:
        if eintrag.get("spieler"):
            name = eintrag["spieler"]
            if name == held:
                raise ValueError("Du kannst nicht gegen dich selbst spielen")
            if name in [b["name"] for b in bots]:
                raise ValueError(f"{name} sitzt schon am Tisch")
            try:
                bots.append(bot_fuer_spieler(echt_db, name))
            except ValueError:
                raise ValueError(f"Einen Spieler '{name}' gibt es nicht") from None
        else:
            typ = eintrag.get("typ")
            typ_nummer[typ] = typ_nummer.get(typ, 0) + 1
            bots.append(bot_fuer_typ(typ, typ_nummer[typ]))
    plaetze = [held] + [b["name"] for b in bots]
    return {
        "held": held,
        "plaetze": plaetze,          # Reihenfolge der naechsten Hand (Small Blind zuerst)
        "bots": {b["name"]: b for b in bots},
        "small_blind": SMALL_BLIND,
        "big_blind": BIG_BLIND,
        "stacks": {name: STARTSTACK for name in plaetze},
        "eingekauft": {name: STARTSTACK for name in plaetze},
        "hand": None,
        "sitzung": {"haende": 0, "entscheidungen": 0, "gleich": 0,
                    "pro_strasse": {}, "abweichungen": {}},
    }


# ---------------- Eine Hand spielen ----------------


def starte_hand(lern_db, spiel, zufall):
    """Teilt eine neue Hand aus. Wer pleite ist, bekommt vorher neue 10 Euro."""
    if spiel["hand"] is not None and spiel["hand"]["ergebnis"] is None:
        raise ValueError("Die Hand laeuft noch")
    for name in spiel["plaetze"]:
        if spiel["stacks"][name] < spiel["big_blind"]:
            spiel["stacks"][name] += STARTSTACK
            spiel["eingekauft"][name] += STARTSTACK
    deck = erzeuge_deck()
    zufall.shuffle(deck)
    karten = {name: austeilen(deck, 2) for name in spiel["plaetze"]}
    zustand = live.starte_hand(lern_db, list(spiel["plaetze"]), spiel["small_blind"],
                               spiel["big_blind"], dict(spiel["stacks"]))
    for name, handkarten in karten.items():
        handkarten_speichern(lern_db, zustand["hand_id"], name, handkarten)
    spiel["hand"] = {"zustand": zustand, "karten": karten, "deck": deck, "tipps": [],
                     "letzter_tipp": None, "ergebnis": None}
    return spiel["hand"]


def phase(spiel):
    """"keine_hand", "held" (du bist dran), "bots" (Bots/Karten als Naechstes) oder "ende"."""
    hand = spiel["hand"]
    if hand is None:
        return "keine_hand"
    if hand["ergebnis"] is not None:
        return "ende"
    zustand = hand["zustand"]
    if not zustand["beendet"] and not live.setzrunde_abgeschlossen(zustand) \
            and zustand["am_zug"] == spiel["held"]:
        return "held"
    return "bots"


def schritt(lern_db, spiel, zufall):
    """Ein Schritt ohne dich: ein Bot handelt, neue Karten kommen oder die Hand
    wird abgerechnet. Gibt kurz zurueck, was passiert ist."""
    if phase(spiel) != "bots":
        return {"art": "nichts"}
    hand = spiel["hand"]
    zustand = hand["zustand"]
    if zustand["beendet"]:
        _abrechnen(lern_db, spiel)
        return {"art": "ende"}
    if live.setzrunde_abgeschlossen(zustand):
        if zustand["strasse"] == "river":
            live.beende_hand(zustand)
            _abrechnen(lern_db, spiel)
            return {"art": "ende"}
        neue = live.NAECHSTE_STRASSE[zustand["strasse"]]
        live.naechste_strasse(lern_db, zustand, austeilen(hand["deck"], live.NEUE_BOARD_KARTEN[neue]))
        return {"art": "karten", "strasse": neue}
    name = zustand["am_zug"]
    bot = bot_aus_werten(spiel["bots"][name]["werte"])
    aktion, betrag = bot(erstelle_sicht(zustand, name, hand["karten"][name]), zufall)
    gespielt, gespielt_betrag = live.verarbeite_aktion(lern_db, zustand, name, aktion, betrag)
    return {"art": "aktion", "name": name, "aktion": gespielt, "betrag": gespielt_betrag}


def _erkennung_fuer(echt_db, lern_db, spiel):
    """So kennt die KI die Gegner: echte Spieler aus der Heimrunde-Datenbank
    (wie am echten Tisch), Typ-Bots aus den bisherigen Lerntisch-Haenden."""
    def erkennung(name):
        bot = spiel["bots"].get(name, {})
        db = echt_db if bot.get("vorbild") else lern_db
        try:
            return erkenne_typ(berechne_statistik(db, bot.get("vorbild") or name))
        except ValueError:
            return {"typ": "unbekannt", "sicherheit": 0.0, "haende": 0, "abstaende": {}}
    return erkennung


def held_aktion(lern_db, echt_db, spiel, grundaktion, betrag=None,
                durchlaeufe=TIPP_DURCHLAEUFE):
    """Deine Entscheidung. Vorher wird (verdeckt) berechnet, was die KI getan
    haette; danach wird beides verglichen. Gibt den Tipp zurueck."""
    if phase(spiel) != "held":
        raise ValueError("Du bist gerade nicht dran")
    hand = spiel["hand"]
    zustand = hand["zustand"]
    held = spiel["held"]
    strasse = zustand["strasse"]
    bewertung = bewerte_situation(zustand, held, hand["karten"][held],
                                  _erkennung_fuer(echt_db, lern_db, spiel),
                                  spiel["small_blind"], durchlaeufe)
    gespielt, gespielt_betrag = live.verarbeite_aktion(
        lern_db, zustand, held, grundaktion, None if betrag is None else int(betrag))

    gleich = befolgt(bewertung["aktion"], gespielt)
    empfehlung_speichern(lern_db, zustand["hand_id"], held, strasse, bewertung["aktion"],
                         bewertung["betrag"], gespielt, gespielt_betrag, gleich,
                         bewertung["equity"], bewertung["pot_odds"])
    tipp = {"strasse": strasse, "ki": bewertung["aktion"], "ki_betrag": bewertung["betrag"],
            "du": gespielt, "du_betrag": gespielt_betrag, "gleich": gleich,
            "equity": bewertung["equity"], "pot_odds": bewertung["pot_odds"],
            "gruende": bewertung["gruende"]}
    hand["tipps"].append(tipp)
    hand["letzter_tipp"] = tipp

    sitzung = spiel["sitzung"]
    sitzung["entscheidungen"] += 1
    sitzung["gleich"] += 1 if gleich else 0
    pro = sitzung["pro_strasse"].setdefault(strasse, [0, 0])
    pro[0] += 1
    pro[1] += 1 if gleich else 0
    if not gleich:
        schluessel = f"{bewertung['aktion']}>{gespielt}"
        sitzung["abweichungen"][schluessel] = sitzung["abweichungen"].get(schluessel, 0) + 1
    return tipp


def _abrechnen(lern_db, spiel):
    """Hand zu Ende: Gewinner bestimmen (Bots zeigen beim Showdown immer), Stacks
    uebernehmen, Button weitergeben."""
    hand = spiel["hand"]
    zustand = hand["zustand"]
    gezeigte = {}
    handarten = {}
    if len(zustand["aktiv"]) == 1:
        gewinner_pro_pot = live.gewinner_ohne_showdown(zustand)
    else:
        for name in zustand["aktiv"]:
            gezeigte[name] = hand["karten"][name]
            handarten[name] = handart_name(bewerte_hand(hand["karten"][name] + zustand["board"]))
        gewinner_pro_pot = live.showdown_gewinner(zustand, gezeigte)
    gewinn = live.abrechnen(lern_db, zustand, gewinner_pro_pot, gezeigte)
    spiel["stacks"] = dict(zustand["stacks"])
    gewinner = []
    for liste in gewinner_pro_pot:
        for name in liste:
            if name not in gewinner:
                gewinner.append(name)
    hand["ergebnis"] = {"gewinn": gewinn, "gezeigt": gezeigte, "handarten": handarten,
                        "gewinner": gewinner}
    spiel["sitzung"]["haende"] += 1
    spiel["plaetze"] = live.rotiere(spiel["plaetze"])


# ---------------- Anzeige und Zusammenfassung ----------------


def zusammenfassung(spiel):
    """Bilanz der Sitzung: Ergebnis und wie oft du wie die KI gespielt hast."""
    sitzung = spiel["sitzung"]
    held = spiel["held"]
    ergebnis = spiel["stacks"][held] - spiel["eingekauft"][held]
    if spiel["hand"] is not None and spiel["hand"]["ergebnis"] is None:
        # Laufende Hand: was schon im Pot liegt, ist (noch) weg
        ergebnis = spiel["hand"]["zustand"]["stacks"][held] - spiel["eingekauft"][held]
    bb = ergebnis / spiel["big_blind"]
    entscheidungen = sitzung["entscheidungen"]
    abweichungen = sorted(sitzung["abweichungen"].items(), key=lambda e: -e[1])
    return {
        "haende": sitzung["haende"],
        "ergebnis_cent": ergebnis,
        "ergebnis_bb": bb,
        "bb_pro_100": bb / sitzung["haende"] * 100 if sitzung["haende"] else None,
        "entscheidungen": entscheidungen,
        "gleich": sitzung["gleich"],
        "quote": sitzung["gleich"] / entscheidungen if entscheidungen else None,
        "pro_strasse": {s: {"entscheidungen": n, "gleich": g, "quote": g / n}
                        for s, (n, g) in sitzung["pro_strasse"].items()},
        "abweichungen": [{"ki": k.split(">")[0], "du": k.split(">")[1], "anzahl": n}
                         for k, n in abweichungen[:3]],
    }


def anzeige(spiel):
    """Alles fuer die Oberflaeche. Karten der Bots nur, wenn sie gezeigt wurden."""
    daten = {
        "held": spiel["held"],
        "phase": phase(spiel),
        "small_blind": spiel["small_blind"],
        "big_blind": spiel["big_blind"],
        "bots": [{"name": b["name"], "typ": b["typ"], "info": b["info"]}
                 for b in spiel["bots"].values()],
        "stacks": spiel["stacks"],
        "sitzung": zusammenfassung(spiel),
        "hand": None,
    }
    hand = spiel["hand"]
    if hand is None:
        return daten
    zustand = hand["zustand"]
    held = spiel["held"]
    ergebnis = hand["ergebnis"]
    sichtbar = {held: hand["karten"][held]}
    if ergebnis is not None:
        sichtbar.update(ergebnis["gezeigt"])
    daten["hand"] = {
        "hand_id": zustand["hand_id"],
        "namen": zustand["namen"],
        "aktiv": zustand["aktiv"],
        "strasse": zustand["strasse"],
        "board": zustand["board"],
        "pot": live.pot(zustand),
        "einsaetze": zustand["einsaetze"],
        "stacks": zustand["stacks"],
        "allin": [n for n in zustand["aktiv"] if live.ist_allin(zustand, n)],
        "am_zug": None if zustand["beendet"] else zustand["am_zug"],
        "verlauf": zustand["verlauf"][-10:],
        "karten": sichtbar,
        "letzter_tipp": hand["letzter_tipp"],
        "ergebnis": ergebnis,
    }
    if daten["phase"] == "held":
        daten["hand"]["erlaubt"] = live.erlaubte_aktionen(zustand, held)
        daten["hand"]["zu_callen"] = min(live.zu_callen(zustand, held), zustand["stacks"][held])
        if "raise" in daten["hand"]["erlaubt"]:
            daten["hand"]["raise"] = raise_vorschlaege(zustand, held, spiel["small_blind"])
    return daten
