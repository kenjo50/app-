// Reiter "Lernen": ueben gegen Bots, die echte Mitspieler nachahmen.
// Die Logik liegt im Kern (poker/lerntisch.py); hier wird nur angezeigt und bedient.
// Hilfsfunktionen aus app.js ($, api, esc, euro, euroVorzeichen, bestaetigt, speicher),
// live.js (karteHtml, centAlsEingabe) und analyse.js (AKTION_NAME, STRASSE_NAME).

"use strict";

const TYP_ANZEIGE = { felsen: "Felsen", station: "Calling Station", maniac: "Maniac", tag: "TAG" };
const BOT_TEMPO = 600;          // ms zwischen zwei Bot-Aktionen

let lernStand = null;           // letzte Antwort vom Server ({spiel})
let lernGegner = [];            // Auswahl vor dem Start: [{spieler}] oder [{typ}]
let lernRaiseOffen = false;
let lernSchrittLaeuft = false;  // damit nie zwei Bot-Schleifen gleichzeitig laufen

async function ladeLerntisch() {
  zeichneLerntisch((await api("/api/lerntisch")).spiel);
}

// ---------------- Start: Gegner auswaehlen ----------------

async function zeichneLernStart() {
  const held = $("lr-held");
  if (!held.value) held.value = speicher("lern-held") || speicher("analyse-spieler") || "";
  const daten = await api("/api/spieler");
  const gewaehlt = new Set(lernGegner.filter((g) => g.spieler).map((g) => g.spieler));
  $("lr-echte").innerHTML = daten.namen.filter((n) => n !== held.value.trim()).map((n) =>
    `<button class="klein-knopf ${gewaehlt.has(n) ? "haupt" : ""}" data-lr-spieler="${esc(n)}">${esc(n)}</button>`
  ).join(" ") || '<p class="klein">Noch keine Spieler gespeichert – nimm Typ-Bots.</p>';
  $("lr-auswahl").innerHTML = lernGegner.map((g, i) => `<div class="lr-auswahl-zeile">
      <span>${g.spieler ? esc(g.spieler) : "Typ-Bot " + TYP_ANZEIGE[g.typ]}</span>
      <button class="klein-knopf" data-lr-weg="${i}">✕</button></div>`).join("")
    || '<p class="klein">Noch niemand ausgewählt (1 bis 8 Gegner).</p>';
}

// ---------------- Tisch ----------------

function zeichneLerntisch(spiel) {
  lernStand = spiel;
  $("lr-start").hidden = spiel !== null;
  $("lr-tisch").hidden = spiel === null;
  if (spiel === null) {
    $("lr-aktionen").hidden = true;
    if ($("lr-ende").hidden) zeichneLernStart();
    return;
  }
  $("lr-ende").hidden = true;
  const s = spiel.sitzung;
  $("lr-sitzung").innerHTML = `${s.haende} Hände · Ergebnis
    <strong class="${s.ergebnis_cent > 0 ? "plus" : s.ergebnis_cent < 0 ? "minus" : ""}">
    ${euroVorzeichen(s.ergebnis_cent)}</strong> · wie die KI: ${s.gleich} von ${s.entscheidungen}`;

  const hand = spiel.hand;
  zeichneLernSpieler(spiel);
  const strasse = STRASSE_NAME[hand.strasse];
  $("lr-info").innerHTML = hand.ergebnis
    ? `Hand vorbei · Pot ${euro(hand.pot)}`
    : `${strasse} · Pot <strong>${euro(hand.pot)}</strong>` +
      (spiel.phase === "held" ? " · <strong>Du bist dran</strong>" : hand.am_zug ? ` · ${esc(hand.am_zug)} überlegt …` : "");
  $("lr-board").innerHTML = hand.board.map((k) => karteHtml(k)).join("");
  $("lr-meine").innerHTML = "Deine Karten: " + hand.karten[spiel.held].map((k) => karteHtml(k)).join("");
  $("lr-tipp").innerHTML = hand.letzter_tipp ? tippHtml(hand.letzter_tipp) : "";
  $("lr-ergebnis").innerHTML = hand.ergebnis ? ergebnisHtml(spiel) : "";
  $("lr-raise").innerHTML = spiel.phase === "held" && lernRaiseOffen && hand.raise ? lernRaiseFeld(hand) : "";
  $("lr-verlauf").innerHTML = hand.verlauf.slice().reverse().map((v) =>
    `${STRASSE_NAME[v.strasse]}: ${esc(v.name)} ${aktionText(v.aktion, v.betrag)}`).join("<br>");
  zeichneLernAktionen(spiel);

  if (spiel.phase === "bots") naechsterBotSchritt();
}

