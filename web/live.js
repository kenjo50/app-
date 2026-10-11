// Live-Modus in der Web-App: Haende am Tisch mitschreiben.
// Die Logik liegt im Python-Kern (poker/tisch.py + poker/live.py); hier wird nur
// angezeigt und bedient. Hilfsfunktionen ($, api, euro, esc, meldung, bestaetigt)
// kommen aus app.js. Alle Betraege vom Server sind Cent.

"use strict";

// ---------------- Karten ----------------

const FARB_INFO = {
  Pik: { zeichen: "♠", code: "s", rot: false },
  Herz: { zeichen: "♥", code: "h", rot: true },
  Karo: { zeichen: "♦", code: "d", rot: true },
  Kreuz: { zeichen: "♣", code: "c", rot: false },
};
const FARB_REIHENFOLGE = ["Pik", "Herz", "Karo", "Kreuz"];
const RAENGE_ABSTEIGEND = [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2];
const RANG_ANZEIGE = { 14: "A", 13: "K", 12: "D", 11: "B", 10: "10" };
const RANG_CODE = { 14: "A", 13: "K", 12: "Q", 11: "J", 10: "T" };

function kartenSchluessel(karte) {
  // [14, "Pik"] -> "14Pik" (zum Vergleichen)
  return karte[0] + karte[1];
}

function kartenCode(karte) {
  // [14, "Pik"] -> "As" (so versteht es der Server)
  return (RANG_CODE[karte[0]] || String(karte[0])) + FARB_INFO[karte[1]].code;
}

function karteHtml(karte, klein = false) {
  const info = FARB_INFO[karte[1]];
  const rang = RANG_ANZEIGE[karte[0]] || karte[0];
  return `<span class="karte ${info.rot ? "rot" : ""} ${klein ? "klein-karte" : ""}">${rang}${info.zeichen}</span>`;
}

function kartenraster(benutzt, ausgewaehlt) {
  // Pro Farbe zwei Reihen (A bis 8, 7 bis 2), damit die Tasten auf dem Handy
  // breit genug fuer den Daumen sind. benutzt/ausgewaehlt: Mengen von Schluesseln.
  let html = '<div class="kartenraster">';
  for (const farbe of FARB_REIHENFOLGE) {
    if (farbe !== FARB_REIHENFOLGE[0]) html += '<div class="farbende"></div>';
    for (const rang of RAENGE_ABSTEIGEND) {
      const karte = [rang, farbe];
      const schluessel = kartenSchluessel(karte);
      const info = FARB_INFO[farbe];
      const klassen = [info.rot ? "rot" : "", ausgewaehlt.has(schluessel) ? "gewaehlt" : ""].join(" ");
      html += `<button class="rasterkarte ${klassen}" data-karte="${rang}|${farbe}"
        ${benutzt.has(schluessel) ? "disabled" : ""}>${RANG_ANZEIGE[rang] || rang}${info.zeichen}</button>`;
    }
  }
  return html + "</div>";
}

function karteAusKnopf(knopf) {
  const [rang, farbe] = knopf.dataset.karte.split("|");
  return [Number(rang), farbe];
}

// Cent -> "1,50" fuer Eingabefelder und den Server
function centAlsEingabe(cent) {
  return (cent / 100).toFixed(2).replace(".", ",");
}

// ---------------- Zustand der Oberflaeche ----------------

let liveStand = null;          // letzte Antwort von /api/abend
let startAuswahl = [];         // Abend einrichten: [{name, stack}]
let boardAuswahl = [];         // gerade angetippte Board-Karten
let raiseOffen = false;        // Raise-Feld aufgeklappt?
let showdown = neuerShowdown();

function neuerShowdown() {
  // gezeigt: {name: [karte, karte]}, zeigtNicht: Menge, ziel: fuer wen gerade Karten gewaehlt werden
  return { handId: null, gezeigt: {}, zeigtNicht: new Set(), ziel: null, vorschau: null, vonHand: {} };
}

