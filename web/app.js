// Web-App fuer Turnier-Timer, Clock und Kasse.
// Die Logik liegt im Python-Kern; hier wird nur angezeigt, bedient und vorgelesen.

"use strict";

// ---------------- Hilfen ----------------

const $ = (id) => document.getElementById(id);

function esc(text) {
  // Namen sicher ins HTML einsetzen
  return String(text).replace(/[&<>"']/g, (z) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[z]);
}

const euroFormat = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
function euro(cent) {
  return euroFormat.format(cent / 100);
}
function euroVorzeichen(cent) {
  const text = euro(cent);
  return cent > 0 ? "+" + text : text;
}

function zeitText(sekunden) {
  // 754 -> "12:34", 3754 -> "1:02:34"
  const s = Math.max(0, Math.ceil(sekunden));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${rest}`;
  return `${String(m).padStart(2, "0")}:${rest}`;
}

function uhrzeit(iso) {
  return iso ? iso.slice(11, 16) : "";
}

let meldungTimer = null;
function meldung(text, gut = false) {
  const el = $("meldung");
  el.textContent = text;
  el.classList.toggle("gut", gut);
  el.hidden = false;
  clearTimeout(meldungTimer);
  meldungTimer = setTimeout(() => (el.hidden = true), 3500);
}

// Bestaetigung per zweitem Tippen statt confirm()-Fenster:
// confirm() ist auf dem iPhone unzuverlaessig (vor allem als Homescreen-App).
// 1. Tippen: Knopf wird rot und fragt "Sicher?", 2. Tippen (innerhalb 3 s): los.
function bestaetigt(knopf, frage = "Sicher?") {
  if (knopf.dataset.sicher === "1") {
    zuruecksetzen(knopf);
    return true;
  }
  knopf.dataset.sicher = "1";
  knopf.dataset.alterText = knopf.textContent;
  knopf.textContent = frage;
  knopf.classList.add("bestaetigen");
  setTimeout(() => {
    if (knopf.dataset.sicher === "1") zuruecksetzen(knopf);
  }, 3000);
  return false;
}

function zuruecksetzen(knopf) {
  knopf.textContent = knopf.dataset.alterText;
  delete knopf.dataset.sicher;
  delete knopf.dataset.alterText;
  knopf.classList.remove("bestaetigen");
}

async function api(pfad, methode = "GET", daten = undefined) {
  const optionen = { method: methode, headers: {} };
  if (daten !== undefined) {
    optionen.headers["Content-Type"] = "application/json";
    optionen.body = JSON.stringify(daten);
  }
  const antwort = await fetch(pfad, optionen);
  const inhalt = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    const text = typeof inhalt.detail === "string" ? inhalt.detail : "Fehler " + antwort.status;
    meldung(text);
    throw new Error(text);
  }
  return inhalt;
}

function speicher(schluessel, wert) {
  // localStorage kann im privaten Modus fehlen -> dann einfach nichts merken
  try {
    if (wert === undefined) return localStorage.getItem(schluessel);
    if (wert === null) localStorage.removeItem(schluessel);
    else localStorage.setItem(schluessel, wert);
  } catch (e) { /* egal */ }
  return null;
}

// ---------------- Ton, Sprache, Wake Lock ----------------

let audio = null;          // AudioContext fuer den Piepton
let tonAktiv = false;
let wakeLock = null;

function deutscheStimme() {
  const stimmen = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  return stimmen.find((s) => s.lang === "de-DE") ||
         stimmen.find((s) => s.lang && s.lang.startsWith("de")) || null;
}

function sprich(text) {
  if (!window.speechSynthesis || !text) return;
  // iOS haelt die Sprachausgabe manchmal still an -> wieder aufwecken
  if (speechSynthesis.paused) speechSynthesis.resume();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "de-DE";
  const stimme = deutscheStimme();
  if (stimme) u.voice = stimme;
  u.rate = 1.0;
  speechSynthesis.speak(u);
}

function piep() {
  if (!audio) return;
  // Nach Sperre/Hintergrund ist der AudioContext oft "suspended"
  if (audio.state !== "running") audio.resume();
  // Ein deutlicher, eine Sekunde langer Ton
  const osc = audio.createOscillator();
  const lautstaerke = audio.createGain();
  osc.type = "square";
  osc.frequency.value = 880;
  const t = audio.currentTime;
  lautstaerke.gain.setValueAtTime(0.0001, t);
  lautstaerke.gain.exponentialRampToValueAtTime(0.5, t + 0.02);
  lautstaerke.gain.setValueAtTime(0.5, t + 0.9);
  lautstaerke.gain.exponentialRampToValueAtTime(0.0001, t + 1.0);
  osc.connect(lautstaerke).connect(audio.destination);
  osc.start(t);
  osc.stop(t + 1.05);
}

async function bildschirmWachHalten() {
  if (!("wakeLock" in navigator)) {
    zeigeHinweis("Dieses Gerät kann den Standby nicht automatisch verhindern (Wake Lock braucht " +
      "HTTPS). Bitte in den iPhone-Einstellungen unter Anzeige & Helligkeit → " +
      "Automatische Sperre „Nie“ wählen.");
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");
  } catch (e) {
    zeigeHinweis("Bildschirm-Sperre konnte nicht verhindert werden: " + e.message);
  }
}

function zeigeHinweis(text) {
  const el = $("hinweis");
  el.textContent = text;
  el.hidden = false;
}

// iOS: Ton und Sprache gehen erst nach einer Beruehrung. Darum dieser Knopf.
// WICHTIG: Alles, was Ton freischaltet, muss SOFORT im Klick passieren -
// ohne "await" davor. Nach einem await zaehlt es fuer iOS nicht mehr als
// Beruehrung, und die Sprachausgabe bleibt fuer immer stumm.
function tonFreischalten() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (AudioCtx && !audio) audio = new AudioCtx();
  if (audio) {
    audio.resume();  // bewusst ohne await
    // kurzer, stiller Ton schaltet die Ausgabe auf iOS frei
    const puffer = audio.createBuffer(1, 1, 22050);
    const quelle = audio.createBufferSource();
    quelle.buffer = puffer;
    quelle.connect(audio.destination);
    quelle.start(0);
  }
  tonAktiv = true;
  $("aktivieren").textContent = "🔊 Ton ist an";
  $("aktivieren").classList.remove("haupt");
}

$("aktivieren").addEventListener("click", () => {
  tonFreischalten();
  sprich("Ton ist an.");
  bildschirmWachHalten();  // darf danach kommen, braucht keine Beruehrung
});

$("ton-testen").addEventListener("click", () => {
  tonFreischalten();
  sprich("Test. Eins, zwei, drei.");
  setTimeout(piep, 1800);
  zeigeAnsage("Test: Du solltest „Test, eins, zwei, drei“ und einen Piepton hören.");
});

// Jede Ansage zusaetzlich als Text anzeigen - so sieht man, ob sie ankam,
// auch wenn kein Ton zu hoeren ist.
let ansageTimer = null;
function zeigeAnsage(text) {
  const el = $("ansage");
  el.textContent = "📢 " + text;
  el.hidden = false;
  clearTimeout(ansageTimer);
  ansageTimer = setTimeout(() => (el.hidden = true), 4000);
}

// Wake Lock geht verloren, wenn die Seite im Hintergrund war -> neu anfordern
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && tonAktiv && "wakeLock" in navigator) {
    bildschirmWachHalten();
  }
});

if (window.speechSynthesis) {
  speechSynthesis.onvoiceschanged = () => deutscheStimme();
}

// ---------------- Steuergeraet ----------------

function istSteuergeraet() {
  return $("steuergeraet").checked;
}

$("steuergeraet").checked = speicher("steuergeraet") === "1";
document.body.classList.toggle("nur-anzeige", !istSteuergeraet());
$("steuergeraet").addEventListener("change", () => {
  speicher("steuergeraet", istSteuergeraet() ? "1" : "0");
  document.body.classList.toggle("nur-anzeige", !istSteuergeraet());
});

// ---------------- Tabs ----------------

const TABS = ["hand", "timer", "clock", "struktur", "turnier", "cash", "bilanz"];

function zeigeTab(name) {
  for (const tab of TABS) {
    $("tab-" + tab).hidden = tab !== name;
  }
  document.querySelectorAll("nav button").forEach((b) => {
    b.classList.toggle("aktiv", b.dataset.tab === name);
  });
  speicher("tab", name);
  if (name === "turnier") ladeTurnier();
  if (name === "cash") ladeCash();
  if (name === "bilanz") ladeBilanz();
  // ladeLive kommt aus live.js, das erst nach app.js geladen wird
  if (name === "hand" && typeof ladeLive === "function") ladeLive();
  if (name === "struktur" && struktur.length === 0) strukturAusVorlage();
}

document.querySelectorAll("nav button").forEach((b) => {
  b.addEventListener("click", () => zeigeTab(b.dataset.tab));
});

// ---------------- Status vom Server ----------------

let stand = null;        // letzte Antwort von /api/status
let versatz = 0;         // Serverzeit minus eigene Zeit (Sekunden)
let letzteId = null;     // letzte Ansage, die wir schon kennen

function serverJetzt() {
  return Date.now() / 1000 + versatz;
}

let abfrageLaeuft = false;

async function holeStatus() {
  // Laeuft noch eine Abfrage, nicht noch eine starten (sonst kaemen Ansagen doppelt)
  if (abfrageLaeuft) return;
  abfrageLaeuft = true;
  try {
    const antwort = await fetch("/api/status?nach_id=" + (letzteId ?? 0));
    const daten = await antwort.json();
    versatz = daten.jetzt - Date.now() / 1000;
    if (letzteId === null) {
      // Beim ersten Mal: alte Ansagen nicht nachholen
      letzteId = daten.letzte_id;
    } else {
      for (const ansage of daten.ansagen) {
        spieleAnsage(ansage, daten.jetzt);
        letzteId = Math.max(letzteId, ansage.id);
      }
    }
    const strukturNeu = !stand || stand.vorlage !== daten.vorlage;
    stand = daten;
    if (strukturNeu) zeigeTimerKopf();
  } catch (e) {
    // Server kurz nicht erreichbar: beim naechsten Mal wieder versuchen
  } finally {
    abfrageLaeuft = false;
  }
}

function spieleAnsage(ansage, jetzt) {
  // Ansagen, die laenger als 5 Sekunden her sind (z. B. Handy war im
  // Hintergrund), werden nicht mehr vorgelesen.
  if (jetzt - ansage.zeit > 5) return;
  const text = ansage.art === "piep" ? "PIEP – Zeit ist um!" : ansage.text;
  // Text immer anzeigen; sprechen nur, wenn auf diesem Geraet der Ton an ist.
  // (Jedes Geraet mit "Ton an" spricht - am besten nur eines einschalten.)
  zeigeAnsage(tonAktiv ? text : text + "  (Ton aus – oben auf 🔊 tippen)");
  if (!tonAktiv) return;
  if (ansage.art === "piep") piep();
  else sprich(ansage.text);
}

// Status regelmaessig holen; 4x pro Sekunde, damit "3, 2, 1" puenktlich kommt
setInterval(holeStatus, 250);

// ---------------- Timer-Anzeige ----------------

function levelText(lvl) {
  if (!lvl) return "–";
  if (lvl.pause) return `Pause (${lvl.minuten} Min)`;
  let text = `${lvl.small_blind} / ${lvl.big_blind}`;
  if (lvl.ante) text += ` · Ante ${lvl.ante}`;
  return text;
}

function zeigeTimerKopf() {
  const hatTimer = stand && stand.timer;
  $("timer-leer").hidden = !!hatTimer;
  $("timer-anzeige").hidden = !hatTimer;
  $("timer-vorlage-name").textContent = hatTimer ? "Struktur: " + stand.vorlage : "";
}

function zeichne() {
  if (!stand) return;
  const t = stand.timer;
  if (t) {
    const rest = t.laeuft ? t.ende - serverJetzt() : t.restzeit;
    $("zeit").textContent = zeitText(rest);
    $("zeit").classList.toggle("warnung", t.laeuft && rest <= 60);
    $("zeit").classList.toggle("angehalten", !t.laeuft);
    $("level-titel").textContent = t.pause ? "Pause" : `Level ${t.nummer}`;
    $("blinds").textContent = t.pause ? "☕" : `${t.small_blind} / ${t.big_blind}`;
    $("ante").textContent = !t.pause && t.ante ? `Ante ${t.ante}` : "";
    $("naechstes").textContent = levelText(t.naechstes);
    if (t.zeit_bis_pause === null) {
      $("pause-in").textContent = t.pause ? "jetzt" : "keine mehr";
    } else {
      const bisPause = t.laeuft ? t.zeit_bis_pause - (serverJetzt() - stand.jetzt) : t.zeit_bis_pause;
      $("pause-in").textContent = zeitText(bisPause);
    }
    $("t-start").textContent = t.vorbei ? "Ende" : t.laeuft ? "Pause" : "Start";
  }

  const c = stand.clock;
  const clockRest = c.laeuft ? Math.max(0, c.ende - serverJetzt()) : 0;
  $("clock-banner").hidden = !c.laeuft;
  $("clock-banner-zeit").textContent = Math.ceil(clockRest);
  $("clock-zeit").textContent = c.laeuft ? Math.ceil(clockRest) : $("clock-sekunden").value;
  $("clock-zeit").classList.toggle("laeuft", c.laeuft);
}
setInterval(zeichne, 100);

async function timerAktion(aktion) {
  await api("/api/timer/" + aktion, "POST");
  await holeStatus();
}

$("t-start").addEventListener("click", () => {
  if (!stand || !stand.timer || stand.timer.vorbei) return;
  timerAktion(stand.timer.laeuft ? "pause" : "start");
});
$("t-naechstes").addEventListener("click", () => timerAktion("naechstes"));
$("t-vorheriges").addEventListener("click", () => timerAktion("vorheriges"));
$("t-plus").addEventListener("click", () => timerAktion("plus"));
$("t-minus").addEventListener("click", () => timerAktion("minus"));

async function ladeVorlagenListe() {
  const daten = await api("/api/vorlagen");
  for (const id of ["timer-vorlage", "timer-vorlage-2", "s-vorlage"]) {
    const auswahl = $(id);
    const vorher = auswahl.value;
    auswahl.innerHTML = daten.namen.map((n) => `<option>${esc(n)}</option>`).join("");
    if (daten.namen.includes(vorher)) auswahl.value = vorher;
  }
}

async function vorlageInTimer(name, knopf) {
  if (stand && stand.timer && stand.timer.laeuft &&
      !bestaetigt(knopf, "Timer läuft – wirklich neu laden?")) return;
  await api("/api/timer/laden", "POST", { vorlage: name });
  await holeStatus();
  zeigeTimerKopf();
}
$("timer-vorlage-laden").addEventListener("click",
  () => vorlageInTimer($("timer-vorlage").value, $("timer-vorlage-laden")));
$("timer-vorlage-laden-2").addEventListener("click",
  () => vorlageInTimer($("timer-vorlage-2").value, $("timer-vorlage-laden-2")));

// ---------------- Clock ----------------

document.querySelectorAll("button.dauer").forEach((b) => {
  b.addEventListener("click", () => ($("clock-sekunden").value = b.dataset.sekunden));
});
$("clock-start").addEventListener("click", async () => {
  await api("/api/clock/start", "POST", { sekunden: Number($("clock-sekunden").value) });
  await holeStatus();
});
async function clockStopp() {
  await api("/api/clock/stop", "POST");
  await holeStatus();
}
$("clock-stopp").addEventListener("click", clockStopp);
$("clock-banner-stopp").addEventListener("click", clockStopp);

// ---------------- Blindstruktur bearbeiten ----------------

let struktur = [];

function zeichneStruktur() {
  let nummer = 0;
  const zeilen = struktur.map((lvl, i) => {
    if (lvl.pause) {
      return `<tr class="pause"><td>☕</td><td colspan="3">Pause</td>
        <td><input data-i="${i}" data-feld="minuten" type="number" value="${lvl.minuten}"></td>
        <td><button class="klein-knopf" data-weg="${i}">✕</button></td></tr>`;
    }
    nummer += 1;
    const feld = (name) =>
      `<td><input data-i="${i}" data-feld="${name}" type="number" inputmode="numeric" value="${lvl[name] ?? 0}"></td>`;
    return `<tr><td>${nummer}</td>${feld("small_blind")}${feld("big_blind")}${feld("ante")}${feld("minuten")}
      <td><button class="klein-knopf" data-weg="${i}">✕</button></td></tr>`;
  });
  $("s-tabelle").querySelector("tbody").innerHTML = zeilen.join("");
}

$("s-tabelle").addEventListener("input", (e) => {
  const el = e.target;
  if (el.dataset.i === undefined) return;
  struktur[Number(el.dataset.i)][el.dataset.feld] = Number(el.value);
});
$("s-tabelle").addEventListener("click", (e) => {
  const weg = e.target.dataset.weg;
  if (weg === undefined) return;
  struktur.splice(Number(weg), 1);
  zeichneStruktur();
});

$("s-plus-level").addEventListener("click", () => {
  // Vorschlag: letztes Spiel-Level verdoppeln
  const letzte = [...struktur].reverse().find((l) => !l.pause);
  const neu = letzte
    ? { small_blind: letzte.small_blind * 2, big_blind: letzte.big_blind * 2,
        ante: letzte.ante * 2, minuten: letzte.minuten }
    : { small_blind: 25, big_blind: 50, ante: 0, minuten: 15 };
  struktur.push(neu);
  zeichneStruktur();
});
$("s-plus-pause").addEventListener("click", () => {
  struktur.push({ pause: true, minuten: 10 });
  zeichneStruktur();
});

async function strukturAusVorlage() {
  await ladeVorlagenListe();
  const name = $("s-vorlage").value;
  if (!name) return;
  const daten = await api("/api/vorlagen/" + encodeURIComponent(name));
  struktur = daten.levels;
  $("s-name").value = name;
  zeichneStruktur();
}
$("s-laden").addEventListener("click", strukturAusVorlage);

$("s-speichern").addEventListener("click", async () => {
  await api("/api/vorlagen", "POST", { name: $("s-name").value, levels: struktur });
  await ladeVorlagenListe();
  meldung("Vorlage gespeichert", true);
});
$("s-loeschen").addEventListener("click", async () => {
  const name = $("s-vorlage").value;
  if (!bestaetigt($("s-loeschen"), "Wirklich löschen?")) return;
  await api("/api/vorlagen/" + encodeURIComponent(name), "DELETE");
  await ladeVorlagenListe();
});
$("s-verwenden").addEventListener("click", async () => {
  if (stand && stand.timer && stand.timer.laeuft &&
      !bestaetigt($("s-verwenden"), "Timer läuft – wirklich ersetzen?")) return;
  await api("/api/timer/laden", "POST", { levels: struktur, name: $("s-name").value || "Eigene Struktur" });
  await holeStatus();
  zeigeTimerKopf();
  zeigeTab("timer");
});

// ---------------- Spielerliste (Vorschlaege beim Tippen) ----------------

async function ladeSpielerliste() {
  const daten = await api("/api/spieler");
  $("spielerliste").innerHTML = daten.namen.map((n) => `<option value="${esc(n)}">`).join("");
}

function prozenteLesen(text) {
  // "60/30/10" -> [60, 30, 10]
  return text.split(/[\/,; ]+/).filter((t) => t.trim() !== "").map(Number);
}

async function offeneAbende(art, ziel, beimKlick) {
  const daten = await api("/api/abende");
  const offen = daten.abende.filter((a) => a.art === art && !a.beendet);
  $(ziel).innerHTML = offen.length === 0
    ? '<p class="klein">Keine.</p>'
    : offen.map((a) => `<button class="klein-knopf" data-id="${a.id}">
        ${esc(a.name || "ohne Name")} · ${esc(a.zeitpunkt.slice(0, 10))}</button>`).join(" ");
  $(ziel).querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => beimKlick(Number(b.dataset.id)));
  });
}

// ---------------- Turnier-Kasse ----------------

function turnierId() {
  const id = speicher("turnier_id");
  return id ? Number(id) : null;
}

async function ladeTurnier() {
  ladeSpielerliste();
  const id = turnierId();
  $("turnier-neu").hidden = id !== null;
  $("turnier-detail").hidden = id === null;
  if (id === null) {
    offeneAbende("turnier", "turnier-offene", (neueId) => {
      speicher("turnier_id", neueId);
      ladeTurnier();
    });
    return;
  }
  try {
    zeichneTurnier(await api("/api/turnier/" + id));
  } catch (e) {
    speicher("turnier_id", null);
    ladeTurnier();
  }
}

function zeichneTurnier(u) {
  $("tu-eintraege").textContent = u.eintraege;
  $("tu-preisgeld").textContent = euro(u.preisgeld_cent);
  $("tu-imspiel").textContent = `${u.im_spiel} / ${u.spieler_gesamt}`;
  $("tu-preise").textContent =
    `Buy-in ${euro(u.buyin_cent)} · Rebuy ${euro(u.rebuy_cent)} · Add-on ${euro(u.addon_cent)}` +
    ` · ${u.rebuys} Rebuys, ${u.addons} Add-ons` + (u.beendet ? " · abgeschlossen" : "");
  $("tu-auszahlung").querySelector("tbody").innerHTML = u.auszahlung.map((p) =>
    `<tr><td>${p.platz}.</td><td>${p.prozent} %</td><td class="zahl">${euro(p.betrag_cent)}</td>
     <td>${esc(p.name || "")}</td></tr>`).join("");
  $("tu-auszahlung-neu").placeholder = u.auszahlung.map((p) => p.prozent).join("/");

  const sortiert = [...u.spieler].sort((a, b) => (a.platz ?? 0) - (b.platz ?? 0));
  $("tu-spieler").querySelector("tbody").innerHTML = sortiert.map((s) => {
    const n = esc(s.name);
    let knoepfe;
    if (u.beendet) {
      knoepfe = `<span class="${s.ausgezahlt_cent - s.eingezahlt_cent >= 0 ? "plus" : "minus"}">
        ${euroVorzeichen(s.ausgezahlt_cent - s.eingezahlt_cent)}</span>`;
    } else if (s.platz === null) {
      knoepfe = `<button class="klein-knopf" data-art="rebuy" data-name="${n}">Rebuy</button>
        <button class="klein-knopf" data-art="addon" data-name="${n}">Add-on</button>
        <button class="klein-knopf gefahr" data-aus="${n}">Raus</button>`;
    } else if (s.platz === 1) {
      knoepfe = "🏆 Sieger";
    } else {
      knoepfe = `<button class="klein-knopf" data-art="rebuy" data-name="${n}">Rebuy</button>
        <button class="klein-knopf" data-zurueck="${n}">Zurück</button>`;
    }
    return `<tr class="${s.platz ? "raus" : ""}"><td>${s.platz ? s.platz + "." : ""}</td>
      <td>${n}</td><td class="zahl">${euro(s.eingezahlt_cent)}</td><td>${knoepfe}</td></tr>`;
  }).join("");
}

$("tu-spieler").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const id = turnierId();
  if (b.dataset.art) {
    zeichneTurnier(await api(`/api/turnier/${id}/buchen`, "POST", { name: b.dataset.name, art: b.dataset.art }));
  } else if (b.dataset.aus) {
    if (!bestaetigt(b, "Wirklich raus?")) return;
    const name = b.dataset.aus;
    const u = await api(`/api/turnier/${id}/aus`, "POST", { name });
    zeichneTurnier(u);
    const spieler = u.spieler.find((s) => s.name === name);
    meldung(`${name} ist raus – Platz ${spieler ? spieler.platz : "?"}`, true);
  } else if (b.dataset.zurueck) {
    zeichneTurnier(await api(`/api/turnier/${id}/zurueck`, "POST", { name: b.dataset.zurueck }));
  }
});

$("tn-anlegen").addEventListener("click", async () => {
  const daten = await api("/api/turnier", "POST", {
    name: $("tn-name").value,
    buyin: $("tn-buyin").value,
    rebuy: $("tn-rebuy").value,
    addon: $("tn-addon").value,
    auszahlung: prozenteLesen($("tn-auszahlung").value),
  });
  speicher("turnier_id", daten.id);
  ladeTurnier();
});

$("tu-buyin").addEventListener("click", async () => {
  const name = $("tu-name").value.trim();
  if (!name) return meldung("Bitte einen Namen eingeben");
  zeichneTurnier(await api(`/api/turnier/${turnierId()}/buchen`, "POST", { name, art: "buyin" }));
  $("tu-name").value = "";
  ladeSpielerliste();
});

$("tu-auszahlung-aendern").addEventListener("click", async () => {
  const prozente = prozenteLesen($("tu-auszahlung-neu").value);
  zeichneTurnier(await api(`/api/turnier/${turnierId()}/auszahlung`, "POST", { auszahlung: prozente }));
  $("tu-auszahlung-neu").value = "";
});

$("tu-abschliessen").addEventListener("click", async () => {
  if (!bestaetigt($("tu-abschliessen"), "Wirklich abschließen?")) return;
  zeichneTurnier(await api(`/api/turnier/${turnierId()}/abschliessen`, "POST"));
  meldung("Turnier abgeschlossen", true);
});

$("tu-wechseln").addEventListener("click", () => {
  speicher("turnier_id", null);
  ladeTurnier();
});

// ---------------- Cash Game ----------------

function cashId() {
  const id = speicher("cash_id");
  return id ? Number(id) : null;
}

async function ladeCash() {
  ladeSpielerliste();
  const id = cashId();
  $("cash-neu").hidden = id !== null;
  $("cash-detail").hidden = id === null;
  if (id === null) {
    offeneAbende("cash", "cash-offene", (neueId) => {
      speicher("cash_id", neueId);
      ladeCash();
    });
    return;
  }
  try {
    zeichneCash(await api("/api/cash/" + id));
  } catch (e) {
    speicher("cash_id", null);
    ladeCash();
  }
}

const CHIPS = [[10, "10 ct"], [25, "25 ct"], [50, "50 ct"], [100, "1 €"]];

function zeichneCash(u) {
  $("ca-spieler").innerHTML = u.spieler.map((s, i) => {
    const n = esc(s.name);
    const buyins = s.buyins.map((b) =>
      `<div class="zeile"><span>${uhrzeit(b.zeitpunkt)}</span><span>${euro(b.betrag_cent)}</span>
       ${u.beendet ? "" : `<button class="klein-knopf" data-loeschen="${b.id}">✕</button>`}</div>`).join("");
    const ergebnis = s.ergebnis_cent === null ? "" :
      `<span class="${s.ergebnis_cent >= 0 ? "plus" : "minus"}">${euroVorzeichen(s.ergebnis_cent)}</span>`;
    const cashout = u.beendet ? `<p>Cash-out: ${euro(s.cashout_cent)}</p>` : `
      <div class="zeile">
        <input class="kurz" id="co-${i}" placeholder="Cash-out €" inputmode="decimal"
          value="${s.cashout_cent === null ? "" : (s.cashout_cent / 100).toFixed(2).replace(".", ",")}">
        <button class="klein-knopf" data-cashout="${n}" data-feld="co-${i}">Cash-out speichern</button>
        <button class="klein-knopf" data-chips="${i}">Chips zählen</button>
      </div>
      <div class="chips" id="chips-${i}" hidden>
        ${CHIPS.map(([wert, text]) =>
          `<label>${text}<input type="number" min="0" inputmode="numeric" data-chipwert="${wert}" data-ziel="${i}"></label>`).join("")}
      </div>`;
    return `<div class="karte">
      <h3><span>${n}</span>${ergebnis}</h3>
      ${buyins}
      <p class="klein">Buy-ins gesamt: ${euro(s.summe_buyins_cent)}</p>
      ${cashout}
    </div>`;
  }).join("");

  const k = $("ca-kontrolle");
  let text = `Buy-ins: ${euro(u.summe_buyins_cent)} · Cash-outs: ${euro(u.summe_cashouts_cent)}`;
  if (u.offen.length > 0) {
    text += `<br>Cash-out fehlt noch: ${u.offen.map(esc).join(", ")}`;
  } else if (u.differenz_cent !== 0) {
    text += `<br>⚠️ Differenz: ${euroVorzeichen(u.differenz_cent)} – ` +
      (u.differenz_cent > 0 ? "es wurde mehr ausgezahlt als eingezahlt." : "es fehlt Geld bei den Cash-outs.");
  } else {
    text += "<br>✓ Kontrollrechnung stimmt.";
  }
  // Wer zahlt wem? (erst wenn alle einen Cash-out haben)
  if (u.ausgleich) {
    const zahlungen = u.ausgleich.zahlungen;
    text += "<h2>Wer zahlt wem?</h2>";
    if (zahlungen.length === 0) {
      text += "<p>Niemand muss etwas zahlen.</p>";
    } else {
      text += '<table class="ausgleich"><tbody>' + zahlungen.map((z) =>
        `<tr><td>${esc(z.von)}</td><td>→</td><td>${esc(z.an)}</td>
         <td class="zahl"><strong>${euro(z.betrag_cent)}</strong></td></tr>`).join("") +
        "</tbody></table>";
    }
    if (u.ausgleich.rest_cent > 0) {
      text += `<p>⚠️ Den Gewinnern fehlen zusammen noch ${euro(u.ausgleich.rest_cent)} (siehe Differenz oben).</p>`;
    } else if (u.ausgleich.rest_cent < 0) {
      text += `<p>⚠️ Es bleiben ${euro(-u.ausgleich.rest_cent)} übrig (siehe Differenz oben).</p>`;
    }
  }
  k.innerHTML = text;
  k.className = "kontrolle " + (u.stimmt ? "ok" : u.offen.length ? "" : "fehler");
}

$("ca-spieler").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const id = cashId();
  if (b.dataset.loeschen) {
    if (!bestaetigt(b, "Löschen?")) return;
    await api("/api/buchung/" + b.dataset.loeschen, "DELETE");
    zeichneCash(await api("/api/cash/" + id));
  } else if (b.dataset.cashout) {
    const betrag = $(b.dataset.feld).value;
    zeichneCash(await api(`/api/cash/${id}/cashout`, "POST", { name: b.dataset.cashout, betrag }));
  } else if (b.dataset.chips) {
    const el = $("chips-" + b.dataset.chips);
    el.hidden = !el.hidden;
  }
});

// Chips zaehlen: der Server rechnet den Wert aus, wir tragen ihn ins Feld ein
$("ca-spieler").addEventListener("input", async (e) => {
  const el = e.target;
  if (!el.dataset.chipwert) return;
  const ziel = el.dataset.ziel;
  const anzahlen = {};
  $("chips-" + ziel).querySelectorAll("input").forEach((f) => {
    anzahlen[f.dataset.chipwert] = Number(f.value || 0);
  });
  const daten = await api("/api/chipwert", "POST", anzahlen);
  $("co-" + ziel).value = (daten.cent / 100).toFixed(2).replace(".", ",");
});

$("cn-anlegen").addEventListener("click", async () => {
  const daten = await api("/api/cash", "POST", { name: $("cn-name").value });
  speicher("cash_id", daten.id);
  ladeCash();
});

$("ca-buyin").addEventListener("click", async () => {
  const name = $("ca-name").value.trim();
  if (!name) return meldung("Bitte einen Namen eingeben");
  zeichneCash(await api(`/api/cash/${cashId()}/buyin`, "POST", { name, betrag: $("ca-betrag").value }));
  $("ca-name").value = "";
  ladeSpielerliste();
});

$("ca-abschliessen").addEventListener("click", async () => {
  const knopf = $("ca-abschliessen");
  if (knopf.dataset.sicher !== "1") {
    // Beim ersten Tippen pruefen; fehlt noch ein Cash-out, meldet der Server das direkt
    const u = await api("/api/cash/" + cashId());
    if (u.offen.length === 0) {
      const frage = u.differenz_cent !== 0
        ? `Differenz ${euroVorzeichen(u.differenz_cent)} – trotzdem?`
        : "Wirklich abschließen?";
      bestaetigt(knopf, frage);
      return;
    }
  } else {
    zuruecksetzen(knopf);
  }
  zeichneCash(await api(`/api/cash/${cashId()}/abschliessen`, "POST"));
  meldung("Cash Game abgeschlossen", true);
});

$("ca-wechseln").addEventListener("click", () => {
  speicher("cash_id", null);
  ladeCash();
});

// ---------------- Bilanz ----------------

async function ladeBilanz() {
  const daten = await api("/api/bilanz?art=" + $("b-art").value);
  $("b-tabelle").querySelector("tbody").innerHTML = daten.bilanz.map((e) =>
    `<tr><td>${esc(e.name)}</td><td class="zahl">${e.abende}</td>
     <td class="zahl">${euro(e.eingezahlt_cent)}</td><td class="zahl">${euro(e.ausgezahlt_cent)}</td>
     <td class="zahl ${e.saldo_cent >= 0 ? "plus" : "minus"}">${euroVorzeichen(e.saldo_cent)}</td></tr>`).join("") ||
    '<tr><td colspan="5" class="klein">Noch keine abgeschlossenen Abende.</td></tr>';
}
$("b-art").addEventListener("change", ladeBilanz);

// ---------------- Entwicklungsmodus ----------------
// Laeuft der Server mit --entwicklung, fragt die Seite jede Sekunde nach, ob sich
// Dateien geaendert haben (oder der Server neu gestartet ist), und laedt sich neu.

async function entwicklungBeobachten() {
  let erster;
  try {
    const antwort = await fetch("/api/entwicklung/stand");
    if (!antwort.ok) return;          // normaler Betrieb: nichts tun
    erster = await antwort.json();
  } catch (e) {
    return;
  }
  document.body.classList.add("entwicklung");
  setInterval(async () => {
    try {
      const stand = await (await fetch("/api/entwicklung/stand")).json();
      if (stand.start !== erster.start || stand.web !== erster.web) location.reload();
    } catch (e) {
      // Server startet gerade neu - beim naechsten Mal wieder versuchen
    }
  }, 1000);
}
entwicklungBeobachten();

// ---------------- Start ----------------

ladeVorlagenListe();
holeStatus();
zeigeTab(speicher("tab") || "timer");
