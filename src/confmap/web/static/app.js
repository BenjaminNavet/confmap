// Interface Mac : transcription bilingue, notes, carte, statuts, finalisation.
"use strict";

const $ = (id) => document.getElementById(id);
const STEP_LABELS = { retranscribe: "Re-transcription complète", retranslate: "Re-traduction", summary: "Résumé", write: "Écriture dans Obsidian" };

const ui = {
  sessionId: new URLSearchParams(location.search).get("s"),
  socket: null,
  items: new Map(), // id -> {ts, el}
  segments: new Map(),
  translations: new Map(),
  cost: 0,
  clock: { ts: 0, wall: 0, recording: false },
  steps: {},
  outputPath: "",
  autoScroll: true,
  map: null,
  contextTimer: null,
  stopArmed: false,
  reconnectDelay: 1000,
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

function resetView() {
  ui.items.clear();
  ui.segments.clear();
  ui.translations.clear();
  ui.cost = 0;
  ui.steps = {};
  ui.outputPath = "";
  $("transcript").innerHTML = "";
  ui.map.cy.elements().remove();
  ui.map.signatures.clear();
}

function connect() {
  if (ui.socket) ui.socket.close();
  const socket = new WebSocket(`ws://${location.host}/ws/${ui.sessionId}`);
  ui.socket = socket;
  socket.onmessage = (message) => {
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
      scrollToBottom();
      ui.reconnectDelay = 1000;
      refreshSessionInfo();
    } else {
      handleEvent(data, false);
    }
  };
  socket.onclose = (event) => {
    if (socket !== ui.socket) return;
    if (event.code === 4404) { toast("Session introuvable"); showHome(); return; }
    setBadge("netBadge", "Serveur ✗", "bad");
    setTimeout(connect, ui.reconnectDelay);
    ui.reconnectDelay = Math.min(ui.reconnectDelay * 2, 10000);
  };
}

async function refreshSessionInfo() {
  try {
    const info = await api(`/api/sessions/${ui.sessionId}`);
    ui.clock.recording = info.recording;
    if (!info.recording && !info.finalized && !info.finalizing) {
      $("stopBtn").textContent = "▶ Reprendre";
      $("stopBtn").dataset.mode = "resume";
    } else {
      $("stopBtn").textContent = info.finalized ? "✓ Finalisée" : "■ Fin";
      $("stopBtn").dataset.mode = info.finalized ? "done" : "stop";
    }
    if (info.finalizing || (Object.keys(info.finalize_steps).length && !info.finalized)) showFinalModal();
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
      ui.segments.set(event.id, event);
      upsertSegment(event);
      setBadge("whisperBadge", "Whisper ✓", "ok");
      break;
    case "translation":
      ui.translations.set(event.segment_id, event.text_fr);
      if (ui.segments.has(event.segment_id)) upsertSegment(ui.segments.get(event.segment_id));
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
      if (event.ok && $("netBadge").className.indexOf("bad") === -1) setBadge("netBadge", "Réseau ✓", "ok");
      $("costBadge").textContent = `${ui.cost.toFixed(3).replace(".", ",")} $`;
      break;
    case "finalize_step":
      ui.steps[event.step] = event;
      if (event.output_path) ui.outputPath = event.output_path;
      if (!replay) showFinalModal();
      renderFinalSteps();
      break;
  }
  if (!replay && ui.autoScroll && ["segment", "translation", "note", "slide"].includes(event.type)) scrollToBottom();
}

function handleStatus(event, replay) {
  if (event.component === "audio") {
    ui.clock.recording = event.state === "recording";
    if (event.state === "error") { setBadge("recBadge", "Micro ✗", "bad"); if (!replay) toast(`Micro : ${event.detail}`, 6000); }
    updateRecBadge();
    if (!replay) refreshSessionInfo();
  } else if (event.component === "whisper") {
    if (event.state === "fallback") { setBadge("whisperBadge", "Whisper ⚠ léger", "warn"); if (!replay) toast(`Whisper trop lent : ${event.detail}`, 5000); }
    else if (event.state === "error") setBadge("whisperBadge", "Whisper ✗", "bad");
  } else if (event.component === "network") {
    if (event.state === "down") setBadge("netBadge", `Réseau ✗ (${event.pending} en attente)`, "bad");
    else setBadge("netBadge", "Réseau ✓", "ok");
  } else if (event.component === "llm" && event.state === "error" && !replay) {
    toast(event.detail, 5000);
  }
}