async function ladeLive() {
  const daten = await api("/api/abend");
  zeichneLive(daten.abend);
}

function uebernimm(antwort) {
  // Jede Antwort des Servers enthaelt den neuen Stand
  zeichneLive(antwort.abend);
  return antwort;
}

// ---------------- Zeichnen ----------------

function zeichneLive(abend) {
  liveStand = abend;
  $("live-start").hidden = abend !== null;
  $("live-tisch").hidden = abend === null;
  if (abend === null) {
    $("lt-aktionen").hidden = true;
    zeichneStart();
    ladeBekannteSpieler();
    return;
  }
  const hand = abend.hand;
  if (!hand || showdown.handId !== hand.hand_id) {
    // neue Hand oder keine Hand: Auswahl zuruecksetzen
    showdown = neuerShowdown();
    showdown.handId = hand ? hand.hand_id : null;
    boardAuswahl = [];
    raiseOffen = false;
  }
  zeichneSpielerleiste(abend);
  zeichneInfo(abend);
  $("lt-board").innerHTML = hand && hand.board.length
    ? hand.board.map((k) => karteHtml(k)).join("") : "";
  zeichneInhalt(abend);
  zeichneAktionsleiste(abend);
  $("lt-verlauf").innerHTML = hand ? verlaufText(hand) : "";
}

function zeichneSpielerleiste(abend) {
  const hand = abend.hand;
  $("lt-spieler").innerHTML = abend.spieler.map((name) => {
    const klassen = [];
    let stack = abend.stacks[name];
    let zusatz = "";
    if (abend.aussetzer.includes(name)) {
      klassen.push("aus");
      zusatz = "setzt aus";
    }
    if (hand && hand.namen.includes(name)) {
      stack = hand.stacks[name];
      if (!hand.aktiv.includes(name)) klassen.push("gefoldet");
      if (hand.am_zug === name) klassen.push("dran");
      if (hand.allin.includes(name)) zusatz = "ALL-IN";
      else if (hand.einsaetze[name] > 0) zusatz = "setzt " + euro(hand.einsaetze[name]);
      if (hand.namen[0] === name) zusatz = "SB " + zusatz;
      if (hand.namen[1] === name) zusatz = "BB " + zusatz;
    } else if (hand) {
      klassen.push("aus");
    }
    return `<button class="spielerchip ${klassen.join(" ")}" data-statistik="${esc(name)}">
      <strong>${esc(name)}</strong><span>${euro(stack)}</span><small>${esc(zusatz)}</small></button>`;
  }).join("");
}

function zeichneInfo(abend) {
  const hand = abend.hand;
  let text = "";
  if (!hand) {
    text = `Blinds ${euro(abend.small_blind)} / ${euro(abend.big_blind)} · nächste Hand: ` +
      `${esc(abend.naechste_hand.join(", "))}`;
  } else {
    const strassen = { preflop: "Preflop", flop: "Flop", turn: "Turn", river: "River" };
    text = `${strassen[hand.strasse]} · Pot <strong>${euro(hand.pot)}</strong>`;
    if (abend.phase === "aktion") {
      text = `<strong>${esc(hand.am_zug)}</strong> ist dran · ` + text;
      if (hand.zu_callen > 0) text += ` · zu callen ${euro(hand.zu_callen)}`;
    }
  }
  $("lt-info").innerHTML = text;
}

function verlaufText(hand) {
  const woerter = { fold: "foldet", check: "checkt", call: "callt", bet: "setzt", raise: "erhöht auf" };
  return hand.verlauf.map((e) => {
    const betrag = ["call", "bet", "raise"].includes(e.aktion) ? " " + euro(e.betrag) : "";
    return `${esc(e.name)} ${woerter[e.aktion]}${betrag}`;
  }).join(" · ");
}

