// Carte des idées : un groupe par sujet, posés de gauche à droite.
// Stabilité : un nœud déjà affiché ne bouge plus ; seuls les nouveaux sont placés
// (près de leurs voisins, sans chevauchement). Seul « Tidy » réorganise tout.
"use strict";

const KIND_INFO = {
  process: { icon: "⚙️", layout: { name: "dagre", rankDir: "TB", nodeSep: 40, rankSep: 55 } },
  timeline: { icon: "⏳", layout: { name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 60 } },
  comparison: { icon: "⚖️", layout: { name: "dagre", rankDir: "TB", nodeSep: 30, rankSep: 80 } },
  concept: { icon: "💡", layout: null },
};
const TOPIC_GAP = 140;
const FRESH_MS = 8000;
const NODE_MARGIN = 30;
// Zoom minimal en suivi du direct : le texte des nœuds reste à ~14 px à l'écran.
const MIN_FOLLOW_ZOOM = 0.95;

const FONT = '"SF Pro Text", -apple-system, BlinkMacSystemFont, "Inter", sans-serif';

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

class IdeaMap {
  constructor(container, { onPositions } = {}) {
    this.container = container;
    this.onPositions = onPositions || (() => {});
    this.topics = [];
    this.signatures = new Map(); // id du sujet -> signature de son contenu
    this.follow = true;
    this.programmatic = false;
    this.savedPositions = {};
    this.lastSource = "";
    this.positionTimer = null;
    this.placed = new Set(); // nœuds déjà positionnés à l'écran (ne bougent plus)
    this.addedAt = new Map(); // id du nœud -> heure d'ajout (ms)
    this.sessionId = null;
    this.hidden = new Set();
    this.loadHidden();
    this.cy = cytoscape({
      container,
            minZoom: 0.15,
      maxZoom: 2.5,
      style: this.styles(),
      elements: [],
    });
    const takeOver = () => { if (!this.programmatic) this.follow = false; };
    this.cy.on("pan zoom", takeOver);
    this.cy.on("dragfree", "node", () => this.reportPositions());
    // Contrôle humain : clic droit sur un nœud = le masquer (avec ses arêtes).
    container.addEventListener("contextmenu", (event) => event.preventDefault());
    this.cy.on("cxttap", "node.idea", (event) => this.hideNode(event.target.id()));
  }

  currentSessionId() {
    return this.sessionId || new URLSearchParams(location.search).get("s") || "default";
  }

  setSessionId(id) {
    this.sessionId = id;
    this.loadHidden();
  }

  loadHidden() {
    this.hiddenKey = this.currentSessionId();
    try { this.hidden = new Set(JSON.parse(localStorage.getItem("confmap.hidden." + this.currentSessionId()) || "[]")); }
    catch { this.hidden = new Set(); }
  }

  hiddenNodeIds() {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    return [...this.hidden];
  }

