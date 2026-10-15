// Reiter "Analyse": Verlauf, Gewinnkurve, KI-Auswertung, Fehler, teuerste Haende, Gegner.
// Gerechnet wird im Python-Kern (poker/analyse.py), hier wird nur angezeigt.
// Benutzt Hilfsfunktionen aus app.js ($, api, esc, euro, speicher) und live.js
// (karteHtml, prozent).

"use strict";

const AKTION_NAME = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise" };
const STRASSE_NAME = { preflop: "Preflop", flop: "Flop", turn: "Turn", river: "River" };

let analyseDaten = null;   // letzte Antwort vom Server (fuer Neuzeichnen bei anderer Breite)

function bb(wert, vorzeichen = true) {
  // 12.345 -> "+12,3"
  if (wert === null || wert === undefined) return "–";
  const text = wert.toLocaleString("de-DE", { maximumFractionDigits: 1 });
  return vorzeichen && wert > 0 ? "+" + text : text;
}

function kurzDatum(datum) {
  // "2026-10-08" -> "08.10.26"
  const [jahr, monat, tag] = datum.split("-");
  return `${tag}.${monat}.${jahr.slice(2)}`;
}

function plusMinus(wert) {
  if (wert === null || wert === undefined || wert === 0) return "";
  return wert > 0 ? "plus" : "minus";
}

function karten(liste) {
  if (!liste || liste.length === 0) return '<span class="klein">–</span>';
  return liste.map((k) => karteHtml(k, true)).join("");
}

function aktionText(aktion, betrag) {
  const name = AKTION_NAME[aktion] || aktion;
  return betrag ? `${name} ${euro(betrag)}` : name;
}

async function ladeAnalyse() {
  const daten = await api("/api/spieler");
  const auswahl = $("an-spieler");
  if (daten.namen.length === 0) {
    auswahl.innerHTML = "";
    $("an-inhalt").innerHTML = '<p class="klein">Noch keine Spieler - erst ein paar Hände im Reiter „Hand“ spielen.</p>';
    return;
  }
  const gemerkt = speicher("analyse-spieler");
  const name = daten.namen.includes(gemerkt) ? gemerkt : daten.namen[0];
  auswahl.innerHTML = daten.namen.map((n) =>
    `<option ${n === name ? "selected" : ""}>${esc(n)}</option>`).join("");
  zeigeAnalyse(await api("/api/analyse/" + encodeURIComponent(name)));
}

$("an-spieler").addEventListener("change", async (e) => {
  speicher("analyse-spieler", e.target.value);
  zeigeAnalyse(await api("/api/analyse/" + encodeURIComponent(e.target.value)));
});

function zeigeAnalyse(a) {
  analyseDaten = a;
  const s = a.statistik;
  $("an-inhalt").innerHTML = `
    <div class="kacheln">
      <div><span class="klein">Hände</span><strong>${s.haende}</strong></div>
      <div><span class="klein">bb/100</span><strong class="${plusMinus(s.bb_pro_100)}">${bb(s.bb_pro_100)}</strong></div>
      <div><span class="klein">Gesamt BB</span><strong class="${plusMinus(summeBb(a))}">${bb(summeBb(a))}</strong></div>
    </div>
    ${abendeHtml(a.abende)}
    ${kiHtml(a.ki)}
    ${fehlerHtml(a.fehler, a.ki)}
    ${teuersteHtml(a.teuerste)}
    ${gegnerHtml(a.gegner)}`;
  zeichneKurve(a.kurve);
}

function summeBb(a) {
  return a.kurve.length ? a.kurve[a.kurve.length - 1].bb : null;
}

// ---------------- Verlauf pro Abend + Gewinnkurve ----------------

function abendeHtml(abende) {
  if (abende.length === 0) {
    return '<h2>Verlauf</h2><p class="klein">Noch keine abgeschlossenen Hände.</p>';
  }
  const zeilen = abende.slice().reverse().map((t) => `<tr>
    <td>${esc(kurzDatum(t.datum))}</td><td class="zahl">${t.haende}</td>
    <td class="zahl">${prozent(t.vpip)}</td><td class="zahl">${prozent(t.pfr)}</td>
    <td class="zahl ${plusMinus(t.bb)}">${bb(t.bb)}</td>
    <td class="zahl ${plusMinus(t.bb_pro_100)}">${bb(Math.round(t.bb_pro_100))}</td></tr>`).join("");
  return `<h2>Gewinnkurve (Big Blinds, aufsummiert)</h2>
    <div id="an-kurve" class="kurve"></div>
    <h2>Verlauf pro Abend</h2>
    <table class="an-tabelle"><thead><tr><th>Datum</th><th class="zahl">Hände</th>
      <th class="zahl">VPIP</th><th class="zahl">PFR</th><th class="zahl">BB</th>
      <th class="zahl">bb/100</th></tr></thead><tbody>${zeilen}</tbody></table>`;
}