function zeichneInhalt(abend) {
  const hand = abend.hand;
  const ziel = $("lt-inhalt");
  if (abend.phase === "keine_hand") {
    ziel.innerHTML = zwischenDenHaenden(abend);
  } else if (abend.phase === "aktion") {
    ziel.innerHTML = raiseOffen && hand.raise ? raiseFeld(hand) : "";
  } else if (abend.phase === "karten") {
    const namen = { flop: "Flop", turn: "Turn", river: "River" };
    const benutzt = new Set(hand.board.map(kartenSchluessel));
    const gewaehlt = new Set(boardAuswahl.map(kartenSchluessel));
    ziel.innerHTML = `<h2>${namen[hand.naechste_strasse]}: ${hand.neue_karten} Karte(n) antippen
      (${boardAuswahl.length}/${hand.neue_karten})</h2>` + kartenraster(benutzt, gewaehlt);
  } else if (abend.phase === "gewonnen") {
    ziel.innerHTML = `<div class="karte-gross">🏆 <strong>${esc(hand.aktiv[0])}</strong> gewinnt
      ${euro(hand.pot)}</div>`;
  } else if (abend.phase === "showdown") {
    ziel.innerHTML = showdownFeld(hand);
  }
  if (hand) {
    ziel.innerHTML += `<button id="lt-abbrechen" class="klein-knopf gefahr abbrechen-knopf">Hand abbrechen</button>`;
  }
}

function zwischenDenHaenden(abend) {
  const zeilen = abend.spieler.map((name) => {
    const aus = abend.aussetzer.includes(name);
    return `<tr class="${aus ? "raus" : ""}"><td>${esc(name)}</td><td class="zahl">${euro(abend.stacks[name])}</td>
      <td><button class="klein-knopf" data-nachkauf="${esc(name)}">+ Nachkauf</button>
      <button class="klein-knopf" data-aussetzen="${esc(name)}" data-aus="${aus ? "0" : "1"}">
        ${aus ? "Wieder dabei" : "Setzt aus"}</button></td></tr>`;
  }).join("");
  return `<h2>Zwischen den Händen</h2>
    <table><tbody>${zeilen}</tbody></table>
    <div class="zeile"><label>Nachkauf € <input id="lt-nachkauf-betrag" value="10" inputmode="decimal" class="kurz"></label></div>
    <div class="zeile">
      <input id="lt-dazu-name" placeholder="Neuer Spieler" list="spielerliste" autocomplete="off">
      <input id="lt-dazu-stack" value="10" inputmode="decimal" class="kurz"> €
      <button id="lt-dazu">Setzt sich dazu</button>
    </div>
    <button id="lt-beenden" class="klein-knopf gefahr">Abend beenden</button>`;
}

function raiseFeld(hand) {
  const r = hand.raise;
  const wort = Math.max(...Object.values(hand.einsaetze)) === 0 ? "Bet" : "Raise";
  const knopf = (betrag, text) =>
    `<button class="schnellwahl" data-raise="${betrag}">${text}<br><strong>${euro(betrag)}</strong></button>`;
  return `<div class="raise-feld">
    <div class="schnellwahl-reihe">
      ${knopf(r.mindest, "Mindest")}${knopf(r.halber_pot, "½ Pot")}${knopf(r.pot, "Pot")}
    </div>
    <div class="zeile">
      <input id="lt-raise-betrag" inputmode="decimal" placeholder="${wort} auf … €" value="${centAlsEingabe(r.mindest)}">
      <button id="lt-raise-frei" class="haupt">${wort} auf</button>
    </div>
  </div>`;
}

