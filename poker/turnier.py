"""Turnier-Timer: Blindstruktur, Levels, Pausen, Ansagen und Vorlagen.

Ein Level ist ein Dictionary:
    {"small_blind": 100, "big_blind": 200, "ante": 25, "minuten": 15}
Eine Pause ist auch ein Level:
    {"pause": True, "minuten": 10}

Zeit: Jede Funktion bekommt `jetzt` uebergeben (Sekunden, z. B. time.time()).
Die Restzeit wird immer aus dem Zeitpunkt `ende` berechnet, nie durch
Herunterzaehlen. Dadurch stimmt der Timer auch, wenn das Handy kurz im
Hintergrund war, und Tests koennen einfach einen anderen Zeitpunkt uebergeben.

Ansagen: Funktionen, bei denen etwas angesagt werden soll, geben eine Liste
von Ansagen zurueck: {"zeit": zeitpunkt, "text": "...", "art": "sprache"}.
Vorgelesen wird nur in der Oberflaeche.
"""

import json

# Unsere Turnier-Chips: 25, 100, 500, 1000. Startstack 3000.
TURNIER_CHIPS = [25, 100, 500, 1000]
STARTSTACK = 3000

WARNUNG_SEKUNDEN = 60  # Hinweis eine Minute vor Levelende


def level(small_blind, big_blind, minuten, ante=0):
    """Erzeugt ein Spiel-Level."""
    return {"small_blind": small_blind, "big_blind": big_blind,
            "ante": ante, "minuten": minuten}


def pause(minuten):
    """Erzeugt eine Pause."""
    return {"pause": True, "minuten": minuten}


STANDARD_VORLAGEN = {
    "Schnelles Turnier": [
        level(25, 50, 12), level(50, 100, 12), level(75, 150, 12),
        level(100, 200, 12), pause(10),
        level(150, 300, 12, 25), level(200, 400, 12, 50), level(300, 600, 12, 75),
        level(400, 800, 12, 100), pause(10),
        level(500, 1000, 12, 100), level(700, 1400, 12, 200),
        level(1000, 2000, 12, 300), level(1500, 3000, 12, 500),
    ],
    "Langer Abend": [
        level(25, 50, 20), level(50, 100, 20), level(75, 150, 20),
        level(100, 200, 20), level(150, 300, 20), pause(15),
        level(200, 400, 20, 25), level(250, 500, 20, 50), level(300, 600, 20, 75),
        level(400, 800, 20, 100), pause(15),
        level(500, 1000, 20, 100), level(600, 1200, 20, 200),
        level(800, 1600, 20, 200), level(1000, 2000, 20, 300),
        level(1500, 3000, 20, 500), level(2000, 4000, 20, 500),
    ],
}


# ---------------- Blindstruktur ----------------


def ist_pause(lvl):
    return lvl.get("pause", False)


def pruefe_struktur(struktur, kleinster_chip=TURNIER_CHIPS[0]):
    """Prueft eine Blindstruktur. Wirft ValueError mit verstaendlicher Meldung."""
    if len(struktur) == 0:
        raise ValueError("Die Blindstruktur braucht mindestens ein Level")
    if ist_pause(struktur[0]):
        raise ValueError("Das Turnier kann nicht mit einer Pause beginnen")
    for i in range(len(struktur)):
        lvl = struktur[i]
        nummer = i + 1
        if lvl.get("minuten", 0) <= 0:
            raise ValueError(f"Eintrag {nummer}: Dauer muss groesser als 0 sein")
        if ist_pause(lvl):
            continue
        sb = lvl.get("small_blind", 0)
        bb = lvl.get("big_blind", 0)
        ante = lvl.get("ante", 0)
        if sb <= 0 or bb < sb:
            raise ValueError(f"Eintrag {nummer}: Small Blind muss > 0 und <= Big Blind sein")
        if ante < 0:
            raise ValueError(f"Eintrag {nummer}: Ante darf nicht negativ sein")
        for betrag in [sb, bb, ante]:
            if betrag % kleinster_chip != 0:
                raise ValueError(f"Eintrag {nummer}: {betrag} ist mit {kleinster_chip}er-Chips "
                                 "nicht zahlbar")


def level_nummer(struktur, index):
    """Nummer eines Spiel-Levels ("Level 5"); Pausen zaehlen nicht mit.

    Fuer eine Pause gibt es None.
    """
    if ist_pause(struktur[index]):
        return None
    nummer = 0
    for i in range(index + 1):
        if not ist_pause(struktur[i]):
            nummer = nummer + 1
    return nummer


