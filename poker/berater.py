"""KI-Berater: Empfehlung fuer den Spieler, fuer den die KI "mitspielt" (den Helden).

Am echten Tisch gibt man die zwei Karten des Helden ein. Immer wenn er dran
ist, berechnet die KI aus seiner Sicht (eigene Karten, Board, Pot, Verlauf der
Hand) und den Profilen der Gegner aus der Datenbank, was sie tun wuerde -
inklusive Begruendung. Die Oberflaeche zeigt das an; uebernommen wird es nur,
wenn man auf "Uebernehmen" tippt.

Die Empfehlung ist fuer dieselbe Spielsituation immer gleich: Der Zufall
(Equity-Simulation, Bluffs) bekommt einen festen Startwert aus Hand und Verlauf.
"""

import random

from poker import live
from poker.bots import erstelle_sicht
from poker.ki import erkenne_typ, ki_bewertung
from poker.profile import berechne_statistik
from poker.tisch import situation_von

BERATER_DURCHLAEUFE = 2000  # genauer als in der Simulation; am Tisch zaehlt Genauigkeit


def _runde_auf_chips(betrag, schritt, minimum, maximum):
    """Raise-Betrag auf zahlbare Chips runden (Vielfache von `schritt`), in den Grenzen."""
    gerundet = int(betrag / schritt + 0.5) * schritt
    return max(minimum, min(gerundet, maximum))


def bewerte_situation(zustand, held, karten, erkennung, schritt,
                      durchlaeufe=BERATER_DURCHLAEUFE):
    """Was wuerde die KI in dieser Situation tun? (fuer Live-Tisch und Lerntisch)

    erkennung: Funktion name -> Typ-Erkennung des Gegners (erkenne_typ).
    schritt: kleinster Chip (Raise wird darauf gerundet).
    Rueckgabe wie ki_bewertung, Raise-Betrag auf Chips gerundet.
    """
    sicht = erstelle_sicht(zustand, held, karten)
    erkennungen = [erkennung(gegner) for gegner in sicht["aktive_gegner"]]

    # Fester Startwert: gleiche Situation -> gleiche Empfehlung
    zufall = random.Random(f"{zustand['hand_id']}-{len(zustand['verlauf'])}-{len(zustand['board'])}")
    bewertung = ki_bewertung(sicht, erkennungen, zufall, durchlaeufe)

    if bewertung["aktion"] == "raise":
        maximal = sicht["maximal"]
        minimum = min(live.mindest_erhoehung(zustand), maximal)
        betrag = _runde_auf_chips(bewertung["betrag"], schritt, minimum, maximal)
        bewertung["betrag"] = betrag
        if betrag == maximal:
            bewertung["gruende"].append("Das ist dein ganzer Stack (All-in)")
    return bewertung


def empfehlung(verbindung, abend, durchlaeufe=BERATER_DURCHLAEUFE):
    """Was soll der Held jetzt tun?

    Rueckgabe: {"aktion": "fold"/"check"/"call"/"raise", "betrag": cent oder None,
                "equity", "fair", "pot_odds", "gegner": [...], "gruende": [...]}
    """
    if abend["hand"] is None:
        raise ValueError("Es laeuft gerade keine Hand")
    zustand = abend["hand"]["zustand"]
    held = abend.get("held")
    if held is None:
        raise ValueError("Es ist kein Spieler fuer die KI ausgewaehlt")
    karten = abend["hand"].get("held_karten")
    if not karten:
        raise ValueError(f"Bitte zuerst die Karten von {held} eingeben")
    if zustand["am_zug"] != held:
        raise ValueError(f"{held} ist gerade nicht dran")

    def erkennung(gegner):
        # Nur abgeschlossene Haende zaehlen - die laufende Hand also nicht
        return erkenne_typ(berechne_statistik(verbindung, gegner))

    bewertung = bewerte_situation(zustand, held, karten, erkennung, abend["small_blind"],
                                  durchlaeufe)
    # Merken, damit beim Handeln protokolliert werden kann, ob sie befolgt wurde
    abend["hand"]["letzte_empfehlung"] = {
        "situation": situation_von(zustand), "aktion": bewertung["aktion"],
        "betrag": bewertung["betrag"], "equity": bewertung["equity"],
        "pot_odds": bewertung["pot_odds"]}
    return bewertung