function showdownFeld(hand) {
  // Welche Karten sind schon vergeben? Board + alle schon gewaehlten Handkarten
  const benutzt = new Set(hand.board.map(kartenSchluessel));
  for (const karten of Object.values(showdown.gezeigt)) {
    for (const k of karten) benutzt.add(kartenSchluessel(k));
  }
  let html = "<h2>Showdown – wer zeigt welche Karten?</h2>";
  for (const name of hand.aktiv) {
    const karten = showdown.gezeigt[name] || [];
    const nicht = showdown.zeigtNicht.has(name);
    const aktiv = showdown.ziel === name;
    html += `<div class="showdown-zeile ${aktiv ? "ziel" : ""}">
      <strong>${esc(name)}</strong>
      <span>${nicht ? "zeigt nicht" : karten.map((k) => karteHtml(k, true)).join("") || "–"}</span>
      ${showdown.vorschau && showdown.vorschau.handarten[name]
        ? `<em>${esc(showdown.vorschau.handarten[name])}</em>` : ""}
      <button class="klein-knopf" data-sd-karten="${esc(name)}">Karten</button>
      <button class="klein-knopf" data-sd-nicht="${esc(name)}">${nicht ? "zeigt doch" : "zeigt nicht"}</button>
    </div>`;
    if (aktiv) {
      const eigene = new Set(karten.map(kartenSchluessel));
      // eigene Karten nicht ausgrauen, damit man sie wieder abwaehlen kann
      const fremd = new Set([...benutzt].filter((s) => !eigene.has(s)));
      html += kartenraster(fremd, eigene);
    }
  }
  if (showdown.vorschau) {
    html += "<h2>Ergebnis</h2>";
    showdown.vorschau.pots.forEach((pot, i) => {
      const titel = showdown.vorschau.pots.length === 1 ? "Pot" : i === 0 ? "Hauptpot" : `Side Pot ${i}`;
      let gewinner;
      if (pot.gewinner) {
        gewinner = esc(pot.gewinner.join(" + "));
      } else {
        // Keiner der Berechtigten hat gezeigt: Gewinner antippen
        const gewaehlt = showdown.vonHand[i] ? showdown.vonHand[i][0] : null;
        gewinner = "Gewinner wählen: " + pot.berechtigte.map((n) =>
          `<button class="klein-knopf ${gewaehlt === n ? "haupt" : ""}" data-sd-pot="${i}"
            data-sd-name="${esc(n)}">${esc(n)}</button>`).join(" ");
      }
      html += `<p>${titel} ${euro(pot.betrag)} → ${gewinner}</p>`;
    });
  }
  return html;
}

function zeichneAktionsleiste(abend) {
  const leiste = $("lt-aktionen");
  const hand = abend.hand;
  const knoepfe = [];
  if (hand && hand.kann_rueckgaengig) {
    knoepfe.push('<button class="aktion zurueck" data-befehl="rueckgaengig">↶</button>');
  }
  if (abend.phase === "keine_hand") {
    knoepfe.push('<button class="aktion haupt breit" data-befehl="hand">Nächste Hand austeilen</button>');
  } else if (abend.phase === "aktion") {
    const erlaubt = hand.erlaubt;
    if (erlaubt.includes("fold")) knoepfe.push('<button class="aktion fold" data-aktion="fold">Fold</button>');
    if (erlaubt.includes("check")) knoepfe.push('<button class="aktion" data-aktion="check">Check</button>');
    if (erlaubt.includes("call")) {
      const allin = hand.zu_callen >= hand.stacks[hand.am_zug];
      knoepfe.push(`<button class="aktion" data-aktion="call">Call<br><small>${euro(hand.zu_callen)}${allin ? " all-in" : ""}</small></button>`);
    }
    if (erlaubt.includes("raise")) {
      knoepfe.push(`<button class="aktion ${raiseOffen ? "offen" : ""}" data-befehl="raise">Raise…</button>`);
      knoepfe.push(`<button class="aktion allin" data-aktion="allin">All-in<br><small>${euro(hand.raise.allin)}</small></button>`);
    }
  } else if (abend.phase === "gewonnen") {
    knoepfe.push('<button class="aktion haupt breit" data-befehl="gewonnen">Pot auszahlen</button>');
  } else if (abend.phase === "showdown") {
    const fertig = showdown.vorschau && showdown.vorschau.pots.every((p, i) => p.gewinner || showdown.vonHand[i]);
    knoepfe.push(`<button class="aktion haupt breit" data-befehl="showdown" ${fertig ? "" : "disabled"}>Abrechnen</button>`);
  }
  leiste.innerHTML = knoepfe.join("");
  leiste.hidden = knoepfe.length === 0;
}