function schoeneSchritte(min, max, anzahl) {
  // Achsen-Teilung mit runden Werten (1, 2, 5, 10, 20, ...)
  const roh = (max - min) / anzahl || 1;
  const zehner = Math.pow(10, Math.floor(Math.log10(roh)));
  const schritt = [1, 2, 5, 10].map((f) => f * zehner).find((s) => s >= roh);
  const werte = [];
  let w = Math.floor(min / schritt) * schritt;
  werte.push(w);
  while (w < max) {          // so lange, bis auch der hoechste Wert unter dem Gitter liegt
    w = Math.round((w + schritt) * 1000) / 1000;
    werte.push(w);
  }
  return werte;
}

function zeichneKurve(kurve) {
  const ziel = $("an-kurve");
  if (!ziel) return;
  // Startpunkt 0 vor der ersten Hand
  const punkte = [{ nr: 0, bb: 0, datum: "" }].concat(kurve);
  const breite = ziel.clientWidth || 340;
  const hoehe = 200;
  const rand = { links: 44, rechts: 10, oben: 10, unten: 24 };

  const werte = punkte.map((p) => p.bb);
  const ticks = schoeneSchritte(Math.min(0, ...werte), Math.max(0, ...werte), 4);
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const xMax = Math.max(1, punkte[punkte.length - 1].nr);
  const x = (nr) => rand.links + (nr / xMax) * (breite - rand.links - rand.rechts);
  const y = (w) => rand.oben + (1 - (w - yMin) / (yMax - yMin || 1)) * (hoehe - rand.oben - rand.unten);

  let svg = `<svg width="${breite}" height="${hoehe}" role="img"
    aria-label="Gewinnkurve: ${bb(werte[werte.length - 1])} Big Blinds nach ${xMax} Händen">`;
  for (const t of ticks) {
    svg += `<line class="gitter${t === 0 ? " null" : ""}" x1="${rand.links}" x2="${breite - rand.rechts}"
      y1="${y(t)}" y2="${y(t)}"/>
      <text class="achse" x="${rand.links - 6}" y="${y(t) + 4}" text-anchor="end">${bb(t, false)}</text>`;
  }
  svg += `<text class="achse" x="${rand.links}" y="${hoehe - 6}">0</text>
    <text class="achse" x="${breite - rand.rechts}" y="${hoehe - 6}" text-anchor="end">${xMax} Hände</text>`;
  const pfad = punkte.map((p, i) => `${i ? "L" : "M"}${x(p.nr).toFixed(1)},${y(p.bb).toFixed(1)}`).join("");
  svg += `<path class="linie" d="${pfad}"/>
    <line id="an-fadenkreuz" class="fadenkreuz" y1="${rand.oben}" y2="${hoehe - rand.unten}" hidden/>
    <circle id="an-punkt" class="punkt" r="4" hidden/>
    <rect class="fangflaeche" x="0" y="0" width="${breite}" height="${hoehe}"/></svg>
    <div id="an-tipp" class="kurven-tipp" hidden></div>`;
  ziel.innerHTML = svg;

  // Hover / Antippen: naechste Hand zur Fingerposition zeigen
  const zeige = (ereignis) => {
    const box = ziel.getBoundingClientRect();
    const px = ereignis.clientX - box.left;
    const nr = Math.round(((px - rand.links) / (breite - rand.links - rand.rechts)) * xMax);
    const p = punkte[Math.max(0, Math.min(punkte.length - 1, nr))];
    const kreuz = $("an-fadenkreuz");
    const punkt = $("an-punkt");
    const tipp = $("an-tipp");
    kreuz.setAttribute("x1", x(p.nr));
    kreuz.setAttribute("x2", x(p.nr));
    punkt.setAttribute("cx", x(p.nr));
    punkt.setAttribute("cy", y(p.bb));
    kreuz.removeAttribute("hidden");
    punkt.removeAttribute("hidden");
    tipp.hidden = false;
    tipp.innerHTML = p.nr === 0
      ? "Start: 0 BB"
      : `Hand ${p.nr} · ${esc(kurzDatum(p.datum))}<br><strong>${bb(p.bb)} BB</strong>`;
    const links = Math.min(Math.max(x(p.nr) - tipp.offsetWidth / 2, 0), breite - tipp.offsetWidth);
    tipp.style.left = links + "px";
  };
  const verstecke = () => {
    $("an-fadenkreuz").setAttribute("hidden", "");
    $("an-punkt").setAttribute("hidden", "");
    $("an-tipp").hidden = true;
  };
  const flaeche = ziel.querySelector(".fangflaeche");
  flaeche.addEventListener("pointermove", zeige);
  flaeche.addEventListener("pointerdown", zeige);
  flaeche.addEventListener("pointerleave", verstecke);
}

window.addEventListener("resize", () => {
  if (analyseDaten && !$("tab-analyse").hidden) zeichneKurve(analyseDaten.kurve);
});

// ---------------- KI-Auswertung ----------------

