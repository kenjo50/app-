// Reiter "Analyse", Ansichten "Hände" und "Rechner": gespeicherte Haende Strasse fuer
// Strasse nachrechnen (Equity, Outs, Pot Odds) und ein freier Odds-Rechner.
// Gerechnet wird im Kern (poker/handanalyse.py). Benutzt Hilfsfunktionen aus app.js,
// live.js (karteHtml, kartenraster, kartenSchluessel, kartenCode, karteAusKnopf, prozent)
// und analyse.js (ladeAnalyse, STRASSE_NAME, AKTION_NAME, bb, plusMinus, karten).

"use strict";

const ladeSpielerAnalyse = ladeAnalyse;   // die Ansicht "Spieler" aus analyse.js
let rechner = { haende: [[], []], board: [], ziel: 0, gegner: 1 };
let rechnerZaehler = 0;   // nur die Antwort der neuesten Anfrage anzeigen

// ---------------- Umschalter ----------------

function zeigeAnsicht(ansicht) {
  speicher("analyse-ansicht", ansicht);
  for (const name of ["spieler", "haende", "rechner"]) {
    $("an-ansicht-" + name).hidden = name !== ansicht;
  }
  document.querySelectorAll("[data-an-ansicht]").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.anAnsicht === ansicht));
  if (ansicht === "spieler") ladeSpielerAnalyse();
  if (ansicht === "haende") ladeHandListe();
  if (ansicht === "rechner") zeichneRechner();
}

// app.js ruft beim Oeffnen des Reiters ladeAnalyse auf - jetzt mit der gemerkten Ansicht
ladeAnalyse = async function () {
  zeigeAnsicht(speicher("analyse-ansicht") || "spieler");
};

document.querySelectorAll("[data-an-ansicht]").forEach((b) =>
  b.addEventListener("click", () => zeigeAnsicht(b.dataset.anAnsicht)));

// ---------------- Haende: Liste ----------------

function haBetrag(wert) {
  return wert === null || wert === undefined ? "–" : euroVorzeichen(wert);
}

async function ladeHandListe() {
  $("ha-detail").hidden = true;
  $("ha-liste").hidden = false;
  const quelle = $("ha-quelle").value;
  const alle = (await api(`/api/haende/${quelle}`)).haende;
  const namen = [...new Set(alle.flatMap((h) => h.bekannt))].sort();
  const vorschlag = quelle === "lerntisch" ? speicher("lern-held") : speicher("analyse-spieler");
  const gewaehlt = $("ha-spieler").value || vorschlag;
  const name = namen.includes(gewaehlt) ? gewaehlt : "";
  $("ha-spieler").innerHTML = '<option value="">alle</option>' + namen.map((n) =>
    `<option ${n === name ? "selected" : ""}>${esc(n)}</option>`).join("");
  const haende = name
    ? (await api(`/api/haende/${quelle}?name=${encodeURIComponent(name)}`)).haende : alle;
  $("ha-liste").innerHTML = haende.map((h) => `<button class="ha-zeile" data-ha-hand="${h.hand_id}">
      <div class="kopf"><span>${esc(h.datum)} · Hand ${h.hand_id}</span>
        ${name ? `<strong class="${plusMinus(h.ergebnis)}">${haBetrag(h.ergebnis)}</strong>`
               : `<span class="klein">Pot ${euro(h.pot)}</span>`}</div>
      <div>${h.karten ? karten(h.karten) + " " : ""}<span class="klein">Board</span> ${karten(h.board)}</div>
      <div class="klein">${esc(h.namen.join(", "))} · gewonnen: ${esc(h.gewinner.join(", ") || "–")}</div>
    </button>`).join("")
    || `<p class="klein">Keine Hände mit bekannten Karten${quelle === "lerntisch"
      ? " – spiel ein paar Hände im Reiter „Lernen“." : " – am Live-Tisch die Karten des KI-Spielers oder beim Showdown eingeben."}</p>`;
}

$("ha-quelle").addEventListener("change", () => {
  $("ha-spieler").value = "";
  ladeHandListe();
});
$("ha-spieler").addEventListener("change", ladeHandListe);

// ---------------- Haende: eine Hand im Detail ----------------

function equityZelle(wert) {
  return wert === null || wert === undefined ? "–" : prozent(wert);
}

function outsHtml(name, o) {
  if (!o || o.anzahl === 0) return "";
  const titel = { outs: "Outs", gefaehrlich: "gefährliche Karten", verbesserung: "Karten verbessern" }[o.art];
  const gruppen = o.gruppen.map((g) => (g.handart ? `${esc(g.handart)}: ` : "") + karten(g.karten)).join("<br>");
  return `<div class="ha-outs"><strong>${esc(name)}</strong>: ${o.anzahl} ${titel}<br>${gruppen}</div>`;
}