function zeichneStart() {
  $("ls-reihenfolge").innerHTML = startAuswahl.map((s, i) => `
    <div class="zeile startzeile">
      <span class="platz">${i + 1}.</span><strong>${esc(s.name)}</strong>
      <input class="kurz" data-stack="${i}" value="${esc(s.stack)}" inputmode="decimal"> €
      <button class="klein-knopf" data-hoch="${i}">↑</button>
      <button class="klein-knopf" data-runter="${i}">↓</button>
      <button class="klein-knopf" data-weg="${i}">✕</button>
    </div>`).join("") || '<p class="klein">Noch niemand ausgewählt.</p>';
}

async function ladeBekannteSpieler() {
  const daten = await api("/api/spieler");
  const gewaehlt = new Set(startAuswahl.map((s) => s.name));
  $("ls-bekannte").innerHTML = daten.namen.map((n) =>
    `<button class="klein-knopf ${gewaehlt.has(n) ? "haupt" : ""}" data-waehle="${esc(n)}">${esc(n)}</button>`
  ).join(" ") || '<p class="klein">Noch keine Spieler gespeichert – unten neue eintragen.</p>';
}

// ---------------- Bedienung ----------------

async function sendeAktion(aktion, betragCent = null) {
  const daten = { aktion };
  if (betragCent !== null) daten.betrag = centAlsEingabe(betragCent);
  raiseOffen = false;
  uebernimm(await api("/api/abend/aktion", "POST", daten));
}

function zeigeErgebnis(ergebnis) {
  const teile = Object.entries(ergebnis)
    .filter(([, betrag]) => betrag !== 0)
    .map(([name, betrag]) => `${name} ${euroVorzeichen(betrag)}`);
  meldung(teile.join(" · "), true);
}

async function aktualisiereShowdownVorschau() {
  const hand = liveStand.hand;
  // Erst auswerten, wenn fuer jeden klar ist: 2 Karten oder "zeigt nicht"
  const fertig = hand.aktiv.every((n) =>
    showdown.zeigtNicht.has(n) || (showdown.gezeigt[n] || []).length === 2);
  showdown.vorschau = null;
  if (fertig) {
    showdown.vorschau = await api("/api/abend/showdown/vorschau", "POST", { gezeigte: gezeigteFuerServer() });
  }
  zeichneLive(liveStand);
}

function gezeigteFuerServer() {
  const gezeigte = {};
  for (const [name, karten] of Object.entries(showdown.gezeigt)) {
    if (!showdown.zeigtNicht.has(name) && karten.length === 2) {
      gezeigte[name] = karten.map(kartenCode).join(" ");
    }
  }
  return gezeigte;
}

