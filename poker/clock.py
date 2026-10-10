"""Clock Call: Countdown fuer die Aktion eines Spielers.

Ansagen bei einer Startzeit von 45 Sekunden:
    "45 Sekunden", "40", "30", "20", "10", "3", "2", "1", Piepton
Also: Startzeit, dann jede volle Zehnerzahl darunter, dann 3, 2, 1, Piep.

Wie beim Turnier-Timer: Jede Funktion bekommt `jetzt` uebergeben, die Restzeit
wird aus dem Zeitpunkt `ende` berechnet. Der Clock ist unabhaengig vom
Turnier-Timer; beide laufen gleichzeitig.
"""

STANDARD_SEKUNDEN = 30


def ansage_punkte(sekunden):
    """Bei welcher Restzeit (in Sekunden) wird was angesagt?

    Rueckgabe: Liste von (restzeit, text, art), absteigend sortiert.
    art ist "sprache" oder "piep". Beispiel fuer 30:
    [(30, "30 Sekunden", "sprache"), (20, "20", "sprache"), (10, "10", "sprache"),
     (3, "3", "sprache"), (2, "2", "sprache"), (1, "1", "sprache"), (0, "", "piep")]
    """
    if sekunden < 1 or int(sekunden) != sekunden:
        raise ValueError("Die Clock-Zeit muss eine ganze Zahl ab 1 sein")
    sekunden = int(sekunden)
    einheit = "Sekunde" if sekunden == 1 else "Sekunden"
    punkte = [(sekunden, f"{sekunden} {einheit}", "sprache")]
    # Volle Zehner unterhalb der Startzeit
    zehner = (sekunden - 1) // 10 * 10
    while zehner >= 10:
        punkte.append((zehner, str(zehner), "sprache"))
        zehner = zehner - 10
    for rest in [3, 2, 1]:
        if rest < sekunden:
            punkte.append((rest, str(rest), "sprache"))
    punkte.append((0, "", "piep"))
    return punkte


def neue_clock():
    """Ein Clock, der gerade nicht laeuft."""
    return {"laeuft": False, "sekunden": STANDARD_SEKUNDEN, "ende": None,
            "geprueft_bis": None, "spieler": None}


def starte_clock(clock, jetzt, sekunden=STANDARD_SEKUNDEN, spieler=None):
    """Startet den Countdown. Gibt die erste Ansage (die Startzeit) zurueck."""
    punkte = ansage_punkte(sekunden)  # prueft auch die Eingabe
    clock["laeuft"] = True
    clock["sekunden"] = sekunden
    clock["ende"] = jetzt + sekunden
    clock["geprueft_bis"] = jetzt
    clock["spieler"] = spieler
    restzeit, text, art = punkte[0]
    return [{"zeit": jetzt, "text": text, "art": art}]


def stoppe_clock(clock):
    """Bricht den Clock ab (der Spieler hat rechtzeitig gehandelt)."""
    clock["laeuft"] = False
    clock["ende"] = None


def clock_restzeit(clock, jetzt):
    """Verbleibende Sekunden, 0 wenn der Clock nicht laeuft."""
    if not clock["laeuft"]:
        return 0
    return max(0, clock["ende"] - jetzt)


def aktualisiere_clock(clock, jetzt):
    """Gibt alle Ansagen zurueck, die seit der letzten Pruefung faellig wurden.

    Nach dem Piepton ist der Clock vorbei.
    """
    if not clock["laeuft"]:
        return []
    ansagen = []
    # punkte[0] ist die Startansage, die kam schon beim Starten
    for restzeit, text, art in ansage_punkte(clock["sekunden"])[1:]:
        zeitpunkt = clock["ende"] - restzeit
        if clock["geprueft_bis"] < zeitpunkt <= jetzt:
            ansagen.append({"zeit": zeitpunkt, "text": text, "art": art})
    clock["geprueft_bis"] = jetzt
    if jetzt >= clock["ende"]:
        clock["laeuft"] = False
    return ansagen


def clock_anzeige(clock, jetzt):
    """Werte fuer die Anzeige."""
    return {
        "laeuft": clock["laeuft"],
        "sekunden": clock["sekunden"],
        "restzeit": clock_restzeit(clock, jetzt),
        "ende": clock["ende"],
        "spieler": clock["spieler"],
    }