function kiHtml(ki) {
  if (ki.entscheidungen === 0) {
    return `<h2>KI-Auswertung</h2><p class="klein">Noch keine KI-Empfehlungen protokolliert.
      Am Tisch den Spieler als KI-Spieler wählen und vor der Entscheidung „KI“ tippen.</p>`;
  }
  const g = ki.gruppen;
  const zeile = (titel, w) => `<tr><td>${titel}</td><td class="zahl">${w.haende}</td>
    <td class="zahl ${plusMinus(w.bb)}">${bb(w.bb)}</td>
    <td class="zahl ${plusMinus(w.bb_pro_100)}">${bb(w.bb_pro_100 === null ? null : Math.round(w.bb_pro_100))}</td></tr>`;
  return `<h2>KI-Auswertung</h2>
    <p>Empfehlung befolgt: <strong>${ki.befolgt} von ${ki.entscheidungen}</strong>
      Entscheidungen (${prozent(ki.quote)})</p>
    <table class="an-tabelle"><thead><tr><th>Hände</th><th class="zahl">Anzahl</th>
      <th class="zahl">BB</th><th class="zahl">bb/100</th></tr></thead><tbody>
      ${zeile("KI befolgt", g.befolgt)}${zeile("Abgewichen", g.abgewichen)}${zeile("Ohne KI", g.ohne_ki)}
    </tbody></table>
    <p class="klein">„Befolgt“ = jede Entscheidung der Hand wie empfohlen. Bei wenigen Händen
      entscheidet vor allem das Kartenglück - erst ab ein paar hundert Händen aussagekräftig.</p>`;
}

function fehlerHtml(fehler, ki) {
  if (ki.entscheidungen === 0) return "";
  if (fehler.length === 0) {
    return '<h2>Wo lag ich falsch?</h2><p class="klein">Keine Abweichungen von der KI.</p>';
  }
  const eintraege = fehler.map((f) => `<div class="analyse-kasten">
    <div class="kopf"><span>${esc(kurzDatum(f.datum))} · ${STRASSE_NAME[f.strasse]}</span>
      <strong class="${plusMinus(f.ergebnis_bb)}">${bb(f.ergebnis_bb)} BB</strong></div>
    <div>${karten(f.handkarten)} <span class="klein">Board</span> ${karten(f.board)}</div>
    <div>KI: <strong>${aktionText(f.empfohlen, f.empfohlen_betrag)}</strong> ·
      gespielt: <strong>${aktionText(f.gespielt, f.gespielt_betrag)}</strong></div>
    <div class="klein">Equity ${prozent(f.equity)} · Pot Odds ${prozent(f.pot_odds)}</div>
  </div>`).join("");
  return `<h2>Wo lag ich falsch?</h2>
    <p class="klein">Entscheidungen gegen die Empfehlung, teuerste Hand zuerst
      (Ergebnis der ganzen Hand).</p>${eintraege}`;
}

// ---------------- Teuerste Haende ----------------

function teuersteHtml(teuerste) {
  if (teuerste.length === 0) return "";
  const eintraege = teuerste.map((h) => {
    const verlauf = h.verlauf.map((v) =>
      `${esc(v.name)} ${aktionText(v.aktion, v.betrag)}`);
    // Nach Strassen gruppieren: "Preflop: Anna Call 0,40 €, Ben Raise ..."
    const strassen = {};
    h.verlauf.forEach((v, i) => { (strassen[v.strasse] = strassen[v.strasse] || []).push(verlauf[i]); });
    const zeilen = Object.keys(strassen).map((s) =>
      `<div class="klein"><strong>${STRASSE_NAME[s]}:</strong> ${strassen[s].join(", ")}</div>`).join("");
    return `<div class="analyse-kasten">
      <div class="kopf"><span>${esc(kurzDatum(h.datum))} · Hand ${h.hand_id}</span>
        <strong class="minus">${bb(h.bb)} BB</strong></div>
      <div>${karten(h.handkarten)} <span class="klein">Board</span> ${karten(h.board)}</div>
      ${zeilen}
      <div class="klein">Gewonnen hat: ${esc(h.gewinner.join(", ") || "–")}</div>
    </div>`;
  }).join("");
  return `<h2>Teuerste Hände</h2>${eintraege}`;
}

// ---------------- Gegner ----------------

function gegnerHtml(gegner) {
  if (gegner.length === 0) return "";
  const eintraege = gegner.map((g) => `<div class="analyse-kasten">
    <div class="kopf"><span><strong>${esc(g.name)}</strong> · ${esc(g.typ_name)}
      ${g.typ === "unbekannt" ? "" : `(${Math.round(g.sicherheit * 100)} % sicher)`}</span>
      <span class="klein">${g.haende} Hände</span></div>
    <div class="klein">VPIP ${prozent(g.vpip)} · PFR ${prozent(g.pfr)} ·
      AF ${g.af === null ? "–" : g.af.toFixed(1)}</div>
    <ul class="tipps">${g.tipps.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
  </div>`).join("");
  return `<h2>Gegner &amp; Anpassung</h2>${eintraege}`;
}

// War beim letzten Mal der Reiter "Analyse" offen, jetzt laden (app.js konnte es noch nicht)
if (speicher("tab") === "analyse") ladeAnalyse();