$("tab-hand").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;

  // --- Aktionen waehrend der Hand ---
  if (d.aktion) return sendeAktion(d.aktion);
  if (d.raise) return sendeAktion("raise", Number(d.raise));
  if (b.id === "lt-raise-frei") {
    const daten = { aktion: "raise", betrag: $("lt-raise-betrag").value };
    raiseOffen = false;
    return uebernimm(await api("/api/abend/aktion", "POST", daten));
  }
  if (d.befehl === "raise") {
    raiseOffen = !raiseOffen;
    return zeichneLive(liveStand);
  }
  if (d.befehl === "rueckgaengig") {
    showdown.vorschau = null;
    return uebernimm(await api("/api/abend/rueckgaengig", "POST"));
  }
  if (d.befehl === "hand") return uebernimm(await api("/api/abend/hand", "POST"));
  if (d.befehl === "gewonnen") {
    const antwort = uebernimm(await api("/api/abend/gewonnen", "POST"));
    return zeigeErgebnis(antwort.ergebnis);
  }
  if (d.befehl === "showdown") {
    const antwort = uebernimm(await api("/api/abend/showdown", "POST", {
      gezeigte: gezeigteFuerServer(), gewinner_von_hand: showdown.vonHand }));
    return zeigeErgebnis(antwort.ergebnis);
  }
  if (b.id === "lt-abbrechen") {
    if (!bestaetigt(b, "Hand wirklich abbrechen?")) return;
    uebernimm(await api("/api/abend/abbrechen", "POST"));
    return meldung("Hand abgebrochen – sie zählt nicht in der Statistik", true);
  }

  // --- Karten antippen ---
  if (d.karte) {
    const karte = karteAusKnopf(b);
    if (liveStand.phase === "karten") {
      boardAuswahl.push(karte);
      if (boardAuswahl.length === liveStand.hand.neue_karten) {
        const karten = boardAuswahl.map(kartenCode).join(" ");
        boardAuswahl = [];
        return uebernimm(await api("/api/abend/karten", "POST", { karten }));
      }
      return zeichneLive(liveStand);
    }
    if (liveStand.phase === "showdown" && showdown.ziel) {
      const liste = showdown.gezeigt[showdown.ziel] || [];
      const schluessel = kartenSchluessel(karte);
      const vorhanden = liste.findIndex((k) => kartenSchluessel(k) === schluessel);
      if (vorhanden >= 0) liste.splice(vorhanden, 1);          // nochmal antippen = abwaehlen
      else if (liste.length < 2) liste.push(karte);
      showdown.gezeigt[showdown.ziel] = liste;
      showdown.zeigtNicht.delete(showdown.ziel);
      if (liste.length === 2) showdown.ziel = null;             // fertig -> Raster zu
      return aktualisiereShowdownVorschau();
    }
  }

  // --- Showdown ---
  if (d.sdKarten) {
    showdown.ziel = showdown.ziel === d.sdKarten ? null : d.sdKarten;
    return zeichneLive(liveStand);
  }
  if (d.sdNicht) {
    const name = d.sdNicht;
    if (showdown.zeigtNicht.has(name)) showdown.zeigtNicht.delete(name);
    else {
      showdown.zeigtNicht.add(name);
      delete showdown.gezeigt[name];
      if (showdown.ziel === name) showdown.ziel = null;
    }
    return aktualisiereShowdownVorschau();
  }
  if (d.sdPot !== undefined) {
    showdown.vonHand[d.sdPot] = [d.sdName];
    return zeichneLive(liveStand);
  }

  // --- Zwischen den Haenden ---
  if (d.nachkauf) {
    uebernimm(await api("/api/abend/nachkauf", "POST",
      { name: d.nachkauf, betrag: $("lt-nachkauf-betrag").value }));
    return meldung(`Nachkauf für ${d.nachkauf} gebucht`, true);
  }
  if (d.aussetzen) {
    return uebernimm(await api("/api/abend/aussetzen", "POST",
      { name: d.aussetzen, aussetzen: d.aus === "1" }));
  }
  if (b.id === "lt-dazu") {
    return uebernimm(await api("/api/abend/dazu", "POST",
      { name: $("lt-dazu-name").value, stack: $("lt-dazu-stack").value }));
  }
  if (b.id === "lt-beenden") {
    if (!bestaetigt(b, "Abend wirklich beenden?")) return;
    startAuswahl = [];
    uebernimm(await api("/api/abend", "DELETE"));
    return ladeBekannteSpieler();
  }

  // --- Abend einrichten ---
  if (d.waehle) {
    const index = startAuswahl.findIndex((s) => s.name === d.waehle);
    if (index >= 0) startAuswahl.splice(index, 1);
    else startAuswahl.push({ name: d.waehle, stack: $("ls-stack").value });
    zeichneStart();
    return ladeBekannteSpieler();
  }
  if (b.id === "ls-neu-knopf") {
    const name = $("ls-neu").value.trim();
    if (!name) return;
    if (!startAuswahl.some((s) => s.name === name)) startAuswahl.push({ name, stack: $("ls-stack").value });
    $("ls-neu").value = "";
    return zeichneStart();
  }
  if (d.hoch !== undefined || d.runter !== undefined) {
    const i = Number(d.hoch ?? d.runter);
    const j = d.hoch !== undefined ? i - 1 : i + 1;
    if (j >= 0 && j < startAuswahl.length) {
      [startAuswahl[i], startAuswahl[j]] = [startAuswahl[j], startAuswahl[i]];
    }
    return zeichneStart();
  }
  if (d.weg !== undefined && b.closest("#ls-reihenfolge")) {
    startAuswahl.splice(Number(d.weg), 1);
    zeichneStart();
    return ladeBekannteSpieler();
  }
  if (b.id === "ls-starten") {
    const stacks = {};
    for (const s of startAuswahl) stacks[s.name] = s.stack;
    uebernimm(await api("/api/abend", "POST", {
      spieler: startAuswahl.map((s) => s.name), stacks,
      small_blind: $("ls-sb").value, big_blind: $("ls-bb").value }));
    return meldung("Abend gestartet", true);
  }
});