def ansage_text(struktur, index):
    """Text fuer die Ansage beim Wechsel in dieses Level."""
    lvl = struktur[index]
    if ist_pause(lvl):
        return f"Pause. {lvl['minuten']} Minuten."
    text = (f"Level {level_nummer(struktur, index)}. "
            f"Blinds {lvl['small_blind']} und {lvl['big_blind']}")
    if lvl.get("ante", 0) > 0:
        text = text + f", Ante {lvl['ante']}"
    return text + "."


def warnung_text(struktur, index):
    """Text fuer den Hinweis eine Minute vor Levelende."""
    if index + 1 < len(struktur) and ist_pause(struktur[index + 1]):
        return "Noch eine Minute bis zur Pause."
    if ist_pause(struktur[index]):
        return "Noch eine Minute Pause."
    return "Noch eine Minute in diesem Level."


def _ansage(zeit, text):
    return {"zeit": zeit, "text": text, "art": "sprache"}


# ---------------- Timer ----------------


def neuer_timer(struktur):
    """Erzeugt einen Timer (noch nicht gestartet) am Anfang von Level 1."""
    pruefe_struktur(struktur)
    return {
        "struktur": [dict(lvl) for lvl in struktur],
        "index": 0,
        "laeuft": False,
        "ende": None,                                 # Zeitpunkt Levelende (wenn laeuft)
        "rest": struktur[0]["minuten"] * 60,          # Restsekunden (wenn angehalten)
        "geprueft_bis": None,                         # bis wann Ansagen erzeugt wurden
        "vorbei": False,                              # letztes Level abgelaufen
    }


def _dauer(timer, index):
    return timer["struktur"][index]["minuten"] * 60


def restzeit(timer, jetzt):
    """Verbleibende Sekunden im aktuellen Level (nie unter 0)."""
    if timer["laeuft"]:
        return max(0, timer["ende"] - jetzt)
    return timer["rest"]


def starte(timer, jetzt):
    """Startet den Timer bzw. setzt ihn nach einer Pause fort."""
    if timer["laeuft"]:
        return []
    if timer["vorbei"]:
        raise ValueError("Das letzte Level ist abgelaufen")
    erster_start = timer["geprueft_bis"] is None
    timer["laeuft"] = True
    timer["ende"] = jetzt + timer["rest"]
    timer["geprueft_bis"] = jetzt
    if erster_start:
        return [_ansage(jetzt, ansage_text(timer["struktur"], timer["index"]))]
    return []


def pausiere(timer, jetzt):
    """Haelt den Timer an. Vorher faellige Ansagen werden noch zurueckgegeben."""
    ansagen = aktualisiere(timer, jetzt)
    if timer["laeuft"]:
        timer["rest"] = restzeit(timer, jetzt)
        timer["laeuft"] = False
        timer["ende"] = None
    return ansagen


def aktualisiere(timer, jetzt):
    """Prueft, was seit der letzten Pruefung passiert ist.

    Wechselt (auch mehrfach) ins naechste Level, wenn die Zeit abgelaufen ist,
    und gibt die faelligen Ansagen zurueck. Jede Ansage hat den Zeitpunkt,
    zu dem sie eigentlich faellig war. So kann die Oberflaeche alte Ansagen
    (z. B. nach dem Hintergrund) weglassen.
    """
    ansagen = []
    if not timer["laeuft"]:
        return ansagen
    struktur = timer["struktur"]
    while True:
        # Hinweis eine Minute vor Levelende
        warn_zeit = timer["ende"] - WARNUNG_SEKUNDEN
        if (_dauer(timer, timer["index"]) > WARNUNG_SEKUNDEN
                and timer["geprueft_bis"] < warn_zeit <= jetzt):
            ansagen.append(_ansage(warn_zeit, warnung_text(struktur, timer["index"])))
        if timer["ende"] > jetzt:
            break
        # Level ist abgelaufen
        level_ende = timer["ende"]
        if timer["index"] + 1 >= len(struktur):
            timer["laeuft"] = False
            timer["vorbei"] = True
            timer["rest"] = 0
            timer["ende"] = None
            ansagen.append(_ansage(level_ende, "Das letzte Level ist abgelaufen."))
            break
        timer["index"] = timer["index"] + 1
        timer["ende"] = level_ende + _dauer(timer, timer["index"])
        timer["geprueft_bis"] = level_ende
        ansagen.append(_ansage(level_ende, ansage_text(struktur, timer["index"])))
    timer["geprueft_bis"] = jetzt
    return ansagen


