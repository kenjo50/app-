"""Tests fuer poker/ki.py: Typ-Erkennung, Bereiche, Entscheidungen."""

import random

from poker.deck import lies_karten
from poker.ki import (
    PROTOTYPEN,
    PROTOTYPEN_NACH_GROESSE,
    abstand,
    aggressions_anteil,
    erkenne_typ,
    ki_entscheidung,
    prototypen_fuer,
    schaetze_bereich,
)


def statistik(vpip, pfr, aggression, haende, aktionen=100):
    """Kuenstliche Statistik wie von berechne_statistik."""
    aggressiv = round(aggression * aktionen)
    return {"haende": haende, "vpip": vpip, "pfr": pfr, "af": None, "bb_pro_100": None,
            "aggressiv": aggressiv, "calls": aktionen - aggressiv}


def wie(typ, haende=300):
    vpip, pfr, aggression = PROTOTYPEN[typ]
    return statistik(vpip, pfr, aggression, haende)


SICHER = {"felsen": {"typ": "felsen", "sicherheit": 0.9},
          "station": {"typ": "station", "sicherheit": 0.9},
          "unbekannt": {"typ": "unbekannt", "sicherheit": 0.0}}


# ---------- Typ-Erkennung ----------


def test_prototypen_fuer_jede_tischgroesse():
    assert set(PROTOTYPEN_NACH_GROESSE) == set(range(2, 10))
    for prototypen in PROTOTYPEN_NACH_GROESSE.values():
        assert set(prototypen) == {"felsen", "station", "maniac", "tag"}
        for werte in prototypen.values():
            assert all(0 <= w <= 1 for w in werte)
            assert werte[1] <= werte[0]   # PFR nie groesser als VPIP


def test_prototypen_fuer_tischgroessen():
    assert prototypen_fuer(None) == PROTOTYPEN
    assert prototypen_fuer({}) == PROTOTYPEN
    assert prototypen_fuer({3: 50}) == {t: tuple(round(w, 3) for w in v)
                                        for t, v in PROTOTYPEN_NACH_GROESSE[3].items()}
    # Groessen ausserhalb der Messung wie die naechste gemessene
    assert prototypen_fuer({10: 5}) == prototypen_fuer({9: 5})
    # Mischung 75 % / 25 %
    gemischt = prototypen_fuer({2: 30, 6: 10})
    erwartet = 0.75 * PROTOTYPEN_NACH_GROESSE[2]["maniac"][0] + 0.25 * PROTOTYPEN_NACH_GROESSE[6]["maniac"][0]
    assert abs(gemischt["maniac"][0] - erwartet) < 0.001


def test_wenige_aktionen_zaehlen_weniger():
    prototyp = (0.10, 0.07, 0.70)
    werte = (0.10, 0.07, 1.0)
    # Aggression 100 % aus 3 Aktionen ist kaum aussagekraeftig, aus 300 sehr wohl
    assert abstand(werte, prototyp, (200, 200, 3)) < abstand(werte, prototyp, (200, 200, 300))
    assert abstand(werte, prototyp, (200, 200, 300)) < abstand(werte, prototyp)


def test_felsen_mit_wenig_flops_bleibt_felsen():
    # Heads-up: Felsen, der nur 3-mal nach dem Flop gehandelt hat (alles Bets)
    vpip, pfr, _ = PROTOTYPEN_NACH_GROESSE[2]["felsen"]
    s = statistik(vpip, pfr, 1.0, 200, aktionen=3)
    s["tischgroessen"] = {2: 200}
    assert erkenne_typ(s)["typ"] == "felsen"


def test_erkennung_nutzt_die_tischgroesse():
    # Werte genau wie der heads-up-Prototyp: mit der Tischgroesse sicherer erkannt
    for typ in PROTOTYPEN:
        vpip, pfr, aggression = PROTOTYPEN_NACH_GROESSE[2][typ]
        s = statistik(vpip, pfr, aggression, 300)
        s["tischgroessen"] = {2: 300}
        e = erkenne_typ(s)
        assert e["typ"] == typ
        assert e["prototyp"] == prototypen_fuer({2: 300})[typ]
        assert e["abstaende"][typ] < 1e-6


def test_jeder_prototyp_wird_erkannt():
    for typ in PROTOTYPEN:
        e = erkenne_typ(wie(typ))
        assert e["typ"] == typ
        assert e["sicherheit"] > 0.6


def test_zu_wenige_haende_unbekannt():
    e = erkenne_typ(wie("station", haende=15))
    assert e["typ"] == "unbekannt" and e["sicherheit"] == 0


def test_sicherheit_waechst_mit_handzahl():
    s30 = erkenne_typ(wie("station", 30))["sicherheit"]
    s100 = erkenne_typ(wie("station", 100))["sicherheit"]
    s500 = erkenne_typ(wie("station", 500))["sicherheit"]
    assert 0 < s30 < s100 < s500 < 1


def test_unklarer_fall_ist_unsicherer():
    # Genau zwischen Felsen und TAG
    f, t = PROTOTYPEN["felsen"], PROTOTYPEN["tag"]
    mitte = statistik((f[0] + t[0]) / 2, (f[1] + t[1]) / 2, (f[2] + t[2]) / 2, 300)
    assert erkenne_typ(mitte)["sicherheit"] < erkenne_typ(wie("felsen"))["sicherheit"] / 2


def test_passt_zu_keinem_typ():
    # Wie der Mischtyp: vor dem Flop aggressiv, danach passiv
    e = erkenne_typ(statistik(0.25, 0.20, 0.35, 400))
    assert e["sicherheit"] < 0.1