function setBadge(id, text, level) {
  const el = $(id);
  el.textContent = text;
  el.className = `badge ${level || ""}`;
}

function updateRecBadge() {
  const now = ui.clock.recording ? ui.clock.ts + (Date.now() / 1000 - ui.clock.wall) : ui.clock.ts;
  if (ui.clock.recording) setBadge("recBadge", `● REC ${fmtTime(now)}`, "rec");
  else setBadge("recBadge", `■ ${fmtTime(now)}`, "");
}

// ---------- transcription ----------

function upsertSegment(segment) {
  const translation = ui.translations.get(segment.id);
  const showOriginal = segment.lang !== "fr";
  const html = `<span class="time">${fmtTime(segment.t0)}</span>`
    + (showOriginal ? `<div class="orig">${escapeHtml(segment.text)}</div>` : "")
    + `<div class="fr ${translation ? "" : "pending"}">${escapeHtml(translation || (showOriginal ? "traduction…" : segment.text))}</div>`;
  upsertItem(segment.id, segment.t0, "seg", html);
}

function upsertItem(id, ts, className, html) {
  let entry = ui.items.get(id);
  if (!entry) {
    const el = document.createElement("div");
    el.dataset.id = id;
    el.onclick = () => {
      const hits = ui.map.highlightSources(id);
      if (!hits) toast("Pas encore dans la carte", 1500);
    };
    entry = { ts, el };
    ui.items.set(id, entry);
    insertOrdered(entry);
  }
  entry.el.className = className;
  entry.el.innerHTML = html;
}

function insertOrdered(entry) {
  const container = $("transcript");
  let after = container.lastElementChild;
  while (after && ui.items.get(after.dataset.id).ts > entry.ts) after = after.previousElementSibling;
  if (after) after.after(entry.el);
  else container.prepend(entry.el);
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
  $("retryFinalBtn").classList.toggle("hidden", !failed);
  const result = $("finalResult");
  if (ui.outputPath) {
    const vaultName = ui.outputPath.split("/").slice(0, -1).join("/");
    result.innerHTML = `Note écrite : <a href="obsidian://open?path=${encodeURIComponent(ui.outputPath)}">${escapeHtml(ui.outputPath)}</a>`;
    result.title = vaultName;
    $("stopBtn").dataset.mode = "done";
    $("stopBtn").textContent = "✓ Finalisée";
  } else {
    result.textContent = failed ? "La finalisation s'est arrêtée sur une erreur." : "En cours… (tu peux fermer cette fenêtre)";
  }
}

async function onStop() {
  const button = $("stopBtn");
  const mode = button.dataset.mode || "stop";
  if (mode === "done") { showFinalModal(); return; }
  if (mode === "resume") {
    try { await api(`/api/sessions/${ui.sessionId}/resume`, { method: "POST" }); refreshSessionInfo(); }
    catch (error) { toast(error.message, 5000); }
    return;
  }
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
  $("retryFinalBtn").onclick = () => api(`/api/sessions/${ui.sessionId}/finalize`, { method: "POST" }).catch((e) => toast(e.message));
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.onclick = () => button.closest(".overlay").classList.add("hidden");
  });
  const transcript = $("transcript");
  transcript.addEventListener("scroll", () => {
    const atBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 40;
    ui.autoScroll = atBottom;
    $("jumpBtn").classList.toggle("hidden", atBottom);
  });
  $("jumpBtn").onclick = () => { ui.autoScroll = true; scrollToBottom(); };
  setInterval(updateRecBadge, 1000);
  if (ui.sessionId) openSession(ui.sessionId);
  else showHome();
}

init();