// Stack-Eingaben beim Einrichten merken
$("ls-reihenfolge").addEventListener("input", (e) => {
  if (e.target.dataset.stack !== undefined) startAuswahl[Number(e.target.dataset.stack)].stack = e.target.value;
});

// ---------------- Statistik-Blatt ----------------

const TYP_TEXT = {
  felsen: "Felsen (spielt wenige Hände, setzt nur stark)",
  station: "Calling Station (callt viel, setzt selten)",
  maniac: "Maniac (erhöht ständig)",
  tag: "TAG (wenige Hände, aber aggressiv)",
  unbekannt: "noch unbekannt (ab 20 Händen)",
};

function prozent(wert) {
  return wert === null ? "–" : Math.round(wert * 100) + " %";
}

async function zeigeStatistik(name) {
  const s = await api("/api/abend/statistik/" + encodeURIComponent(name));
  const blatt = $("statistik-blatt");
  blatt.innerHTML = `<div class="blatt-inhalt">
    <h2>${esc(s.name)}</h2>
    <div class="kacheln">
      <div><span class="klein">Hände</span><strong>${s.haende}</strong></div>
      <div><span class="klein">VPIP</span><strong>${prozent(s.vpip)}</strong></div>
      <div><span class="klein">PFR</span><strong>${prozent(s.pfr)}</strong></div>
      <div><span class="klein">AF</span><strong>${s.af === null ? "–" : s.af.toFixed(1)}</strong></div>
      <div><span class="klein">bb/100</span><strong>${s.bb_pro_100 === null ? "–" : Math.round(s.bb_pro_100)}</strong></div>
      <div><span class="klein">Sicherheit</span><strong>${Math.round(s.sicherheit * 100)} %</strong></div>
    </div>
    <p>Typ: <strong>${esc(TYP_TEXT[s.typ] || s.typ)}</strong></p>
    <p class="klein">VPIP: wie oft freiwillig mitgespielt · PFR: wie oft vor dem Flop erhöht ·
      AF: Setzen/Erhöhen geteilt durch Callen. Nur abgeschlossene Hände zählen.</p>
    <button class="gross" id="blatt-zu">Schließen</button>
  </div>`;
  blatt.hidden = false;
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-statistik]");
  if (chip) return zeigeStatistik(chip.dataset.statistik);
  if (e.target.id === "blatt-zu" || e.target.id === "statistik-blatt") $("statistik-blatt").hidden = true;
});

// War beim letzten Mal der Reiter "Hand" offen, jetzt laden (app.js konnte es noch nicht)
if (speicher("tab") === "hand") ladeLive();