function entscheidungHtml(e) {
  let text = `<strong>${esc(e.name)}</strong> ${aktionText(e.aktion, e.betrag)}`;
  if (e.pot_odds !== null) {
    text += ` · ${euro(e.zu_callen)} zu zahlen in ${euro(e.pot)} → braucht ${prozent(e.pot_odds)}`;
  }
  if (e.equity) {
    const wirklich = e.equity.wirklich !== null;
    text += `, hatte ${prozent(wirklich ? e.equity.wirklich : e.equity.bereich)}
      <span class="klein">(${wirklich ? "wirklich" : "gegen Bereich"})</span>`;
  }
  if (e.urteil) {
    const gut = e.urteil === "lohnend" || e.urteil === "Fold ok";
    text += ` <strong class="${gut ? "urteil-gut" : "urteil-schlecht"}">${esc(e.urteil)}</strong>`;
  }
  return `<div class="ha-entscheidung">${text}</div>`;
}

function strasseHtml(s, a) {
  const spieler = Object.keys(s.equity);
  const zeilen = spieler.map((n) => {
    const w = s.equity[n];
    return `<tr><td>${esc(n)} ${karten(a.karten[n])}</td><td class="zahl">${equityZelle(w.wirklich)}</td>
      <td class="zahl">${equityZelle(w.zufall)}</td><td class="zahl">${equityZelle(w.bereich)}</td></tr>`;
  }).join("");
  // Geschaetzte Bereiche aus Sicht des ersten Spielers mit bekannten Karten
  const sicht = spieler.find((n) => s.equity[n].bereiche);
  const bereiche = sicht ? Object.entries(s.equity[sicht].bereiche).map(([n, p]) =>
    `${esc(n)} beste ${bb(p, false)} %`).join(", ") : "";
  return `<div class="analyse-kasten">
    <div class="kopf"><strong>${STRASSE_NAME[s.strasse]}</strong><span>Pot ${euro(s.pot)}</span></div>
    ${s.board.length ? `<div>${karten(s.board)}</div>` : ""}
    ${zeilen ? `<table class="ha-tabelle"><thead><tr><th>Equity</th><th class="zahl">wirklich</th>
      <th class="zahl">Zufall</th><th class="zahl">Bereich</th></tr></thead><tbody>${zeilen}</tbody></table>` : ""}
    ${bereiche ? `<div class="klein">Geschätzte Bereiche (Sicht ${esc(sicht)}): ${bereiche}</div>` : ""}
    ${spieler.map((n) => outsHtml(n, s.outs[n])).join("")}
    ${s.entscheidungen.map(entscheidungHtml).join("")}
  </div>`;
}

async function zeigeHand(handId) {
  const quelle = $("ha-quelle").value;
  $("ha-liste").hidden = true;
  $("ha-detail").hidden = false;
  $("ha-detail").innerHTML = '<p class="klein">Rechne …</p>';
  const a = await api(`/api/haende/${quelle}/${handId}`);
  const spieler = a.namen.map((n) => `<div>${esc(n)}: ${a.karten[n] ? karten(a.karten[n]) : '<span class="klein">unbekannt</span>'}
      <strong class="${plusMinus(a.ergebnis[n])}">${haBetrag(a.ergebnis[n])}</strong></div>`).join("");
  $("ha-detail").innerHTML = `<button class="klein-knopf" id="ha-zurueck">← Liste</button>
    <h2>Hand ${a.hand_id} · ${esc(a.datum)}</h2>
    <p class="klein">Blinds ${euro(a.small_blind)} / ${euro(a.big_blind)} · Board ${karten(a.board)}</p>
    ${spieler}
    ${a.strassen.map((s) => strasseHtml(s, a)).join("")}
    <p class="klein"><strong>wirklich</strong> = gegen die echten Karten (nur wenn alle Gegner bekannt) ·
      <strong>Zufall</strong> = gegen zufällige Hände · <strong>Bereich</strong> = gegen die geschätzten
      Hände der Gegner (Spielertyp + Aktionen). Bei Entscheidungen zählt „wirklich“, sonst „Bereich“.</p>`;
}

$("an-ansicht-haende").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.haHand) zeigeHand(b.dataset.haHand);
  if (b.id === "ha-zurueck") {
    $("ha-detail").hidden = true;
    $("ha-liste").hidden = false;
  }
});

// ---------------- Rechner ----------------

function rechnerFeldKarten(ziel) {
  return ziel === "board" ? rechner.board : rechner.haende[ziel];
}