function zeichneLernSpieler(spiel) {
  const hand = spiel.hand;
  const infos = Object.fromEntries(spiel.bots.map((b) => [b.name, b]));
  $("lr-spieler").innerHTML = hand.namen.map((name, platz) => {
    const klassen = [];
    let zusatz = "";
    if (!hand.aktiv.includes(name)) klassen.push("gefoldet");
    if (hand.am_zug === name && !hand.ergebnis) klassen.push("dran");
    if (hand.allin.includes(name)) zusatz = "ALL-IN";
    else if (hand.einsaetze[name] > 0) zusatz = "setzt " + euro(hand.einsaetze[name]);
    if (platz === 0) zusatz = "SB " + zusatz;
    if (platz === 1) zusatz = "BB " + zusatz;
    if (hand.ergebnis && hand.ergebnis.gewinn[name]) zusatz = euroVorzeichen(hand.ergebnis.gewinn[name]);
    const karten = name !== spiel.held && hand.karten[name]
      ? `<div class="chip-karten">${hand.karten[name].map((k) => karteHtml(k, true)).join("")}</div>` : "";
    const titel = name === spiel.held ? "🙂 " + esc(name)
      : esc(name) + (infos[name] ? ` <small>(${esc(TYP_ANZEIGE[infos[name].typ])})</small>` : "");
    return `<div class="spielerchip ${klassen.join(" ")}" title="${esc(infos[name] ? infos[name].info : "")}">
      <strong>${titel}</strong><span>${euro(hand.stacks[name])}</span><small>${esc(zusatz)}</small>${karten}</div>`;
  }).join("");
}

function aktionText(aktion, betrag) {
  const name = AKTION_NAME[aktion] || aktion;
  if (!betrag || aktion === "fold" || aktion === "check") return name;
  return `${name} ${aktion === "call" ? "" : "auf "}${euro(betrag)}`;
}

function tippHtml(t) {
  const kopf = t.gleich
    ? `✓ Die KI hätte auch <strong>${aktionText(t.ki, t.ki_betrag)}</strong> gespielt`
    : `KI hätte: <strong>${aktionText(t.ki, t.ki_betrag)}</strong> – du: <strong>${aktionText(t.du, t.du_betrag)}</strong>`;
  return `<div class="tipp ${t.gleich ? "" : "anders"}">
    <div class="tipp-kopf">${kopf}</div>
    <div class="klein">${STRASSE_NAME[t.strasse]} · Equity ${prozent(t.equity)} · Pot Odds ${prozent(t.pot_odds)}</div>
    <details><summary class="klein">Warum?</summary>
      <ul>${t.gruende.map((g) => `<li>${esc(g)}</li>`).join("")}</ul></details>
  </div>`;
}

