// Interface Mac : transcription bilingue, notes, carte, statuts, finalisation.
"use strict";

const $ = (id) => document.getElementById(id);
const STEP_LABELS = { retranscribe: "Re-transcription complète", retranslate: "Re-traduction", summary: "Résumé", write: "Écriture dans Obsidian" };

const ui = {
  sessionId: new URLSearchParams(location.search).get("s"),
  socket: null,
  items: new Map(), // id -> {ts, kind, segment | className+html}
  shownItems: new Set(), // ids d'encadrés déjà affichés (animation d'apparition jouée une seule fois)
  renderPending: false,
  hoverId: null,
  lastSessionId: null,
  segments: new Map(),
  translations: new Map(),
  cost: 0,
  clock: { ts: 0, wall: 0, recording: false },
  steps: {},
  finalizing: false,
  outputPath: "",
  autoScroll: true,
  map: null,
  contextTimer: null,
  stopArmed: false,
  reconnectDelay: 1000,
  arrivals: new Map(), // id de segment -> heure d'arrivée (ms) en direct
  awayAt: null, // heure (ms) où l'utilisateur a quitté le direct
  catchup: null, // {since, until} : surlignage des passages manqués
  catchupTimer: null,
};

function fmtTime(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function toast(text, ms = 3000) {
  const el = $("toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* rien */ }
    throw new Error(detail);
  }
  return response.json();
}

// ---------- accueil ----------

function goHome() {
  // Quitte la session affichée (elle continue côté serveur : finalisation, etc.).
  const socket = ui.socket;
  ui.socket = null;
  if (socket) socket.close();
  if (ui.sessionId) ui.lastSessionId = ui.sessionId;
  ui.sessionId = null;
  resetView();
  history.replaceState(null, "", "/");
  document.title = "confmap";
  document.querySelectorAll(".overlay").forEach((el) => el.classList.add("hidden"));
  showHome();
}

async function showHome() {
  $("home").classList.remove("hidden");
  const list = $("sessionList");
  list.innerHTML = "";
  let sessions = [];
  try { sessions = await api("/api/sessions"); } catch (error) { toast(error.message); }
  if (!sessions.length) list.innerHTML = "<li class='meta'>Aucune session.</li>";
  for (const session of sessions) {
    const li = document.createElement("li");
    const date = new Date(session.created_at * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
    const state = session.recording ? "● en cours" : session.finalized ? "✓ finalisée" : session.finalizing ? "… finalisation" : "non finalisée";
    li.innerHTML = `<div><div>${escapeHtml(session.title || "(sans titre)")}</div><div class="meta">${date} · ${state}</div></div>`;
    const open = document.createElement("button");
    open.className = "btn";
    open.textContent = "Ouvrir";
    open.onclick = () => openSession(session.id);
    li.appendChild(open);
    list.appendChild(li);
  }
}

async function newSession() {
  try {
    const session = await api("/api/sessions", { method: "POST" });
    openSession(session.id);
    setTimeout(() => $("titleInput").focus(), 100);
  } catch (error) {
    toast(error.message, 5000);
  }
}

function openSession(id) {
  ui.sessionId = id;
  history.replaceState(null, "", `/?s=${id}`);
  $("home").classList.add("hidden");
  connect();
}

// ---------- WebSocket ----------

function resetClock() {
  ui.clock = { ts: 0, wall: Date.now() / 1000, recording: false };
  updateRecBadge();
}

function resetView() {
  resetClock();
  ui.items.clear();
  ui.segments.clear();
  ui.translations.clear();
  ui.cost = 0;
  renderCost();
  ui.arrivals.clear();
  ui.awayAt = null;
  ui.catchup = null;
  $("catchup").classList.add("hidden");
  setBadge("whisperBadge", "Transcription : en attente", "");
  setBadge("netBadge", "Traduction/IA : en attente", "");
  ui.steps = {};
  ui.outputPath = "";
  $("rows").innerHTML = "";
  ui.shownItems.clear();
  ui.map.cy.elements().remove();
  ui.map.signatures.clear();
  ui.map.placed.clear();
}

function connect() {
  if (ui.socket) ui.socket.close();
  const socket = new WebSocket(`ws://${location.host}/ws/${ui.sessionId}`);
  ui.socket = socket;
  socket.onmessage = (message) => {
    if (socket !== ui.socket) return; // ancienne session
    const data = JSON.parse(message.data);
    if (data.type === "snapshot") {
      resetView();
      const positions = {};
      for (const event of data.events) if (event.type === "map_positions") Object.assign(positions, event.positions);
      ui.map.setSavedPositions(positions);
      let lastMap = null;
      for (const event of data.events) {
        if (event.type === "map_update") { lastMap = event; continue; }
        handleEvent(event, true);
      }
      if (lastMap) renderMap(lastMap, true);
      ui.autoScroll = true;
      ui.reconnectDelay = 1000;
      refreshSessionInfo();
    } else {
      handleEvent(data, false);
    }
  };
  socket.onclose = (event) => {
    if (socket !== ui.socket) return;
    if (event.code === 4404) { toast("Session introuvable"); showHome(); return; }
    setBadge("netBadge", "✗ Serveur injoignable", "bad");
    setTimeout(connect, ui.reconnectDelay);
    ui.reconnectDelay = Math.min(ui.reconnectDelay * 2, 10000);
  };
}

async function refreshSessionInfo() {
  try {
    const info = await api(`/api/sessions/${ui.sessionId}`);
    if (info.id !== ui.sessionId) return; // réponse tardive d'une autre session
    ui.clock.recording = info.recording;
    ui.finalizing = info.finalizing;
    ui.clock.ts = Math.max(ui.clock.ts, info.elapsed || 0);
    ui.clock.wall = Date.now() / 1000;
    $("stopBtn").textContent = info.finalized ? "✓ Finalisée" : "■ Fin";
    $("stopBtn").dataset.mode = info.finalized ? "done" : "stop";
    const pause = $("pauseBtn");
    pause.disabled = false;
    pause.classList.toggle("hidden", info.finalized || info.finalizing);
    pause.textContent = info.recording ? "⏸ Pause" : "▶ Reprendre";
    pause.dataset.mode = info.recording ? "pause" : "resume";
    if (info.finalizing || (Object.keys(info.finalize_steps).length && !info.finalized)) showFinalModal();
    else renderFinalSteps();
    updateRecBadge();
  } catch (_) { /* hors ligne */ }
}

// ---------- événements ----------

function handleEvent(event, replay) {
  if (typeof event.ts === "number" && event.type !== "finalize_step") {
    ui.clock.ts = Math.max(ui.clock.ts, event.ts);
    ui.clock.wall = Date.now() / 1000;
  }
  switch (event.type) {
    case "context":
      if (document.activeElement !== $("titleInput")) $("titleInput").value = event.title;
      if (document.activeElement !== $("speakerInput")) $("speakerInput").value = event.speaker;
      document.title = event.title ? `${event.title} · confmap` : "confmap";
      break;
    case "segment":
      if (event.final) break;
      if (!replay && !ui.segments.has(event.id)) ui.arrivals.set(event.id, Date.now());
      ui.segments.set(event.id, event);
      upsertSegment(event);
      setBadge("whisperBadge", "✓ Transcription", "ok");
      break;
    case "translation":
      ui.translations.set(event.segment_id, event.text_fr);
      if (ui.segments.has(event.segment_id)) scheduleRender();
      break;
    case "note":
      upsertItem(event.id, event.ts, "item note", `📝 ${escapeHtml(event.text)}`);
      break;
    case "slide": {
      const text = event.status === "done" ? (event.text_fr ? `📷 ${renderMini(event.text_fr)}` : "📷 (rien d'informatif sur la photo)")
        : event.status === "error" ? `📷 analyse en échec : ${escapeHtml(event.text_fr)}` : "📷 analyse de la photo…";
      upsertItem(event.id, event.ts, `item slide ${event.status === "pending" ? "pending" : ""}`, text);
      break;
    }
    case "map_update":
      renderMap(event, replay);
      break;
    case "status":
      handleStatus(event, replay);
      break;
    case "llm_usage":
      ui.cost += event.cost_usd || 0;
      if (event.ok && $("netBadge").className.indexOf("bad") === -1) setBadge("netBadge", "✓ Traduction/IA", "ok");
      renderCost();
      break;
    case "finalize_step":
      ui.steps[event.step] = event;
      if (event.output_path) ui.outputPath = event.output_path;
      if (!replay) showFinalModal();
      renderFinalSteps();
      break;
  }
}

function handleStatus(event, replay) {
  if (event.component === "audio") {
    ui.clock.recording = event.state === "recording";
    if (event.state === "error") { setBadge("recBadge", "✗ Micro", "bad pulse"); if (!replay) toast(`Micro : ${event.detail}`, 6000); }
    updateRecBadge();
    if (!replay) refreshSessionInfo();
  } else if (event.component === "whisper") {
    if (event.state === "fallback") { setBadge("whisperBadge", "⚠ Transcription (modèle léger)", "warn"); if (!replay) toast(`Transcription trop lente : ${event.detail}`, 5000); }
    else if (event.state === "error") setBadge("whisperBadge", "✗ Transcription", "bad");
  } else if (event.component === "network") {
    if (event.state === "down") setBadge("netBadge", `✗ Traduction/IA (${event.pending} en attente)`, "bad");
    else setBadge("netBadge", "✓ Traduction/IA", "ok");
  } else if (event.component === "llm" && event.state === "error" && !replay) {
    toast(event.detail, 5000);
  }
}

function setBadge(id, text, level) {
  const el = $(id);
  el.textContent = text;
  el.className = `badge ${level || ""}`;
}

function renderCost() {
  $("costBadge").textContent = `${ui.cost.toFixed(3).replace(".", ",")} $`;
}

function updateRecBadge() {
  const now = ui.clock.recording ? ui.clock.ts + (Date.now() / 1000 - ui.clock.wall) : ui.clock.ts;
  if (ui.clock.recording) setBadge("recBadge", `REC ${fmtTime(now)}`, "rec");
  else setBadge("recBadge", `⏸ Pause ${fmtTime(now)}`, "warn pulse");
}

// ---------- transcription ----------
// Deux colonnes alignées par paragraphe : original | français.
// Les segments s'enchaînent dans un paragraphe ; on en ouvre un nouveau après une pause,
// au bout d'une minute, ou quand une note / une photo s'intercale.

const PARAGRAPH_GAP = 4;
const PARAGRAPH_MAX = 30;
const LANG_NAMES = { en: "anglais", es: "espagnol", de: "allemand", it: "italien", pt: "portugais", fr: "français", nl: "néerlandais", zh: "chinois", ja: "japonais", ru: "russe", ar: "arabe" };

function upsertSegment(segment) {
  ui.items.set(segment.id, { ts: segment.t0, kind: "seg", segment });
  scheduleRender();
}

function upsertItem(id, ts, className, html) {
  ui.items.set(id, { ts, kind: "item", className, html });
  scheduleRender();
}

function scheduleRender() {
  if (ui.renderPending) return;
  ui.renderPending = true;
  requestAnimationFrame(() => {
    ui.renderPending = false;
    renderTranscript();
    if (ui.autoScroll) scrollToBottom();
  });
}

function buildParagraphs() {
  const entries = [...ui.items.entries()].sort((a, b) => a[1].ts - b[1].ts);
  const rows = [];
  let paragraph = null;
  for (const [id, entry] of entries) {
    if (entry.kind === "item") {
      rows.push({ type: "item", id, entry });
      paragraph = null;
      continue;
    }
    const segment = entry.segment;
    const startsNew = !paragraph
      || segment.t0 - paragraph.t1 > PARAGRAPH_GAP
      || segment.t1 - paragraph.t0 > PARAGRAPH_MAX;
    if (startsNew) {
      paragraph = { type: "para", t0: segment.t0, t1: segment.t1, segments: [] };
      rows.push(paragraph);
    }
    paragraph.segments.push(segment);
    paragraph.t1 = Math.max(paragraph.t1, segment.t1);
  }
  return rows;
}

function renderTranscript() {
  const rows = buildParagraphs();
  const liveNow = liveClock();
  const languages = {};
  // Le dernier paragraphe parlé est mis en avant, les précédents sont atténués.
  let currentIndex = -1;
  rows.forEach((row, index) => { if (row.type !== "item") currentIndex = index; });
  const html = rows.map((row, index) => {
    if (row.type === "item") {
      // L'animation d'apparition ne joue qu'une fois : le rendu complet est refait chaque seconde.
      const fresh = ui.shownItems.has(row.id) ? "" : " fresh";
      ui.shownItems.add(row.id);
      return `<div class="row-item ${row.entry.className}${fresh}" data-id="${row.id}">${row.entry.html}</div>`;
    }
    let original = "", french = "";
    for (const segment of row.segments) {
      languages[segment.lang] = (languages[segment.lang] || 0) + 1;
      const translation = ui.translations.get(segment.id);
      if (segment.lang !== "fr") original += `<span class="s${missedClass(segment.id)}" data-id="${segment.id}">${escapeHtml(segment.text)}</span> `;
      const text = segment.lang === "fr" ? segment.text : translation || "…";
      const pending = segment.lang !== "fr" && !translation ? " pending" : "";
      const waited = pending ? Math.floor(liveNow - segment.t1) : 0;
      const latency = waited >= 3 ? ` <span class="lat">${waited} s</span>` : "";
      french += `<span class="s${pending}${missedClass(segment.id)}" data-id="${segment.id}">${escapeHtml(text)}${latency}</span> `;
    }
    const time = `<span class="time">${fmtTime(row.t0)}</span>`;
    const current = index === currentIndex ? " current" : "";
    return `<div class="cell orig${current}">${time}${original}</div><div class="cell fr${current}">${original ? "" : time}${french}</div>`;
  }).join("");
  $("rows").innerHTML = html;
  const dominant = Object.entries(languages).sort((a, b) => b[1] - a[1])[0];
  $("origHeader").textContent = dominant ? `Original (${LANG_NAMES[dominant[0]] || dominant[0]})` : "Original";
}

function missedClass(segmentId) {
  const catchup = ui.catchup;
  if (!catchup || Date.now() > catchup.until) return "";
  return (ui.arrivals.get(segmentId) || 0) >= catchup.since ? " missed" : "";
}

function liveClock() {
  return ui.clock.recording ? ui.clock.ts + (Date.now() / 1000 - ui.clock.wall) : ui.clock.ts;
}

// ---------- rattrapage ----------
// Quand l'utilisateur a quitté le direct, on mémorise l'heure ; à son retour, une ligne résume
// ce qui est arrivé pendant l'absence (passages de transcription, nœuds de la carte, sujet).

function markAway() {
  if (ui.awayAt === null) ui.awayAt = Date.now();
}

function showCatchup() {
  const since = ui.awayAt;
  ui.awayAt = null;
  if (since === null) return;
  const seconds = Math.round((Date.now() - since) / 1000);
  if (seconds < 5) return;
  const paragraphs = buildParagraphs().filter((row) => row.type === "para"
    && row.segments.some((segment) => (ui.arrivals.get(segment.id) || 0) >= since));
  const map = ui.map;
  const mapInfo = map && typeof map.markSince === "function" ? (map.markSince(since) || {}) : {};
  const nodes = mapInfo.count || 0;
  if (!paragraphs.length && !nodes) return;
  const parts = [`${paragraphs.length} passage${paragraphs.length > 1 ? "s" : ""}`];
  if (nodes) parts.push(`${nodes} nœud${nodes > 1 ? "s" : ""}`);
  const topics = [].concat(mapInfo.topics || []).filter(Boolean);
  const subject = topics.length ? ` — sujet : ${topics.slice(0, 2).join(", ")}` : "";
  $("catchupText").textContent = `Pendant votre absence (${fmtDuration(seconds)}) : ${parts.join(", ")}${subject}`;
  $("catchup").classList.remove("hidden");
  ui.catchup = { since, until: Date.now() + 8000 };
  clearTimeout(ui.catchupTimer);
  ui.catchupTimer = setTimeout(() => { ui.catchup = null; scheduleRender(); }, 8100);
  clearTimeout(showCatchup.hideTimer);
  showCatchup.hideTimer = setTimeout(() => $("catchup").classList.add("hidden"), 15000);
  scheduleRender();
}

function onTranscriptHover(event) {
  const span = event.target.closest(".s");
  const id = span ? span.dataset.id : null;
  if (id === ui.hoverId) return;
  ui.hoverId = id;
  $("rows").querySelectorAll(".s.hover").forEach((el) => el.classList.remove("hover"));
  if (id) $("rows").querySelectorAll(`.s[data-id="${id}"]`).forEach((el) => el.classList.add("hover"));
}

function onTranscriptClick(event) {
  const target = event.target.closest("[data-id]");
  if (!target) return;
  const hits = ui.map.highlightSources(target.dataset.id);
  if (!hits) toast("Pas encore dans la carte", 1500);
}

function scrollToBottom() {
  const container = $("transcript");
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function renderMini(markdown) {
  return escapeHtml(markdown).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

// ---------- carte ----------

function renderMap(event, replay) {
  $("mapEmpty").classList.toggle("hidden", (event.topics || []).length > 0);
  ui.map.render(event.topics || [], replay ? [] : event.added_node_ids || [], event.source_text || "");
}

// ---------- finalisation ----------

function showFinalModal() {
  $("finalModal").classList.remove("hidden");
  renderFinalSteps();
}

function renderFinalSteps() {
  const list = $("finalSteps");
  list.innerHTML = "";
  let failed = false;
  for (const step of Object.keys(STEP_LABELS)) {
    const event = ui.steps[step];
    const li = document.createElement("li");
    li.className = event ? event.state : "";
    li.textContent = STEP_LABELS[step] + (event && event.state === "error" ? ` : ${event.detail}` : "");
    if (event && event.state === "error") failed = true;
    list.appendChild(li);
  }
  // Interrompue (serveur relancé) : aucune tâche ne tourne, il faut pouvoir reprendre.
  const interrupted = !ui.finalizing && !ui.outputPath && Object.keys(ui.steps).length > 0;
  $("retryFinalBtn").classList.toggle("hidden", !failed && !interrupted);
  const result = $("finalResult");
  if (ui.outputPath) {
    const noteName = ui.outputPath.split("/").pop().replace(/\.md$/, "");
    result.innerHTML = `<div>Note écrite dans Obsidian :</div>`
      + `<div class="note-name"><a href="obsidian://open?path=${encodeURIComponent(ui.outputPath)}">${escapeHtml(noteName)}</a></div>`
      + `<div class="meta-line">Durée de la conférence : ${fmtDuration(ui.clock.ts)}</div>`;
    result.title = ui.outputPath;
    $("copyPathBtn").classList.remove("hidden");
    $("stopBtn").dataset.mode = "done";
    $("stopBtn").textContent = "✓ Finalisée";
  } else {
    $("copyPathBtn").classList.add("hidden");
    result.textContent = failed ? "La finalisation s'est arrêtée sur une erreur."
      : interrupted ? "La finalisation a été interrompue (serveur relancé)."
      : "En cours… (tu peux fermer cette fenêtre)";
  }
}

async function onPause() {
  const button = $("pauseBtn");
  const action = button.dataset.mode === "resume" ? "resume" : "pause";
  button.disabled = true;
  button.textContent = "…";
  try {
    await api(`/api/sessions/${ui.sessionId}/${action}`, { method: "POST" });
    if (action === "pause") ui.clock.recording = false;
  } catch (error) {
    toast(error.message, 5000);
  }
  refreshSessionInfo();
}

async function onStop() {
  const button = $("stopBtn");
  const mode = button.dataset.mode || "stop";
  if (mode === "done") { showFinalModal(); return; }
  if (!ui.stopArmed) {
    ui.stopArmed = true;
    button.textContent = "Confirmer ?";
    setTimeout(() => { ui.stopArmed = false; if (button.textContent === "Confirmer ?") button.textContent = "■ Fin"; }, 3000);
    return;
  }
  ui.stopArmed = false;
  button.textContent = "…";
  try {
    await api(`/api/sessions/${ui.sessionId}/stop`, { method: "POST" });
    showFinalModal();
  } catch (error) {
    toast(error.message, 5000);
  }
}

// ---------- menu des finalisations ----------

const FINAL_STATES = {
  running: "… en cours", interrupted: "⏸ interrompue", error: "✗ en échec",
  done: "✓ terminée", not_started: "non finalisée",
};

function fmtDuration(seconds) {
  return seconds < 60 ? `${Math.round(seconds)} s` : `${Math.floor(seconds / 60)} min ${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

async function showFinalizations() {
  $("finalsModal").classList.remove("hidden");
  await refreshFinalizations();
  clearInterval(ui.finalsTimer);
  ui.finalsTimer = setInterval(() => {
    if ($("finalsModal").classList.contains("hidden")) { clearInterval(ui.finalsTimer); return; }
    refreshFinalizations();
  }, 2000);
}

async function refreshFinalizations() {
  let items = [];
  try { items = await api("/api/finalizations"); } catch (error) { toast(error.message); return; }
  const now = Date.now() / 1000;
  const list = $("finalsList");
  list.innerHTML = items.length ? "" : "<li class='meta'>Aucune session.</li>";
  for (const item of items) {
    const li = document.createElement("li");
    const date = new Date(item.created_at * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
    const steps = Object.keys(STEP_LABELS).map((name) => {
      const step = item.steps[name];
      const state = step ? step.state : "todo";
      const icon = { done: "✓", running: "…", error: "✗", todo: "·" }[state];
      let extra = "";
      if (step && step.started) {
        const end = state === "running" ? now : step.ended || now;
        extra = ` ${fmtDuration(end - step.started)}`;
      }
      if (state === "running" && item.progress) extra += `, ${item.progress}`;
      return `<span class="${state}">${icon} ${STEP_LABELS[name]}${extra}</span>`;
    }).join(" · ");
    const errors = Object.entries(item.steps).filter(([, step]) => step.state === "error")
      .map(([name, step]) => `<div class="err">${STEP_LABELS[name]} : ${escapeHtml(step.detail)}</div>`).join("");
    const issue = item.issue ? `<div class="issue">⚠ ${escapeHtml(item.issue)} — nouvel essai en cours</div>` : "";
    const note = item.output_path ? `<div class="meta"><a href="obsidian://open?path=${encodeURIComponent(item.output_path)}">Ouvrir la note dans Obsidian</a></div>` : "";
    li.innerHTML = `<div class="head"><div><div>${escapeHtml(item.title || "(sans titre)")}</div>`
      + `<div class="meta">${date} · ${FINAL_STATES[item.state] || item.state}</div></div><div class="actions"></div></div>`
      + `<div class="steps">${steps}</div>${issue}${errors}${note}`;
    const actions = li.querySelector(".actions");
    if (["interrupted", "error", "not_started"].includes(item.state)) {
      const relaunch = document.createElement("button");
      relaunch.className = "btn btn-primary";
      relaunch.textContent = item.state === "not_started" ? "Finaliser" : "Reprendre";
      relaunch.onclick = async () => {
        relaunch.disabled = true;
        try { await api(`/api/sessions/${item.id}/finalize`, { method: "POST" }); } catch (error) { toast(error.message, 5000); }
        refreshFinalizations();
      };
      actions.appendChild(relaunch);
    }
    const open = document.createElement("button");
    open.className = "btn";
    open.textContent = "Ouvrir";
    open.onclick = () => { $("finalsModal").classList.add("hidden"); if (ui.sessionId !== item.id) { goHome(); openSession(item.id); } };
    actions.appendChild(open);
    list.appendChild(li);
  }
}

// ---------- initialisation ----------

function sendContext() {
  clearTimeout(ui.contextTimer);
  ui.contextTimer = setTimeout(() => {
    api(`/api/sessions/${ui.sessionId}/context`, {
      method: "POST",
      body: JSON.stringify({ title: $("titleInput").value, speaker: $("speakerInput").value }),
    }).catch((error) => toast(error.message));
  }, 700);
}

async function sendNote() {
  const text = $("noteInput").value.trim();
  if (!text) return;
  $("noteInput").value = "";
  try {
    await api(`/api/sessions/${ui.sessionId}/notes`, { method: "POST", body: JSON.stringify({ text }) });
    ui.autoScroll = true;
  } catch (error) {
    $("noteInput").value = text;
    toast(error.message);
  }
}

function init() {
  ui.map = new IdeaMap($("map"), {
    onPositions: (positions) => {
      if (!ui.sessionId) return;
      api(`/api/sessions/${ui.sessionId}/map/positions`, { method: "POST", body: JSON.stringify({ positions }) }).catch(() => {});
    },
  });
  $("newBtn").onclick = newSession;
  $("homeBtn").onclick = goHome;
  $("brand").onclick = goHome;
  $("finalNewBtn").onclick = () => { goHome(); newSession(); };
  $("titleInput").oninput = sendContext;
  $("speakerInput").oninput = sendContext;
  $("noteInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendNote(); }
  });
  $("noteForm").onsubmit = (event) => { event.preventDefault(); sendNote(); };
  $("forceBtn").onclick = () => api(`/api/sessions/${ui.sessionId}/map/force`, { method: "POST" }).then(() => toast("Mise à jour de la carte demandée", 1500)).catch((e) => toast(e.message));
  $("fitBtn").onclick = () => { ui.map.fit(true); toast("Vue d'ensemble — le suivi reprend à la prochaine mise à jour", 2000); };
  $("tidyBtn").onclick = () => ui.map.tidy();
  $("sourceBtn").onclick = () => {
    const box = $("sourceBox");
    box.textContent = ui.map.lastSource || "Aucune mise à jour pour l'instant.";
    box.classList.toggle("hidden");
  };
  $("qrBtn").onclick = async () => {
    const info = await api(`/api/sessions/${ui.sessionId}`);
    $("qrImg").src = `/api/sessions/${ui.sessionId}/qr.svg?ts=${Date.now()}`;
    $("captureLink").href = info.capture_url;
    $("captureLink").textContent = info.capture_url;
    $("qrModal").classList.remove("hidden");
  };
  $("stopBtn").onclick = onStop;
  $("finalsBtn").onclick = showFinalizations;
  $("homeFinalsBtn").onclick = showFinalizations;
  $("pauseBtn").onclick = onPause;
  $("copyPathBtn").onclick = () => {
    navigator.clipboard.writeText(ui.outputPath)
      .then(() => toast("Chemin copié", 1500))
      .catch(() => toast(ui.outputPath, 6000));
  };
  $("retryFinalBtn").onclick = () => api(`/api/sessions/${ui.sessionId}/finalize`, { method: "POST" })
    .then(() => { ui.finalizing = true; renderFinalSteps(); })
    .catch((e) => toast(e.message));
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.onclick = () => button.closest(".overlay").classList.add("hidden");
  });
  const transcript = $("transcript");
  transcript.addEventListener("scroll", () => {
    const atBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 40;
    ui.autoScroll = atBottom;
    $("jumpBtn").classList.toggle("hidden", atBottom);
    if (!atBottom) markAway();
    else if (ui.awayAt !== null) showCatchup();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) markAway();
    else if (ui.autoScroll) showCatchup();
  });
  $("catchupClose").onclick = () => { $("catchup").classList.add("hidden"); ui.catchup = null; scheduleRender(); };
  transcript.addEventListener("mouseover", onTranscriptHover);
  transcript.addEventListener("click", onTranscriptClick);
  $("jumpBtn").onclick = () => { ui.autoScroll = true; showCatchup(); scrollToBottom(); };
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = [...document.querySelectorAll(".overlay:not(.hidden)")];
    if (!open.length) return;
    for (const overlay of open) {
      if (overlay.id !== "home") overlay.classList.add("hidden");
    }
    // L'accueil ne se ferme que s'il y a une session derrière.
    if (!$("home").classList.contains("hidden") && open.every((o) => o.id === "home") && ui.lastSessionId) {
      openSession(ui.lastSessionId);
    }
  });
  setInterval(() => {
    updateRecBadge();
    if (ui.clock.recording && document.querySelector(".s.pending")) scheduleRender();
  }, 1000);
  if (ui.sessionId) openSession(ui.sessionId);
  else showHome();
}

init();
