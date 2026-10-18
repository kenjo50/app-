// Reiter "Analyse", Ansicht "Hände": gespeicherte Haende Strasse fuer Strasse
// nachrechnen (Equity, Outs, Pot Odds). Der Umschalter Spieler | Hände | Tisch steht
// auch hier; die Ansicht "Tisch" ist in tischrechner.js.
// Gerechnet wird im Kern (poker/handanalyse.py). Benutzt Hilfsfunktionen aus app.js,
// live.js (karteHtml, kartenraster, kartenSchluessel, kartenCode, karteAusKnopf, prozent)
// und analyse.js (ladeAnalyse, STRASSE_NAME, AKTION_NAME, bb, plusMinus, karten).

"use strict";

const ladeSpielerAnalyse = ladeAnalyse;   // die Ansicht "Spieler" aus analyse.js

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
  // zeichneTischrechner kommt aus tischrechner.js (wird danach geladen)
  if (ansicht === "rechner" && typeof zeichneTischrechner === "function") zeichneTischrechner();
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

// Gemerkte Ansicht wiederherstellen, falls der Reiter "Analyse" schon offen ist
if (speicher("tab") === "analyse") ladeAnalyse();