function ergebnisHtml(spiel) {
  const e = spiel.hand.ergebnis;
  const mein = e.gewinn[spiel.held] || 0;
  const zeilen = Object.keys(e.gezeigt).map((name) =>
    `<div>${esc(name)}: ${e.gezeigt[name].map((k) => karteHtml(k, true)).join("")}
      <span class="klein">${esc(e.handarten[name])}</span></div>`).join("");
  return `<div class="analyse-kasten">
    <div class="kopf"><span>Gewonnen: <strong>${esc(e.gewinner.join(" + "))}</strong></span>
      <strong class="${mein > 0 ? "plus" : mein < 0 ? "minus" : ""}">${euroVorzeichen(mein)}</strong></div>
    ${zeilen || '<div class="klein">Alle anderen haben aufgegeben – keine Karten gezeigt.</div>'}
  </div>`;
}

function lernRaiseFeld(hand) {
  const r = hand.raise;
  const wort = Math.max(...Object.values(hand.einsaetze)) === 0 ? "Bet" : "Raise";
  const knopf = (betrag, text) =>
    `<button class="schnellwahl" data-lr-raise="${betrag}">${text}<br><strong>${euro(betrag)}</strong></button>`;
  return `<div class="raise-feld">
    <div class="schnellwahl-reihe">
      ${knopf(r.mindest, "Mindest")}${knopf(r.halber_pot, "½ Pot")}${knopf(r.pot, "Pot")}
    </div>
    <div class="zeile">
      <input id="lr-raise-betrag" inputmode="decimal" placeholder="${wort} auf … €" value="${centAlsEingabe(r.mindest)}">
      <button id="lr-raise-frei" class="haupt">${wort} auf</button>
    </div>
  </div>`;
}

function zeichneLernAktionen(spiel) {
  const hand = spiel.hand;
  const knoepfe = [];
  if (spiel.phase === "held") {
    const erlaubt = hand.erlaubt;
    if (erlaubt.includes("fold")) knoepfe.push('<button class="aktion fold" data-lr-aktion="fold">Fold</button>');
    if (erlaubt.includes("check")) knoepfe.push('<button class="aktion" data-lr-aktion="check">Check</button>');
    if (erlaubt.includes("call")) {
      knoepfe.push(`<button class="aktion" data-lr-aktion="call">Call<br><small>${euro(hand.zu_callen)}</small></button>`);
    }
    if (erlaubt.includes("raise")) {
      knoepfe.push(`<button class="aktion ${lernRaiseOffen ? "offen" : ""}" data-lr-befehl="raise">Raise…</button>`);
      knoepfe.push(`<button class="aktion allin" data-lr-aktion="allin">All-in<br><small>${euro(hand.raise.allin)}</small></button>`);
    }
  } else if (spiel.phase === "ende") {
    knoepfe.push('<button class="aktion haupt breit" data-lr-befehl="hand">Nächste Hand</button>');
  } else {
    knoepfe.push('<button class="aktion breit" disabled>Die Bots spielen …</button>');
  }
  $("lr-aktionen").innerHTML = knoepfe.join("");
  $("lr-aktionen").hidden = false;
}

function naechsterBotSchritt() {
  if (lernSchrittLaeuft) return;
  lernSchrittLaeuft = true;
  setTimeout(async () => {
    try {
      const antwort = await api("/api/lerntisch/schritt", "POST");
      lernSchrittLaeuft = false;
      zeichneLerntisch(antwort.spiel);
    } catch (e) {
      lernSchrittLaeuft = false;
    }
  }, BOT_TEMPO);
}

async function lernAktion(aktion, betragCent = null) {
  const daten = { aktion };
  if (betragCent !== null) daten.betrag = centAlsEingabe(betragCent);
  lernRaiseOffen = false;
  zeichneLerntisch((await api("/api/lerntisch/aktion", "POST", daten)).spiel);
}

// ---------------- Zusammenfassung ----------------

