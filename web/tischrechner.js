// Reiter "Analyse", Ansicht "Tisch": ein Poker-Tisch mit 9 Plaetzen.
// Platz antippen -> Spieler ist dabei, unten oeffnet sich die Leiste mit dem
// Kartenraster. Board in der Mitte antippen -> Flop/Turn/River waehlen.
// Gerechnet wird im Kern (poker/handanalyse.py, odds_verlauf): Equity jedes
// Spielers Preflop, Flop, Turn, River. Plaetze ohne Karten = unbekannte Hand.
// Benutzt Hilfsfunktionen aus app.js ($, api, esc), live.js (karteHtml, kartenraster,
// kartenSchluessel, kartenCode, karteAusKnopf, prozent), analyse.js (STRASSE_NAME, karten)
// und handanalyse.js (outsHtml).

"use strict";

const TISCH_PLAETZE = 9;
// plaetze[i]: null = frei, [] = dabei ohne Karten, [k1, k2] = dabei mit Karten
let tisch = { plaetze: [[], null, null, null, null, null, null, null, null], board: [], ziel: null };
let tischErgebnis = null;
let tischZaehler = 0;   // nur die Antwort der neuesten Anfrage anzeigen

function platzPosition(i) {
  // Platz 1 unten in der Mitte, dann im Uhrzeigersinn um den Tisch
  const winkel = (90 + i * (360 / TISCH_PLAETZE)) * Math.PI / 180;
  return { x: 50 + 41 * Math.cos(winkel), y: 50 + 43 * Math.sin(winkel) };
}

function dabei() {
  return tisch.plaetze.map((p, i) => (p === null ? -1 : i)).filter((i) => i >= 0);
}

function mitKarten() {
  return dabei().filter((i) => tisch.plaetze[i].length === 2);
}

// Equity eines Platzes auf der letzten gerechneten Strasse
function letzteEquity(i) {
  if (!tischErgebnis) return null;
  const stelle = tischErgebnis.plaetze.indexOf(i);
  if (stelle < 0) return null;
  const strassen = tischErgebnis.daten.strassen;
  return strassen[strassen.length - 1].haende[stelle].equity;
}

function zeichneTischrechner() {
  const plaetze = tisch.plaetze.map((p, i) => {
    const { x, y } = platzPosition(i);
    const klassen = ["tr-platz", p === null ? "frei" : "", tisch.ziel === i ? "ziel" : ""].join(" ");
    let inhalt;
    if (p === null) {
      inhalt = `<span class="nummer">Platz ${i + 1}</span><span>＋</span>`;
    } else {
      const equity = letzteEquity(i);
      inhalt = `<span class="nummer">Platz ${i + 1}</span>
        <span>${p.length ? p.map((k) => karteHtml(k, true)).join("") : '<span class="unbekannt">? ?</span>'}</span>
        <span class="equity">${equity === null ? "" : prozent(equity)}</span>`;
    }
    return `<button class="${klassen}" data-tr-platz="${i}" style="left:${x}%;top:${y}%">${inhalt}</button>`;
  }).join("");
  const board = [0, 1, 2, 3, 4].map((i) =>
    tisch.board[i] ? karteHtml(tisch.board[i], true) : '<span class="leer"></span>').join("");
  $("tr-tisch").innerHTML = `<div class="tr-filz"></div>
    <button class="tr-board ${tisch.ziel === "board" ? "ziel" : ""}" data-tr-board="1">${board}</button>
    ${plaetze}`;
  zeichneLeiste();
  zeichneTischErgebnis();
}

function zeichneLeiste() {
  const leiste = $("tr-leiste");
  if (tisch.ziel === null) {
    leiste.hidden = true;
    return;
  }
  const istBoard = tisch.ziel === "board";
  const eigene = istBoard ? tisch.board : tisch.plaetze[tisch.ziel];
  // Ausgegraut: alle Karten, die schon woanders liegen
  const benutzt = new Set();
  tisch.plaetze.forEach((p, i) => {
    if (p && i !== tisch.ziel) p.forEach((k) => benutzt.add(kartenSchluessel(k)));
  });
  if (!istBoard) tisch.board.forEach((k) => benutzt.add(kartenSchluessel(k)));
  const knoepfe = istBoard
    ? '<button class="klein-knopf" data-tr-befehl="board-leeren">Board leeren</button>'
    : `<button class="klein-knopf" data-tr-befehl="unbekannt">Karten unbekannt</button>
       <button class="klein-knopf gefahr" data-tr-befehl="frei">Platz frei</button>`;
  const titel = istBoard ? `Board (${eigene.length}/5) – Flop, Turn, River`
    : `Platz ${tisch.ziel + 1} – zwei Karten wählen (${eigene.length}/2)`;
  leiste.innerHTML = `<div class="kopf"><strong>${titel}</strong>
      <button class="klein-knopf haupt" data-tr-befehl="fertig">Fertig</button></div>
    ${kartenraster(benutzt, new Set(eigene.map(kartenSchluessel)))}
    <div class="zeile">${knoepfe}</div>`;
  leiste.hidden = false;
}