  hideNode(nodeId) {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    this.hidden.add(nodeId);
    try { localStorage.setItem("confmap.hidden." + this.currentSessionId(), JSON.stringify([...this.hidden])); } catch { /* stockage indisponible */ }
    this.applyHidden();
    try {
      fetch("/api/map/hide", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId, session_id: this.currentSessionId() }) }).catch(() => {});
    } catch { /* le serveur pourra l'ajouter plus tard */ }
  }

  applyHidden() {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    this.cy.batch(() => {
      this.hidden.forEach((id) => {
        const node = this.cy.getElementById(id);
        if (node.empty()) return;
        node.addClass("user-hidden");
        node.connectedEdges().addClass("user-hidden");
      });
    });
  }

  // Surligne (8 s) les nœuds ajoutés depuis `timestampMs` ; renvoie leur nombre et leurs sujets.
  markSince(timestampMs) {
    const nodes = this.cy.nodes(".idea").filter((n) => (this.addedAt.get(n.id()) || 0) >= timestampMs && !n.hasClass("user-hidden"));
    const topicLabels = [];
    nodes.forEach((n) => {
      const topic = this.topics.find((t) => t.id === n.data("parent"));
      const title = topic ? topic.title : "";
      if (title && !topicLabels.includes(title)) topicLabels.push(title);
    });
    nodes.addClass("fresh");
    clearTimeout(this.markTimer);
    this.markTimer = setTimeout(() => nodes.removeClass("fresh"), FRESH_MS);
    return { count: nodes.length, topics: topicLabels };
  }

  styles() {
    const kindColor = (ele) => cssVar("--" + (ele.data("kind") || "process"));
    return [
      {
        selector: "node.topic",
        style: {
          shape: "round-rectangle",
          "corner-radius": 18,
          "background-color": kindColor,
          "background-opacity": 0.06,
          "border-color": kindColor,
          "border-opacity": 0.55,
          "border-width": 1.5,
          label: "data(label)",
          "text-valign": "top",
          "text-halign": "center",
          "text-margin-y": -8,
          "font-family": FONT,
          "font-size": 16,
          "font-weight": 700,
          color: kindColor,
          padding: 26,
        },
      },
      {
        selector: "node.idea",
        style: {
          shape: "round-rectangle",
          "corner-radius": 10,
          "font-family": FONT,
          "font-weight": 500,
          "background-color": cssVar("--node-bg"),
          "border-color": cssVar("--node-border"),
          "border-width": 1.5,
          label: "data(label)",
          "text-wrap": "wrap",
          "text-max-width": 180,
          "text-valign": "center",
          "font-size": 15,
          color: cssVar("--text"),
          width: "data(w)",
          height: "data(h)",
        },
      },
      {
        selector: "edge",
        style: {
          width: 1.6,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "arrow-scale": 0.9,
          "line-color": cssVar("--node-border"),
          "target-arrow-color": cssVar("--node-border"),
          "font-family": FONT,
          label: "data(label)",
          "font-size": 13,
          color: cssVar("--muted"),
          "text-background-color": cssVar("--bg"),
          "text-background-opacity": 0.9,
          "text-background-padding": 3,
          "text-wrap": "wrap",
          "text-max-width": 200,
          "text-margin-y": -11,
        },
      },
      { selector: "edge.dup", style: { label: "" } },
      { selector: ".user-hidden", style: { display: "none" } },
      { selector: "node.idea.fresh", style: { "border-color": cssVar("--fresh-glow"), "border-width": 3, "underlay-color": cssVar("--fresh-glow"), "underlay-opacity": 0.45, "underlay-padding": 9 } },
      { selector: "node.idea.highlight", style: { "border-width": 4, "border-color": cssVar("--accent"), "underlay-color": cssVar("--accent"), "underlay-opacity": 0.45, "underlay-padding": 10 } },
    ];
  }

  nodeSize(text) {
    const length = text.length;
    const width = Math.max(90, Math.min(205, 26 + length * 8.3));
    const lines = Math.ceil((length * 8.3) / 180);
    return { w: width, h: 34 + Math.max(0, lines - 1) * 19 };
  }

  setSavedPositions(positions) {
    this.savedPositions = Object.assign({}, positions || {});
  }

  render(topics, addedIds = [], sourceText = "") {
    this.topics = topics || [];
    if (sourceText) this.lastSource = sourceText;
    const cy = this.cy;
    const changed = [];
    this.newIds = new Set();
    const newTopicIds = [];
    cy.batch(() => {
      for (const topic of this.topics) {
        const signature = JSON.stringify([topic.title, topic.nodes.map((n) => n.id), topic.edges.map((e) => e.from + ">" + e.to)]);
        if (this.signatures.get(topic.id) === signature) continue;
        this.signatures.set(topic.id, signature);
        changed.push(topic.id);
        const info = KIND_INFO[topic.kind] || KIND_INFO.process;
        if (cy.getElementById(topic.id).empty()) {
          newTopicIds.push(topic.id);
          cy.add({ group: "nodes", data: { id: topic.id, label: `${info.icon} ${topic.title}`, kind: topic.kind }, classes: "topic" });
        } else {
          cy.getElementById(topic.id).data("label", `${info.icon} ${topic.title}`);
        }
        for (const node of topic.nodes) {
          if (!cy.getElementById(node.id).empty()) continue;
          const label = `${node.emoji ? node.emoji + " " : ""}${node.label}`;
          cy.add({ group: "nodes", data: { id: node.id, parent: topic.id, label, kind: topic.kind, sources: node.sources || [], ...this.nodeSize(label) }, classes: "idea" });
          this.newIds.add(node.id);
          this.addedAt.set(node.id, Date.now());
        }
        for (const edge of topic.edges) {
          const id = `${edge.from}->${edge.to}`;
          if (!cy.getElementById(id).empty()) continue;
          if (cy.getElementById(edge.from).empty() || cy.getElementById(edge.to).empty()) continue;
          cy.add({ group: "edges", data: { id, source: edge.from, target: edge.to, label: edge.label || "" } });
        }
      }
    });
    if (changed.length) { this.dedupeEdgeLabels(); this.layoutTopics(changed); this.applyHidden(); }
    const fresh = cy.collection(addedIds.map((id) => cy.getElementById(id)).filter((ele) => ele.nonempty()));
    // Un seul signal à la fois : le dernier nœud ajouté.
    const newest = fresh.nonempty() ? fresh[fresh.length - 1] : null;
    if (newest) {
      cy.nodes(".fresh").removeClass("fresh");
      newest.addClass("fresh");
      clearTimeout(this.freshTimer);
      this.freshTimer = setTimeout(() => newest.removeClass("fresh"), FRESH_MS);
    }
    if (this.follow) this.followLatest(fresh, newTopicIds.length > 0);
    return changed.length;
  }

  topicAnchorX(index) {
    if (index === 0) return 0;
    const previous = this.cy.getElementById(this.topics[index - 1].id);
    if (previous.empty() || previous.children().empty()) return 0;
    return previous.boundingBox().x2 + TOPIC_GAP;
  }

  layoutTopics(topicIds, force = false) {
    const cy = this.cy;
    this.topics.forEach((topic, index) => {
      if (!topicIds.includes(topic.id)) return;
      const kids = cy.getElementById(topic.id).children();
      if (kids.empty()) return;
      // Positions à conserver : nœuds déjà à l'écran, ou positions enregistrées (rechargement).
      const kept = new Map();
      if (!force) {
        kids.forEach((k) => {
          if (this.placed.has(k.id())) kept.set(k.id(), { ...k.position() });
          else if (this.savedPositions[k.id()]) { const [x, y] = this.savedPositions[k.id()]; kept.set(k.id(), { x, y }); }
        });
      }
      if (kept.size === kids.length) {
        kids.forEach((k) => k.position(kept.get(k.id())));
      } else {
        const hubInfo = this.hubShape(kids);
        if (hubInfo) this.placeHubColumn(hubInfo, kept);
        else this.runTopicLayout(topic, kids);
        if (kept.size === 0) {
          // Nouveau sujet : à droite du précédent, en haut.
          const box = kids.boundingBox();
          const dx = this.topicAnchorX(index) - box.x1;
          const dy = 0 - box.y1;
          kids.positions((k) => ({ x: k.position("x") + dx, y: k.position("y") + dy }));
        } else if (!hubInfo) {
          // Sujet qui grandit : on aligne la nouvelle disposition sur l'ancienne,
          // les anciens nœuds reprennent leur place, seuls les nouveaux arrivent.
          let dx = 0, dy = 0;
          kept.forEach((old, id) => { const now = cy.getElementById(id).position(); dx += old.x - now.x; dy += old.y - now.y; });
          dx /= kept.size; dy /= kept.size;
          kids.forEach((k) => {
            k.position(kept.has(k.id()) ? kept.get(k.id()) : { x: k.position("x") + dx, y: k.position("y") + dy });
          });
        }
        const movable = kids.filter((k) => !kept.has(k.id()));
        this.resolveCollisions(movable);
      }
      kids.forEach((k) => this.placed.add(k.id()));
    });
    this.reportPositions();
  }

  // Étiquettes identiques sortant d'un même nœud : une seule reste affichée.
  dedupeEdgeLabels() {
    this.cy.batch(() => {
      this.cy.nodes().forEach((node) => {
        const seen = new Set();
        node.outgoers("edge").forEach((edge) => {
          const label = edge.data("label");
          if (!label) return;
          if (seen.has(label)) edge.addClass("dup"); else { seen.add(label); edge.removeClass("dup"); }
        });
      });
    });
  }

  // Un nœud d'où partent ≥ 3 flèches vers des feuilles : hub à gauche, cibles en colonne à droite.
  hubShape(kids) {
    const edges = kids.connectedEdges();
    const hubs = kids.filter((n) => edges.filter((e) => e.source().same(n)).length >= 3);
    if (hubs.length !== 1) return null;
    const hub = hubs[0];
    const targets = kids.difference(hub);
    const onlyHub = targets.every((t) => t.connectedEdges().every((e) => e.source().same(hub) || e.target().same(hub)));
    return onlyHub && targets.length >= 3 ? { hub, targets } : null;
  }

  // Place hub et cibles ; les nœuds déjà posés (`kept`) ne bougent pas, les nouvelles cibles
  // s'empilent sous la colonne existante.
  placeHubColumn({ hub, targets }, kept) {
    const gap = NODE_MARGIN + 6;
    const keptTargets = targets.filter((t) => kept.has(t.id()));
    const columnX = keptTargets.nonempty()
      ? kept.get(keptTargets[0].id()).x
      : hub.data("w") / 2 + 200 + Math.max(...targets.map((t) => t.data("w"))) / 2;
    let bottom = keptTargets.nonempty() ? Math.max(...keptTargets.map((t) => kept.get(t.id()).y + t.data("h") / 2)) + gap : 0;
    targets.forEach((t) => {
      if (kept.has(t.id())) { t.position(kept.get(t.id())); return; }
      t.position({ x: columnX, y: bottom + t.data("h") / 2 });
      bottom += t.data("h") + gap;
    });
    if (kept.has(hub.id())) { hub.position(kept.get(hub.id())); return; }
    const ys = targets.map((t) => t.position("y"));
    hub.position({ x: columnX - hub.data("w") / 2 - 200 - Math.max(...targets.map((t) => t.data("w"))) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 });
  }

  runTopicLayout(topic, kids) {
    if (topic.kind === "concept") this.layoutConcept(kids);
    else if (topic.kind === "comparison" && this.layoutComparison(kids)) return;
    else kids.union(kids.connectedEdges()).layout({ ...(KIND_INFO[topic.kind] || KIND_INFO.process).layout, fit: false, animate: false }).run();
  }

  // Déplace chaque nœud de `movable` qui chevauche un autre nœud vers la place libre
  // la plus proche (cercles de rayon croissant autour de sa position proposée).
  resolveCollisions(movable) {
    const others = this.cy.nodes(".idea");
    const boxAt = (n, p) => {
      const w = n.data("w") / 2 + NODE_MARGIN / 2, h = n.data("h") / 2 + NODE_MARGIN / 2;
      return { x1: p.x - w, x2: p.x + w, y1: p.y - h, y2: p.y + h };
    };
    const free = (node, p) => {
      const a = boxAt(node, p);
      return others.every((o) => {
        if (o.same(node)) return true;
        const b = boxAt(o, o.position());
        return !(a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2);
      });
    };
    movable.forEach((node) => {
      const origin = { ...node.position() };
      if (free(node, origin)) return;
      for (let radius = 40; radius <= 1200; radius += 40) {
        const steps = Math.max(8, Math.round(radius / 15));
        let found = null;
        for (let i = 0; i < steps && !found; i++) {
          // Commence vers le bas puis tourne : les ajouts restent sous leur parent si possible.
          const angle = Math.PI / 2 + (2 * Math.PI * i) / steps;
          const p = { x: origin.x + Math.cos(angle) * radius * 1.2, y: origin.y + Math.sin(angle) * radius };
          if (free(node, p)) found = p;
        }
        if (found) { node.position(found); return; }
      }
    });
  }

  // Comparaison en colonnes (même logique de groupes que _comparison_groups de l'export) :
  // chaque élément comparé est une tête de colonne, ses caractéristiques sont dessous ;
  // les caractéristiques communes (liées à plusieurs têtes) ou sans lien vont au centre, plus bas.
  layoutComparison(kids) {
    const edges = kids.connectedEdges();
    const sources = kids.filter((n) => edges.some((e) => e.source().same(n)) && !edges.some((e) => e.target().same(n)));
    if (sources.length < 2) return false;
    const sourceIds = sources.map((n) => n.id());
    const members = kids.difference(sources);
    const linkedOf = (n) => edges.filter((e) => e.target().same(n) && sourceIds.includes(e.source().id())).map((e) => sourceIds.indexOf(e.source().id()));
    const columnWidth = Math.max(...kids.map((n) => n.data("w"))) + 90;
    const columnOf = (index) => index * columnWidth;
    const rowGap = NODE_MARGIN + 6;
    const headBottom = Math.max(...sources.map((n) => n.data("h")));
    sources.forEach((n, i) => n.position({ x: columnOf(i), y: n.data("h") / 2 }));
    const cursors = sources.map(() => headBottom + 46);
    const common = [];
    members.forEach((n) => {
      const linked = linkedOf(n);
      if (linked.length === 1) {
        const i = linked[0];
        n.position({ x: columnOf(i), y: cursors[i] + n.data("h") / 2 });
        cursors[i] += n.data("h") + rowGap;
      } else common.push({ n, linked });
    });
    let commonY = Math.max(...cursors) + 20;
    common.forEach(({ n, linked }) => {
      const x = linked.length ? linked.reduce((sum, i) => sum + columnOf(i), 0) / linked.length : columnOf((sources.length - 1) / 2);
      n.position({ x, y: commonY + n.data("h") / 2 });
      commonY += n.data("h") + rowGap;
    });
    return true;
  }

  layoutConcept(kids) {
    const edges = kids.connectedEdges();
    const degree = (n) => edges.filter((e) => e.source().same(n) || e.target().same(n)).length;
    const sorted = kids.sort((a, b) => degree(b) - degree(a));
    const center = sorted[0];
    center.position({ x: 0, y: 0 });
    const first = center.neighborhood("node").intersection(kids);
    const rest = kids.difference(first).difference(center);
    const placed = new Map();
    const radius1 = Math.max(150, first.length * 34);
    first.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, first.length) - Math.PI / 2;
      n.position({ x: Math.cos(angle) * radius1, y: Math.sin(angle) * radius1 });
      placed.set(n.id(), angle);
    });
    const radius2 = radius1 + 140;
    const counts = new Map();
    rest.forEach((n, i) => {
      const parent = n.neighborhood("node").filter((m) => placed.has(m.id()))[0];
      let angle = parent ? placed.get(parent.id()) : (2 * Math.PI * i) / Math.max(1, rest.length);
      if (parent) {
        const k = counts.get(parent.id()) || 0;
        counts.set(parent.id(), k + 1);
        angle += (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 0.35;
      }
      n.position({ x: Math.cos(angle) * radius2, y: Math.sin(angle) * radius2 });
      placed.set(n.id(), angle);
    });
  }

  tidy() {
    this.savedPositions = {};
    this.placed.clear();
    this.layoutTopics(this.topics.map((t) => t.id), true);
    this.fit(true);
  }

  // Marges de cadrage (px écran) : la barre d'outils de la carte ne doit rien masquer.
  viewInsets() {
    const tools = this.container.parentElement && this.container.parentElement.querySelector(".map-tools");
    let bottom = 24;
    if (tools) {
      const toolsBox = tools.getBoundingClientRect();
      const containerBox = this.container.getBoundingClientRect();
      const overlap = containerBox.bottom - toolsBox.top;
      if (overlap > 0) bottom = overlap + 16;
    }
    return { top: 24, left: 24, right: 24, bottom };
  }

  followLatest(fresh, hasNewTopic) {
    // Nouveau sujet : on le cadre (zoom lisible). Sinon, pas de zoom ni de re-cadrage :
    // simple panoramique minimal si les nouveaux nœuds sortent de la zone visible.
    const cy = this.cy;
    const inset = this.viewInsets();
    const areaW = cy.width() - inset.left - inset.right;
    const areaH = cy.height() - inset.top - inset.bottom;
    this.programmatic = true;
    try {
      if (hasNewTopic) {
        const last = this.topics.length ? cy.getElementById(this.topics[this.topics.length - 1].id) : null;
        if (!last || last.empty()) return;
        const box = last.union(last.descendants()).boundingBox();
        const fitZoom = Math.min(areaW / box.w, areaH / box.h);
        const zoom = fitZoom >= 0.6 ? Math.min(1.3, fitZoom) : MIN_FOLLOW_ZOOM;
        // Si le sujet est trop grand pour la zone, on montre son début (coin haut-gauche).
        const centerX = fitZoom >= 0.6 ? (box.x1 + box.x2) / 2 : box.x1 + areaW / zoom / 2;
        const centerY = fitZoom >= 0.6 ? (box.y1 + box.y2) / 2 : box.y1 + areaH / zoom / 2;
        cy.zoom(zoom);
        cy.pan({ x: inset.left + areaW / 2 - centerX * zoom, y: inset.top + areaH / 2 - centerY * zoom });
      } else if (fresh && fresh.nonempty()) {
        const zoom = cy.zoom();
        const pan = cy.pan();
        const box = fresh.boundingBox();
        const screen = { x1: box.x1 * zoom + pan.x, x2: box.x2 * zoom + pan.x, y1: box.y1 * zoom + pan.y, y2: box.y2 * zoom + pan.y };
        let dx = 0, dy = 0;
        if (screen.x2 > cy.width() - inset.right) dx = cy.width() - inset.right - screen.x2;
        if (screen.x1 + dx < inset.left) dx = inset.left - screen.x1;
        if (screen.y2 > cy.height() - inset.bottom) dy = cy.height() - inset.bottom - screen.y2;
        if (screen.y1 + dy < inset.top) dy = inset.top - screen.y1;
        if (dx || dy) cy.pan({ x: pan.x + dx, y: pan.y + dy });
      }
    } finally {
      this.programmatic = false;
    }
  }

  fit(animate) {
    this.follow = true;
    if (this.cy.elements().empty()) return;
    this.programmatic = true;
    if (animate) {
      this.cy.animate({ fit: { eles: this.cy.elements(), padding: Math.max(40, this.viewInsets().bottom) } }, { duration: 300, complete: () => { this.programmatic = false; } });
    } else {
      this.cy.fit(this.cy.elements(), 40);
      const inset = this.viewInsets();
      if (inset.bottom > 40) {
        const zoom = Math.min(this.cy.zoom(), (this.cy.height() - inset.top - inset.bottom) / this.cy.elements().boundingBox().h);
        this.cy.zoom(zoom);
        const box = this.cy.elements().boundingBox();
        this.cy.pan({ x: this.cy.width() / 2 - ((box.x1 + box.x2) / 2) * zoom, y: inset.top + (this.cy.height() - inset.top - inset.bottom) / 2 - ((box.y1 + box.y2) / 2) * zoom });
      }
      if (this.cy.zoom() > 1.2) this.cy.zoom({ level: 1.2, renderedPosition: { x: this.container.clientWidth / 2, y: this.container.clientHeight / 2 } });
      this.programmatic = false;
    }
  }

  reportPositions() {
    clearTimeout(this.positionTimer);
    this.positionTimer = setTimeout(() => {
      const positions = {};
      this.cy.nodes(".idea").forEach((n) => { positions[n.id()] = [Math.round(n.position("x")), Math.round(n.position("y"))]; });
      Object.assign(this.savedPositions, positions);
      this.onPositions(positions);
    }, 800);
  }

  highlightSources(eventId) {
    this.cy.nodes(".idea").removeClass("highlight");
    const hits = this.cy.nodes(".idea").filter((n) => (n.data("sources") || []).includes(eventId));
    hits.addClass("highlight");
    return hits.length;
  }
}

window.IdeaMap = IdeaMap;
window.KIND_INFO = KIND_INFO;