function zeigeLernEnde(z) {
  const zeilen = Object.entries(z.pro_strasse).map(([s, w]) =>
    `<tr><td>${STRASSE_NAME[s]}</td><td class="zahl">${w.gleich} / ${w.entscheidungen}</td>
      <td class="zahl">${prozent(w.quote)}</td></tr>`).join("");
  const abweichungen = z.abweichungen.map((a) =>
    `<li>KI ${AKTION_NAME[a.ki]}, du ${AKTION_NAME[a.du]}: ${a.anzahl}×</li>`).join("");
  $("lr-ende").innerHTML = `<h2>Bilanz der Sitzung</h2>
    <div class="kacheln">
      <div><span class="klein">Hände</span><strong>${z.haende}</strong></div>
      <div><span class="klein">Ergebnis</span><strong class="${z.ergebnis_cent > 0 ? "plus" : z.ergebnis_cent < 0 ? "minus" : ""}">${euroVorzeichen(z.ergebnis_cent)}</strong></div>
      <div><span class="klein">wie die KI</span><strong>${prozent(z.quote)}</strong></div>
    </div>
    <p class="klein">${bb(z.ergebnis_bb)} Big Blinds${z.bb_pro_100 === null ? "" : ` · ${bb(Math.round(z.bb_pro_100))} bb/100`}
      · ${z.gleich} von ${z.entscheidungen} Entscheidungen wie die KI</p>
    ${zeilen ? `<table class="an-tabelle"><thead><tr><th>Straße</th><th class="zahl">gleich</th>
      <th class="zahl">Anteil</th></tr></thead><tbody>${zeilen}</tbody></table>` : ""}
    ${abweichungen ? `<h2>Häufigste Abweichungen</h2><ul>${abweichungen}</ul>` : ""}
    <button id="lr-neu" class="haupt gross">Neue Sitzung</button>`;
  $("lr-ende").hidden = false;
  $("lr-start").hidden = true;
}

// ---------------- Bedienung ----------------

$("tab-lernen").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;

  // Start
  if (d.lrSpieler) {
    const i = lernGegner.findIndex((g) => g.spieler === d.lrSpieler);
    if (i >= 0) lernGegner.splice(i, 1);
    else if (lernGegner.length < 8) lernGegner.push({ spieler: d.lrSpieler });
    return zeichneLernStart();
  }
  if (d.lrTyp) {
    if (lernGegner.length < 8) lernGegner.push({ typ: d.lrTyp });
    return zeichneLernStart();
  }
  if (d.lrWeg) {
    lernGegner.splice(Number(d.lrWeg), 1);
    return zeichneLernStart();
  }
  if (b.id === "lr-los") {
    const held = $("lr-held").value.trim();
    speicher("lern-held", held);
    return zeichneLerntisch((await api("/api/lerntisch", "POST", { held, gegner: lernGegner })).spiel);
  }
  if (b.id === "lr-neu") {
    $("lr-ende").hidden = true;
    return zeichneLerntisch(null);
  }

  // Am Tisch
  if (d.lrAktion) return lernAktion(d.lrAktion);
  if (d.lrRaise) return lernAktion("raise", Number(d.lrRaise));
  if (b.id === "lr-raise-frei") {
    lernRaiseOffen = false;
    const antwort = await api("/api/lerntisch/aktion", "POST",
      { aktion: "raise", betrag: $("lr-raise-betrag").value });
    return zeichneLerntisch(antwort.spiel);
  }
  if (d.lrBefehl === "raise") {
    lernRaiseOffen = !lernRaiseOffen;
    return zeichneLerntisch(lernStand);
  }
  if (d.lrBefehl === "hand") {
    return zeichneLerntisch((await api("/api/lerntisch/hand", "POST")).spiel);
  }
  if (b.id === "lr-beenden") {
    if (!bestaetigt(b, "Wirklich beenden?")) return;
    const antwort = await api("/api/lerntisch/ende", "POST");
    zeichneLerntisch(null);
    return zeigeLernEnde(antwort.zusammenfassung);
  }
});

$("lr-held").addEventListener("change", zeichneLernStart);

// War beim letzten Mal der Reiter "Lernen" offen, jetzt laden (app.js konnte es noch nicht)
if (speicher("tab") === "lernen") ladeLerntisch();