def _springe_zu(timer, jetzt, index):
    """Hilfsfunktion: wechselt in ein Level, dessen Zeit wieder voll ist."""
    timer["index"] = index
    timer["vorbei"] = False
    if timer["laeuft"]:
        timer["ende"] = jetzt + _dauer(timer, index)
        timer["geprueft_bis"] = jetzt
    else:
        timer["rest"] = _dauer(timer, index)
    return [_ansage(jetzt, ansage_text(timer["struktur"], index))]


def naechstes_level(timer, jetzt):
    """Springt sofort ins naechste Level."""
    aktualisiere(timer, jetzt)
    if timer["index"] + 1 >= len(timer["struktur"]):
        raise ValueError("Es gibt kein weiteres Level")
    return _springe_zu(timer, jetzt, timer["index"] + 1)


def vorheriges_level(timer, jetzt):
    """Springt zurueck ins vorherige Level."""
    aktualisiere(timer, jetzt)
    if timer["index"] == 0:
        raise ValueError("Es gibt kein vorheriges Level")
    return _springe_zu(timer, jetzt, timer["index"] - 1)


def zeit_anpassen(timer, jetzt, sekunden):
    """Veraendert die Restzeit im laufenden Level (z. B. +60 oder -60).

    Weniger als 0 geht nicht; bei 0 wechselt das Level bei der naechsten Pruefung.
    Wird Zeit dazugegeben, kommt der Minuten-Hinweis spaeter noch einmal.
    """
    ansagen = aktualisiere(timer, jetzt)
    if timer["laeuft"]:
        timer["ende"] = max(jetzt, timer["ende"] + sekunden)
    else:
        timer["rest"] = max(0, timer["rest"] + sekunden)
    return ansagen


def zeit_bis_pause(timer, jetzt):
    """Sekunden bis zur naechsten Pause, None wenn keine mehr kommt (oder gerade Pause ist)."""
    struktur = timer["struktur"]
    if ist_pause(struktur[timer["index"]]):
        return None
    summe = restzeit(timer, jetzt)
    for i in range(timer["index"] + 1, len(struktur)):
        if ist_pause(struktur[i]):
            return summe
        summe = summe + _dauer(timer, i)
    return None


def anzeige(timer, jetzt):
    """Alle Werte fuer die Anzeige in einem Dictionary."""
    struktur = timer["struktur"]
    index = timer["index"]
    lvl = struktur[index]
    naechstes = None
    if index + 1 < len(struktur):
        naechstes = dict(struktur[index + 1])
        naechstes["nummer"] = level_nummer(struktur, index + 1)
    return {
        "index": index,
        "nummer": level_nummer(struktur, index),
        "pause": ist_pause(lvl),
        "small_blind": lvl.get("small_blind"),
        "big_blind": lvl.get("big_blind"),
        "ante": lvl.get("ante", 0),
        "minuten": lvl["minuten"],
        "restzeit": restzeit(timer, jetzt),
        "ende": timer["ende"],
        "laeuft": timer["laeuft"],
        "vorbei": timer["vorbei"],
        "naechstes": naechstes,
        "zeit_bis_pause": zeit_bis_pause(timer, jetzt),
    }


# ---------------- Vorlagen (SQLite) ----------------


def vorlage_speichern(verbindung, name, struktur):
    """Speichert eine Blindstruktur unter einem Namen (ueberschreibt gleichnamige)."""
    name = name.strip()
    if name == "":
        raise ValueError("Die Vorlage braucht einen Namen")
    pruefe_struktur(struktur)
    verbindung.execute(
        "INSERT OR REPLACE INTO blindvorlagen (name, levels) VALUES (?, ?)",
        (name, json.dumps(struktur)),
    )
    verbindung.commit()


def vorlage_laden(verbindung, name):
    """Laedt eine Vorlage: erst aus der Datenbank, sonst aus den Standard-Vorlagen."""
    zeile = verbindung.execute(
        "SELECT levels FROM blindvorlagen WHERE name = ?", (name,)
    ).fetchone()
    if zeile is not None:
        return json.loads(zeile[0])
    if name in STANDARD_VORLAGEN:
        return [dict(lvl) for lvl in STANDARD_VORLAGEN[name]]
    raise ValueError(f"Keine Vorlage mit dem Namen '{name}'")


def vorlagen_namen(verbindung):
    """Namen aller Vorlagen: Standard-Vorlagen und eigene, alphabetisch."""
    namen = set(STANDARD_VORLAGEN.keys())
    for (name,) in verbindung.execute("SELECT name FROM blindvorlagen"):
        namen.add(name)
    return sorted(namen)


def vorlage_loeschen(verbindung, name):
    """Loescht eine eigene Vorlage (Standard-Vorlagen bleiben immer da)."""
    verbindung.execute("DELETE FROM blindvorlagen WHERE name = ?", (name,))
    verbindung.commit()