function zeichneRechner(ergebnis = null) {
  const felder = rechner.haende.map((hand, i) => {
    const r = ergebnis && ergebnis.haende[ergebnisIndex(i)];
    return `<button class="or-feld ${rechner.ziel === i ? "ziel" : ""}" data-or-ziel="${i}">
      <span class="name">Hand ${i + 1}</span>${karten(hand)}
      ${r && hand.length === 2 ? `<span class="equity">${prozent(r.equity)}</span>` : ""}</button>`;
  }).join("");
  const nurEine = rechner.haende.filter((h) => h.length === 2).length === 1;
  $("or-felder").innerHTML = `${felder}
    <div class="zeile">
      ${rechner.haende.length < 9 ? '<button class="klein-knopf" data-or-befehl="hand">+ Hand</button>' : ""}
      ${rechner.haende.length > 1 ? '<button class="klein-knopf" data-or-befehl="weg">− Hand</button>' : ""}
      <button class="klein-knopf" data-or-befehl="leeren">Alles leeren</button>
    </div>
    <button class="or-feld ${rechner.ziel === "board" ? "ziel" : ""}" data-or-ziel="board">
      <span class="name">Board</span>${karten(rechner.board)}</button>
    ${nurEine ? `<div class="zeile">Gegner (zufällig):
      <button class="klein-knopf" data-or-befehl="weniger">−</button> <strong>${rechner.gegner}</strong>
      <button class="klein-knopf" data-or-befehl="mehr">+</button></div>` : ""}`;

  const benutzt = new Set();
  for (const k of rechner.haende.flat().concat(rechner.board)) benutzt.add(kartenSchluessel(k));
  const eigene = new Set(rechnerFeldKarten(rechner.ziel).map(kartenSchluessel));
  const fremd = new Set([...benutzt].filter((s) => !eigene.has(s)));
  $("or-raster").innerHTML = kartenraster(fremd, eigene);

  if (ergebnis) {
    $("or-ergebnis").innerHTML = ergebnis.haende.map((r, i) => `<div class="analyse-kasten">
        <div class="kopf"><span>${karten(r.karten)} ${r.handart ? esc(r.handart) : ""}</span>
          <strong>${prozent(r.equity)}</strong></div>
        ${outsHtml("Hand " + (vollstaendigeIndizes()[i] + 1), r.outs)}</div>`).join("") +
      `<p class="klein">${ergebnis.art === "zufall"
        ? `Gegen ${rechner.gegner} zufällige Hand/Hände (Monte-Carlo).`
        : "Die Hände gegeneinander (ab dem Flop exakt ausgezählt)."}</p>`;
  } else {
    $("or-ergebnis").innerHTML = "";
  }
}

function vollstaendigeIndizes() {
  return rechner.haende.map((h, i) => (h.length === 2 ? i : -1)).filter((i) => i >= 0);
}

function ergebnisIndex(feld) {
  return vollstaendigeIndizes().indexOf(feld);
}

async function rechne() {
  const fertig = rechner.haende.filter((h) => h.length === 2);
  const halbe = rechner.haende.some((h) => h.length === 1);
  if (fertig.length === 0 || halbe || ![0, 3, 4, 5].includes(rechner.board.length)) {
    return zeichneRechner();
  }
  const nummer = ++rechnerZaehler;
  const ergebnis = await api("/api/odds", "POST", {
    haende: fertig.map((h) => h.map(kartenCode).join(" ")),
    board: rechner.board.map(kartenCode).join(" "),
    gegner: rechner.gegner,
  });
  if (nummer === rechnerZaehler) zeichneRechner(ergebnis);
}

function naechstesZiel() {
  // Nach einer vollen Hand zum naechsten leeren Feld springen
  const leer = rechner.haende.findIndex((h) => h.length < 2);
  return leer >= 0 ? leer : "board";
}

$("an-ansicht-rechner").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;
  if (d.orZiel !== undefined) {
    rechner.ziel = d.orZiel === "board" ? "board" : Number(d.orZiel);
    return zeichneRechner();
  }
  if (d.karte) {
    const karte = karteAusKnopf(b);
    const feld = rechnerFeldKarten(rechner.ziel);
    const stelle = feld.findIndex((k) => kartenSchluessel(k) === kartenSchluessel(karte));
    if (stelle >= 0) {
      feld.splice(stelle, 1);
    } else if (feld.length < (rechner.ziel === "board" ? 5 : 2)) {
      feld.push(karte);
      if (rechner.ziel !== "board" && feld.length === 2) rechner.ziel = naechstesZiel();
    }
    return rechne();
  }
  if (d.orBefehl === "hand") {
    rechner.haende.push([]);
    rechner.ziel = rechner.haende.length - 1;
  }
  if (d.orBefehl === "weg") {
    rechner.haende.pop();
    if (rechner.ziel !== "board" && rechner.ziel >= rechner.haende.length) rechner.ziel = 0;
  }
  if (d.orBefehl === "leeren") rechner = { haende: [[], []], board: [], ziel: 0, gegner: rechner.gegner };
  if (d.orBefehl === "weniger") rechner.gegner = Math.max(1, rechner.gegner - 1);
  if (d.orBefehl === "mehr") rechner.gegner = Math.min(8, rechner.gegner + 1);
  rechne();
});

// Gemerkte Ansicht wiederherstellen, falls der Reiter "Analyse" schon offen ist
if (speicher("tab") === "analyse") ladeAnalyse();