def test_aggressions_anteil():
    assert aggressions_anteil({"aggressiv": 3, "calls": 1}) == 0.75
    assert aggressions_anteil({"aggressiv": 0, "calls": 0}) is None


# ---------- Bereiche ----------


def raise_verlauf(name):
    return [{"name": name, "strasse": "preflop", "aktion": "raise", "betrag": 6}]


def test_bereich_nach_typ_und_sicherheit():
    verlauf = raise_verlauf("G")
    assert schaetze_bereich(SICHER["unbekannt"], verlauf, "G", "preflop") == 20
    felsen_pfr = PROTOTYPEN["felsen"][1] * 100
    assert schaetze_bereich({"typ": "felsen", "sicherheit": 1.0}, verlauf, "G", "preflop") \
        == round(felsen_pfr, 1)
    halb = schaetze_bereich({"typ": "felsen", "sicherheit": 0.5}, verlauf, "G", "preflop")
    assert halb == round((felsen_pfr + 20) / 2, 1)   # vorsichtig: halb Typ, halb Standard
    # Mit dem Prototyp aus der Erkennung (passend zur Tischgroesse)
    erkennung = {"typ": "maniac", "sicherheit": 1.0, "prototyp": (0.4, 0.25, 0.8)}
    assert schaetze_bereich(erkennung, verlauf, "G", "preflop") == 25


def test_bereich_ohne_freiwillige_aktion():
    assert schaetze_bereich(SICHER["felsen"], [], "G", "preflop") == 100


def test_bet_nach_dem_flop_engt_ein():
    verlauf = [{"name": "G", "strasse": "preflop", "aktion": "call", "betrag": 2},
               {"name": "G", "strasse": "flop", "aktion": "bet", "betrag": 4}]
    vorher = schaetze_bereich(SICHER["station"], verlauf[:1], "G", "flop")
    nachher = schaetze_bereich(SICHER["station"], verlauf, "G", "flop")
    assert nachher < vorher / 2   # setzt eine Station, hat sie meistens etwas


# ---------- Entscheidungen ----------


def sicht(**werte):
    grund = {
        "name": "KI", "handkarten": lies_karten("As Jd"), "board": [], "strasse": "preflop",
        "pot": 10, "zu_callen": 7, "hoechster": 7, "einsatz": 0, "stack": 200, "maximal": 200,
        "mindest_erhoehung": 12, "darf_erhoehen": True, "erlaubt": ["fold", "call", "raise"],
        "gegner": 1, "big_blind": 2, "verlauf": raise_verlauf("G"), "aktive_gegner": ["G"],
    }
    grund.update(werte)
    return grund


def test_gegen_felsen_raise_aufgeben_gegen_unbekannt_mitgehen():
    # A9o gegen eine Erhoehung auf 6 (Pot Odds 40 %):
    # Ein Felsen erhoeht nur mit den besten ca. 8 % -> Equity ca. 34 % -> fold.
    # Bei einem Unbekannten (Standardbereich 20 %) ca. 46 % -> mitgehen.
    s = sicht(handkarten=lies_karten("As 9d"), pot=9, zu_callen=6, hoechster=6)
    for seed in range(20):
        assert ki_entscheidung(s, [SICHER["felsen"]], random.Random(seed))[0] == "fold"
        assert ki_entscheidung(s, [SICHER["unbekannt"]], random.Random(seed))[0] != "fold"


def test_keine_bluffs_gegen_station():
    # Schwache Hand, nichts zu zahlen: gegen eine Station nie bluffen
    s = sicht(handkarten=lies_karten("7c 2d"), board=lies_karten("Ks 9h 4d"), strasse="flop",
              zu_callen=0, hoechster=0, mindest_erhoehung=2, erlaubt=["check", "raise"],
              verlauf=[])
    zufall = random.Random(2)
    for i in range(100):
        assert ki_entscheidung(s, [SICHER["station"]], zufall)[0] == "check"


def test_bluffs_gegen_felsen():
    s = sicht(handkarten=lies_karten("7c 2d"), board=lies_karten("Ks 9h 4d"), strasse="flop",
              zu_callen=0, hoechster=0, mindest_erhoehung=2, erlaubt=["check", "raise"],
              verlauf=[])
    zufall = random.Random(3)
    aktionen = [ki_entscheidung(s, [SICHER["felsen"]], zufall)[0] for i in range(200)]
    anteil = aktionen.count("raise") / len(aktionen)
    assert 0.15 < anteil < 0.5   # ca. 35 % x Sicherheit 0.9


def test_vorsichtig_bei_unsicherheit():
    # Bei Sicherheit 0 wird nie geblufft
    s = sicht(handkarten=lies_karten("7c 2d"), board=lies_karten("Ks 9h 4d"), strasse="flop",
              zu_callen=0, hoechster=0, mindest_erhoehung=2, erlaubt=["check", "raise"],
              verlauf=[])
    unsicherer_felsen = {"typ": "felsen", "sicherheit": 0.0}
    zufall = random.Random(4)
    for i in range(100):
        assert ki_entscheidung(s, [unsicherer_felsen], zufall)[0] == "check"


def test_ki_in_der_simulation():
    from poker.simulation import erstelle_aufstellung, oeffne_simulationsdatenbank, simuliere_bots
    db = oeffne_simulationsdatenbank(":memory:")
    zufall = random.Random(5)
    bots = erstelle_aufstellung(["ki", "station", "felsen"], zufall, db)
    simuliere_bots(db, bots, 60, zufall=zufall)
    profile = bots["Ki 1"].profile
    assert set(profile) == {"Station 1", "Felsen 1"}
    assert profile["Station 1"]["haende"] >= 20