function zeichneTischErgebnis() {
  const hinweis = $("tr-hinweis");
  if (!tischErgebnis) {
    $("tr-ergebnis").innerHTML = "";
    hinweis.textContent = tischHinweis() || "";
    return;
  }
  hinweis.textContent = tischHinweis() || "";
  const { daten, plaetze, unbekannte } = tischErgebnis;
  const strassen = daten.strassen;
  const kopf = strassen.map((s) => `<th class="zahl">${STRASSE_NAME[s.strasse]}</th>`).join("");
  const zeilen = plaetze.map((platz, stelle) => {
    const zellen = strassen.map((s, j) => {
      const wert = s.haende[stelle].equity;
      const vorher = j > 0 ? strassen[j - 1].haende[stelle].equity : null;
      const klasse = vorher === null ? "" : wert > vorher + 0.005 ? "besser" : wert < vorher - 0.005 ? "schlechter" : "";
      return `<td class="zahl ${klasse}">${prozent(wert)}</td>`;
    }).join("");
    return `<tr><td>${platz + 1}. ${karten(tisch.plaetze[platz])}</td>${zellen}</tr>`;
  }).join("");
  const unbekannteZeile = unbekannte ? `<tr><td class="klein">${unbekannte} unbekannt</td>${
    strassen.map((s) => `<td class="zahl klein">${prozent(s.zufall_equity)}</td>`).join("")}</tr>` : "";
  const letzte = strassen[strassen.length - 1];
  const details = plaetze.map((platz, stelle) => {
    const h = letzte.haende[stelle];
    return (h.handart ? `<div class="klein">Platz ${platz + 1}: ${esc(h.handart)}</div>` : "") +
      outsHtml(`Platz ${platz + 1}`, h.outs);
  }).join("");
  $("tr-ergebnis").innerHTML = `<table class="tr-tabelle"><thead><tr><th>Equity</th>${kopf}</tr></thead>
      <tbody>${zeilen}${unbekannteZeile}</tbody></table>
    ${details ? `<div class="analyse-kasten"><strong>${STRASSE_NAME[letzte.strasse]}</strong>${details}</div>` : ""}
    <p class="klein">Grün/rot: besser/schlechter als auf der Straße davor. Ab dem Flop wird exakt
      ausgezählt, solange alle Karten bekannt sind; mit unbekannten Händen per Simulation.</p>`;
}

function tischHinweis() {
  if (dabei().length < 2) return "Mindestens zwei Plätze antippen.";
  if (mitKarten().length === 0) return "Mindestens ein Spieler braucht seine zwei Karten.";
  if (dabei().some((i) => tisch.plaetze[i].length === 1)) return "Ein Spieler hat erst eine Karte.";
  if (![0, 3, 4, 5].includes(tisch.board.length)) return "Board: erst 3 Karten für den Flop.";
  return null;
}

async function rechneTisch() {
  if (tischHinweis()) {
    tischErgebnis = null;
    return zeichneTischrechner();
  }
  const plaetze = mitKarten();
  const unbekannte = dabei().length - plaetze.length;
  const nummer = ++tischZaehler;
  zeichneTischrechner();
  const daten = await api("/api/odds/verlauf", "POST", {
    haende: plaetze.map((i) => tisch.plaetze[i].map(kartenCode).join(" ")),
    board: tisch.board.map(kartenCode).join(" "),
    zufall: unbekannte,
  });
  if (nummer !== tischZaehler) return;   // inzwischen wurde schon weiter getippt
  tischErgebnis = { daten, plaetze, unbekannte };
  zeichneTischrechner();
}

function tischKlick(e) {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;
  if (d.trPlatz !== undefined) {
    const i = Number(d.trPlatz);
    if (tisch.plaetze[i] === null) tisch.plaetze[i] = [];
    tisch.ziel = i;
    return rechneTisch();
  }
  if (d.trBoard) {
    tisch.ziel = "board";
    return zeichneTischrechner();
  }
  if (d.karte && tisch.ziel !== null) {
    const karte = karteAusKnopf(b);
    const feld = tisch.ziel === "board" ? tisch.board : tisch.plaetze[tisch.ziel];
    const stelle = feld.findIndex((k) => kartenSchluessel(k) === kartenSchluessel(karte));
    const maximal = tisch.ziel === "board" ? 5 : 2;
    if (stelle >= 0) feld.splice(stelle, 1);
    else if (feld.length < maximal) feld.push(karte);
    if (feld.length === maximal && stelle < 0) tisch.ziel = null;   // voll -> Leiste zu
    return rechneTisch();
  }
  if (d.trBefehl === "fertig") tisch.ziel = null;
  if (d.trBefehl === "board-leeren") tisch.board = [];
  if (d.trBefehl === "unbekannt") tisch.plaetze[tisch.ziel] = [];
  if (d.trBefehl === "frei") {
    tisch.plaetze[tisch.ziel] = null;
    tisch.ziel = null;
  }
  rechneTisch();
}

$("tr-tisch").addEventListener("click", tischKlick);
$("tr-leiste").addEventListener("click", tischKlick);

// War beim letzten Mal die Ansicht "Tisch" offen, jetzt zeichnen
if (speicher("tab") === "analyse" && speicher("analyse-ansicht") === "rechner") zeichneTischrechner();
