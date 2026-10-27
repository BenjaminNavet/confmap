// Carte des idées : un groupe par sujet, posés de gauche à droite.
// Stabilité : un nœud déjà affiché ne bouge plus ; seuls les nouveaux sont placés
// (près de leurs voisins, sans chevauchement). Seul « Tidy » réorganise tout.
"use strict";

const KIND_INFO = {
  process: { icon: "⚙️", layout: { name: "dagre", rankDir: "LR", ranker: "network-simplex", nodeSep: 36, rankSep: 70, edgeSep: 20 } },
  timeline: { icon: "⏳", layout: null },
  comparison: { icon: "⚖️", layout: { name: "dagre", rankDir: "TB", ranker: "network-simplex", nodeSep: 36, rankSep: 80, edgeSep: 20 } },
  concept: { icon: "💡", layout: null },
};
const TOPIC_GAP = 140;
const FRESH_MS = 8000;
const NODE_MARGIN = 30;
// Cadrage : zoom borné, un seul mouvement de 300 ms.
const FRAME_MIN_ZOOM = 0.6;
const FRAME_MAX_ZOOM = 1.3;
const FRAME_MS = 300;
const HIDE_HINT = "Clic droit sur une boîte pour la masquer";
const TIMELINE_PITCH = 130;

// Arête déviée : deux points de contrôle décalés de d de part et d'autre de la droite (poids 0,08 / 0,92).
// Cytoscape trace alors deux quadratiques raccordées ; la courbe passe à d de la droite en son milieu.
const ROUTE_WEIGHTS = [0.08, 0.92];
function edgePathPoints(a, b, d, steps) {
  const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
  if (!d) return Array.from({ length: steps + 1 }, (_, i) => ({ x: a.x + (dx * i) / steps, y: a.y + (dy * i) / steps }));
  const nx = -dy / length, ny = dx / length;
  const c1 = { x: a.x + dx * ROUTE_WEIGHTS[0] + nx * d, y: a.y + dy * ROUTE_WEIGHTS[0] + ny * d };
  const c2 = { x: a.x + dx * ROUTE_WEIGHTS[1] + nx * d, y: a.y + dy * ROUTE_WEIGHTS[1] + ny * d };
  const m = { x: (c1.x + c2.x) / 2, y: (c1.y + c2.y) / 2 };
  const quad = (p0, c, p1, t) => ({ x: (1 - t) * (1 - t) * p0.x + 2 * (1 - t) * t * c.x + t * t * p1.x, y: (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * c.y + t * t * p1.y });
  const half = Math.max(1, Math.floor(steps / 2));
  const points = [];
  for (let i = 0; i <= half; i++) points.push(quad(a, c1, m, i / half));
  for (let i = 1; i <= half; i++) points.push(quad(m, c2, b, i / half));
  return points;
}

function prefersReducedMotion() {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
}

const FONT = '"SF Pro Text", -apple-system, BlinkMacSystemFont, "Inter", sans-serif';

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

class IdeaMap {
  constructor(container, { onPositions, onHide } = {}) {
    this.container = container;
    this.onPositions = onPositions || (() => {});
    this.onHide = onHide || null; // (id, label) appelé après un masquage
    this.frameToken = 0;
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
      minZoom: 0.05,
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
    if (!container.title) container.title = HIDE_HINT;
    // Le conteneur peut changer de taille (volet, fenêtre) : cytoscape doit le savoir pour cadrer juste.
    if (typeof ResizeObserver === "function") new ResizeObserver(() => this.cy.resize()).observe(container);
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

  saveHidden() {
    try { localStorage.setItem("confmap.hidden." + this.currentSessionId(), JSON.stringify([...this.hidden])); } catch { /* stockage indisponible */ }
  }

  postHidden(path, nodeId) {
    try {
      fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node_id: nodeId, session_id: this.currentSessionId() }) }).catch(() => {});
    } catch { /* le serveur pourra l'ajouter plus tard */ }
  }

  hideNode(nodeId) {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    this.hidden.add(nodeId);
    this.saveHidden();
    this.applyHidden();
    this.postHidden("/api/map/hide", nodeId);
    const node = this.cy.getElementById(nodeId);
    if (this.onHide) this.onHide(nodeId, node.nonempty() ? String(node.data("label") || "") : "");
  }

  // Annule un masquage : le nœud et ses arêtes (dont l'autre bout est visible) reviennent.
  unhideNode(nodeId) {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    if (!this.hidden.delete(nodeId)) return false;
    this.saveHidden();
    this.refreshHidden();
    this.postHidden("/api/map/unhide", nodeId);
    return true;
  }

  unhideAll() {
    if (this.hiddenKey !== this.currentSessionId()) this.loadHidden();
    const ids = [...this.hidden];
    this.hidden.clear();
    this.saveHidden();
    this.refreshHidden();
    ids.forEach((id) => this.postHidden("/api/map/unhide", id));
    return ids.length;
  }

  refreshHidden() {
    this.cy.batch(() => { this.cy.elements(".user-hidden").removeClass("user-hidden"); });
    this.applyHidden();
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

  // Surligne (8 s) les nœuds ajoutés depuis `timestampMs` ; renvoie leur nombre, leurs sujets,
  // jusqu'à 3 libellés et tous leurs identifiants.
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
    const labels = nodes.slice(0, 3).map((n) => String(n.data("label") || ""));
    return { count: nodes.length, topics: topicLabels, labels, ids: nodes.map((n) => n.id()) };
  }

  // Cadre les nœuds donnés (même mouvement animé que le suivi du direct).
  focusNodes(ids) {
    const eles = this.cy.collection((ids || []).map((id) => this.cy.getElementById(id)).filter((n) => n.nonempty() && !n.hasClass("user-hidden")));
    if (eles.empty()) return false;
    this.frame(eles, { force: true });
    return true;
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
          // Étiquette lisible : fond opaque, au-dessus des nœuds.
          "text-background-color": cssVar("--bg"),
          "text-background-opacity": 1,
          "text-background-padding": 4,
          "text-background-shape": "round-rectangle",
          "text-wrap": "wrap",
          "text-max-width": 200,
          "z-index-compare": "manual",
          "z-index": 10,
        },
      },
      { selector: "node.idea", style: { "z-index-compare": "manual", "z-index": 5 } },
      { selector: "node.topic", style: { "z-index-compare": "manual", "z-index": 0 } },
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
    if (this.follow) this.followLatest(fresh);
    return changed.length;
  }

  // Où poser un nouveau sujet : à droite du précédent si le panneau est large, dessous s'il est haut
  // (le panneau de la carte est souvent plus haut que large : la carte reste ainsi lisible en vue d'ensemble).
  topicAnchor(index) {
    if (index === 0) return { x: 0, y: 0 };
    const previous = this.cy.getElementById(this.topics[index - 1].id);
    if (previous.empty() || previous.children().empty()) return { x: 0, y: 0 };
    const box = previous.boundingBox({ includeEdges: false });
    const stacked = this.cy.width() < this.cy.height() * 1.3;
    return stacked ? { x: box.x1, y: box.y2 + TOPIC_GAP * 0.6 } : { x: box.x2 + TOPIC_GAP, y: 0 };
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
        // Les nœuds déjà posés reprennent leur place avant tout calcul (les nouveaux se calent dessus).
        kids.forEach((k) => { if (kept.has(k.id())) k.position(kept.get(k.id())); });
        const structured = this.placeStructure(topic, kids, kept);
        if (!structured) {
          const hubInfo = topic.kind === "process" ? this.hubShape(kids) : null;
          if (hubInfo) this.placeHubColumn(hubInfo, kept);
          else this.runDagre(topic, kids, kept);
        }
        if (kept.size === 0) {
          // Nouveau sujet : à droite du précédent, en haut.
          const box = kids.boundingBox();
          const anchor = this.topicAnchor(index);
          const dx = anchor.x - box.x1;
          const dy = anchor.y - box.y1;
          kids.positions((k) => ({ x: k.position("x") + dx, y: k.position("y") + dy }));
        }
        this.resolveCollisions(kids.filter((k) => !kept.has(k.id())));
      }
      kids.forEach((k) => this.placed.add(k.id()));
    });
    this.routeEdges();
    this.reportPositions();
  }

  // Disposition qui encode le type du sujet par la position. Les nœuds de `kept` ne bougent pas :
  // seuls les nouveaux sont posés, dans la structure existante (colonne, cercle, axe).
  placeStructure(topic, kids, kept) {
    if (topic.kind === "comparison") return this.layoutComparison(kids, kept);
    if (topic.kind === "concept") { this.layoutConcept(kids, kept); return true; }
    if (topic.kind === "timeline") { this.layoutTimeline(kids, kept); return true; }
    return false;
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

  // Processus : de gauche à droite. Premier calcul par dagre (rangs network-simplex, moins de croisements) ;
  // ensuite chaque nouveau nœud se pose à droite de ses prédécesseurs sans toucher aux anciens.
  runDagre(topic, kids, kept) {
    const options = (KIND_INFO[topic.kind] || KIND_INFO.process).layout || KIND_INFO.process.layout;
    if (kept.size === 0 || topic.kind !== "process") {
      const before = new Map();
      kids.forEach((k) => before.set(k.id(), { ...k.position() }));
      kids.union(kids.connectedEdges()).layout({ ...options, fit: false, animate: false }).run();
      if (kept.size) {
        // Nouveau calcul aligné sur l'ancien : les anciens reprennent leur place.
        let dx = 0, dy = 0;
        kept.forEach((old, id) => { const now = this.cy.getElementById(id).position(); dx += old.x - now.x; dy += old.y - now.y; });
        dx /= kept.size; dy /= kept.size;
        kids.forEach((k) => k.position(kept.has(k.id()) ? kept.get(k.id()) : { x: k.position("x") + dx, y: k.position("y") + dy }));
      }
      return;
    }
    const placedNow = new Set(kept.keys());
    const gap = 60;
    kids.filter((k) => !kept.has(k.id())).forEach((node) => {
      const preds = node.incomers("node").filter((m) => placedNow.has(m.id()));
      const succs = node.outgoers("node").filter((m) => placedNow.has(m.id()));
      let x, y;
      if (preds.nonempty()) {
        x = Math.max(...preds.map((m) => m.position("x") + m.data("w") / 2)) + gap + node.data("w") / 2;
        y = preds.map((m) => m.position("y")).reduce((a, b) => a + b, 0) / preds.length;
      } else if (succs.nonempty()) {
        x = Math.min(...succs.map((m) => m.position("x") - m.data("w") / 2)) - gap - node.data("w") / 2;
        y = succs.map((m) => m.position("y")).reduce((a, b) => a + b, 0) / succs.length;
      } else {
        const placedKids = kids.filter((k) => placedNow.has(k.id()));
        const box = placedKids.boundingBox();
        x = box.x2 + gap + node.data("w") / 2;
        y = (box.y1 + box.y2) / 2;
      }
      node.position({ x, y });
      placedNow.add(node.id());
      this.resolveCollisions(node.collection(), true);
    });
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

  // Têtes de colonnes d'une comparaison : les sources (≥ 2) ; sinon, si une seule racine, ses enfants directs.
  comparisonHeads(kids) {
    const edges = kids.connectedEdges();
    const sources = kids.filter((n) => edges.some((e) => e.source().same(n)) && !edges.some((e) => e.target().same(n)));
    if (sources.length >= 2) return { heads: sources, root: null };
    if (sources.length === 1) {
      const root = sources[0];
      const heads = root.outgoers("node").filter((n) => kids.contains(n));
      if (heads.length >= 2) return { heads, root };
    }
    return null;
  }

  // Comparaison en colonnes parallèles : une tête par élément comparé, ses attributs dessous,
  // les attributs communs (liés à plusieurs têtes) au centre. Les nouveaux nœuds s'ajoutent
  // à la colonne de leur tête sans déplacer les anciens.
  layoutComparison(kids, kept) {
    const found = this.comparisonHeads(kids);
    if (!found) return false;
    const { heads, root } = found;
    const headIds = heads.map((n) => n.id());
    const edges = kids.connectedEdges();
    const members = kids.difference(heads).difference(root || kids.nodes().filter(() => false));
    const columnWidth = Math.max(...kids.map((n) => n.data("w"))) + 90;
    const rowGap = NODE_MARGIN + 6;
    // Colonnes : celles des têtes déjà posées, les autres à droite (au centre, deux colonnes écartées pour les communs).
    const spacing = headIds.length === 2 ? columnWidth * 1.8 : columnWidth;
    const columnX = new Map();
    const keptHeads = heads.filter((n) => kept.has(n.id()));
    keptHeads.forEach((n) => columnX.set(n.id(), kept.get(n.id()).x));
    let nextX = columnX.size ? Math.max(...columnX.values()) + spacing : 0;
    const headY = keptHeads.nonempty() ? kept.get(keptHeads[0].id()).y : null;
    heads.forEach((n) => {
      if (columnX.has(n.id())) return;
      columnX.set(n.id(), nextX);
      nextX += spacing;
    });
    const headTop = headY === null ? 0 : headY - keptHeads[0].data("h") / 2;
    const headBottom = headTop + Math.max(...heads.map((n) => n.data("h")));
    heads.forEach((n) => { if (!kept.has(n.id())) n.position({ x: columnX.get(n.id()), y: headTop + n.data("h") / 2 }); });
    // Rattachement de chaque attribut : à une colonne (un seul lien), sinon au centre.
    const owner = new Map(); // id -> id de tête, ou null pour « commun »
    const linkedHeads = (n) => [...new Set(edges.filter((e) => e.source().same(n) || e.target().same(n))
      .map((e) => (e.source().same(n) ? e.target() : e.source()).id()).filter((id) => headIds.includes(id)))];
    members.forEach((n) => { const linked = linkedHeads(n); if (linked.length === 1) owner.set(n.id(), linked[0]); else if (linked.length > 1) owner.set(n.id(), null); });
    for (let pass = 0; pass < 4; pass++) {
      members.forEach((n) => {
        if (owner.has(n.id())) return;
        const around = new Set(n.neighborhood("node").filter((m) => owner.has(m.id())).map((m) => owner.get(m.id())));
        if (around.size === 1) owner.set(n.id(), [...around][0]);
        else if (around.size > 1) owner.set(n.id(), null);
      });
    }
    const commonX = [...columnX.values()].reduce((a, b) => a + b, 0) / columnX.size;
    const cursors = new Map(); // clé de colonne -> bas de la colonne
    const keyOf = (n) => (owner.get(n.id()) === undefined || owner.get(n.id()) === null ? "common" : owner.get(n.id()));
    const baseY = headBottom + 46;
    const xOf = (key) => (key === "common" ? commonX : columnX.get(key));
    members.filter((n) => kept.has(n.id())).forEach((n) => {
      const key = keyOf(n);
      cursors.set(key, Math.max(cursors.get(key) ?? baseY, kept.get(n.id()).y + n.data("h") / 2 + rowGap));
    });
    const commonOnTwo = headIds.length === 2;
    members.filter((n) => !kept.has(n.id())).forEach((n) => {
      const key = keyOf(n);
      let x = xOf(key);
      let top = cursors.get(key) ?? baseY;
      if (key === "common" && !commonOnTwo) {
        // Plus de deux colonnes : les communs vont dans une bande sous toutes les colonnes.
        const lowest = Math.max(baseY, ...[...cursors.entries()].filter(([k]) => k !== "common").map(([, v]) => v));
        top = Math.max(top, lowest + 20);
        x = commonX;
      }
      n.position({ x, y: top + n.data("h") / 2 });
      cursors.set(key, top + n.data("h") + rowGap);
    });
    if (root && !kept.has(root.id())) {
      root.position({ x: commonX, y: headTop - root.data("h") / 2 - 54 });
    }
    return true;
  }

  // Axe horizontal ordonné : les événements se suivent de gauche à droite dans l'ordre d'arrivée,
  // en alternance de part et d'autre de l'axe pour que les étiquettes ne se recouvrent pas.
  layoutTimeline(kids, kept) {
    const order = kids.toArray();
    let rightmost = kept.size ? Math.max(...[...kept.values()].map((p) => p.x)) : -TIMELINE_PITCH;
    order.forEach((node, index) => {
      if (kept.has(node.id())) return;
      rightmost += TIMELINE_PITCH;
      node.position({ x: rightmost, y: (index % 2 ? 1 : -1) * 56 });
    });
  }

  // Concept : l'idée centrale au milieu, ses satellites en cercle autour (rayon assez grand pour
  // qu'ils ne se touchent pas). Un nouveau satellite prend le plus grand vide de l'anneau ;
  // un détail de satellite se place vers l'extérieur, dans la direction de son satellite.
  layoutConcept(kids, kept) {
    const edges = kids.connectedEdges();
    const degree = (n) => edges.filter((e) => e.source().same(n) || e.target().same(n)).length;
    const keptNodes = kids.filter((n) => kept.has(n.id()));
    const pool = keptNodes.nonempty() ? keptNodes : kids;
    const center = pool.toArray().sort((a, b) => degree(b) - degree(a) || a.position("x") ** 2 + a.position("y") ** 2 - (b.position("x") ** 2 + b.position("y") ** 2))[0];
    if (!kept.has(center.id())) center.position({ x: 0, y: 0 });
    const origin = { ...center.position() };
    const polar = (n) => { const p = n.position(); return { angle: Math.atan2(p.y - origin.y, p.x - origin.x), radius: Math.hypot(p.x - origin.x, p.y - origin.y) }; };
    const maxWidth = Math.max(...kids.map((n) => n.data("w")));
    const maxHeight = Math.max(...kids.map((n) => n.data("h")));
    const ring = kids.filter((n) => !n.same(center) && n.edgesWith(center).nonempty());
    const ringAngles = ring.filter((n) => kept.has(n.id())).map((n) => polar(n).angle);
    const arc = maxWidth + 40; // place minimale qu'un satellite occupe sur le cercle
    const newcomers = ring.filter((n) => !kept.has(n.id()));
    const keptRadius = ring.filter((n) => kept.has(n.id())).map((n) => polar(n).radius);
    const radiusFor = (count) => Math.max(130 + center.data("w") / 4, (count * arc) / (2 * Math.PI) / 0.8);
    const ringRadius = keptRadius.length ? Math.max(...keptRadius) : radiusFor(ring.length);
    if (ringAngles.length === 0) {
      newcomers.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / newcomers.length + (newcomers.length % 2 ? -Math.PI / 2 : 0);
        n.position({ x: origin.x + Math.cos(angle) * ringRadius * 1.25, y: origin.y + Math.sin(angle) * ringRadius });
      });
    } else {
      newcomers.forEach((n) => {
        // Plus grand vide entre deux satellites déjà posés.
        const sorted = [...ringAngles].sort((a, b) => a - b);
        let bestGap = -1, bestAngle = 0;
        sorted.forEach((angle, i) => {
          const next = i === sorted.length - 1 ? sorted[0] + 2 * Math.PI : sorted[i + 1];
          if (next - angle > bestGap) { bestGap = next - angle; bestAngle = angle + (next - angle) / 2; }
        });
        // Vide trop étroit pour la boîte : on passe à un anneau plus large.
        const needed = (arc * 0.9) / ringRadius;
        const outer = bestGap < needed ? ringRadius + maxHeight + 70 : ringRadius;
        n.position({ x: origin.x + Math.cos(bestAngle) * outer * 1.25, y: origin.y + Math.sin(bestAngle) * outer });
        ringAngles.push(bestAngle);
      });
    }
    // Détails : vers l'extérieur de leur satellite, étalés en éventail.
    const placedIds = new Set([center.id(), ...ring.map((n) => n.id())]);
    const rest = kids.filter((n) => !placedIds.has(n.id()));
    const fanCount = new Map();
    for (let pass = 0; pass < 3; pass++) {
      rest.forEach((n) => {
        if (placedIds.has(n.id()) || kept.has(n.id())) { placedIds.add(n.id()); return; }
        const parent = n.neighborhood("node").filter((m) => placedIds.has(m.id()))[0];
        if (!parent) return;
        const base = polar(parent);
        const k = fanCount.get(parent.id()) || 0;
        fanCount.set(parent.id(), k + 1);
        const angle = base.angle + (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 0.4;
        const radius = base.radius + maxHeight + 90 + Math.floor(k / 3) * 60;
        n.position({ x: origin.x + Math.cos(angle) * radius * 1.25, y: origin.y + Math.sin(angle) * radius });
        placedIds.add(n.id());
      });
    }
    rest.forEach((n) => {
      if (placedIds.has(n.id())) return;
      n.position({ x: origin.x + (ringRadius + 2 * maxHeight + 160) * 1.25, y: origin.y });
    });
  }

  // Évite que les arêtes traversent des boîtes : une arête qui passerait derrière un nœud
  // devient une courbe dont le point de contrôle est écarté du côté libre (le plus petit écart).
  routeEdges() {
    const ideas = this.cy.nodes(".idea").filter((n) => !n.hasClass("user-hidden"));
    const boxes = ideas.map((n) => {
      const p = n.position(), w = n.data("w") / 2 + 8, h = n.data("h") / 2 + 8;
      return { id: n.id(), x1: p.x - w, x2: p.x + w, y1: p.y - h, y2: p.y + h };
    });
    const offsets = [0];
    for (const d of [60, 95, 130, 170, 220, 290]) offsets.push(d, -d);
    this.cy.batch(() => {
      this.cy.edges().forEach((edge) => {
        const a = edge.source().position(), b = edge.target().position();
        const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
        const normal = { x: -dy / length, y: dx / length };
        const blockers = boxes.filter((box) => box.id !== edge.source().id() && box.id !== edge.target().id());
        const clear = (d) => edgePathPoints(a, b, d, 30).slice(1, -1).every((p) => !blockers.some((box) => p.x > box.x1 && p.x < box.x2 && p.y > box.y1 && p.y < box.y2));
        const previous = edge.data("cpd") || 0;
        let chosen = 0;
        if (!clear(0)) {
          // Garde le côté déjà choisi quand c'est possible (arête stable d'un rendu à l'autre).
          const ordered = previous ? [previous, ...offsets.filter((d) => d !== previous)] : offsets;
          const found = ordered.find((d) => d !== 0 && clear(d));
          chosen = found === undefined ? 0 : found;
        }
        if (chosen === previous && edge.hasClass("routed") === (chosen !== 0)) return;
        edge.data("cpd", chosen);
        if (chosen) {
          edge.addClass("routed");
          edge.style({ "curve-style": "unbundled-bezier", "control-point-distances": [chosen, chosen], "control-point-weights": ROUTE_WEIGHTS });
        } else {
          edge.removeClass("routed");
          edge.removeStyle("curve-style control-point-distances control-point-weights");
        }
        void normal;
      });
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

  // Un seul mouvement (zoom + panoramique, 300 ms ; instantané si l'utilisateur préfère moins d'animations).
  moveCamera(zoom, pan) {
    const cy = this.cy;
    cy.stop();
    const token = ++this.frameToken;
    this.programmatic = true;
    const done = () => { if (token === this.frameToken) this.programmatic = false; };
    if (prefersReducedMotion()) {
      cy.zoom(zoom);
      cy.pan(pan);
      done();
      return;
    }
    cy.animate({ zoom, pan }, { duration: FRAME_MS, easing: "ease-out", complete: done });
    setTimeout(done, FRAME_MS + 80);
  }

  // Cadre `eles` en entier, zoom borné [0,6 ; 1,3]. Sans `force`, ne bouge pas si tout est déjà visible.
  // Trop grand pour le zoom plancher : on centre sur `focus` (les nœuds nouveaux), sinon sur le coin haut-gauche.
  frame(eles, { force = false, focus = null } = {}) {
    const cy = this.cy;
    cy.resize();
    const visible = eles.filter(":visible");
    if (visible.empty()) return;
    const box = visible.boundingBox({ includeEdges: true, includeLabels: true, includeOverlays: false });
    const inset = this.viewInsets();
    const areaW = cy.width() - inset.left - inset.right;
    const areaH = cy.height() - inset.top - inset.bottom;
    if (areaW <= 0 || areaH <= 0) return;
    const zoom0 = cy.zoom(), pan0 = cy.pan();
    if (!force) {
      const tolerance = 2;
      const inside = box.x1 * zoom0 + pan0.x >= inset.left - tolerance && box.x2 * zoom0 + pan0.x <= cy.width() - inset.right + tolerance
        && box.y1 * zoom0 + pan0.y >= inset.top - tolerance && box.y2 * zoom0 + pan0.y <= cy.height() - inset.bottom + tolerance;
      if (inside) return;
    }
    const fitZoom = Math.min(areaW / box.w, areaH / box.h);
    const zoom = Math.max(FRAME_MIN_ZOOM, Math.min(FRAME_MAX_ZOOM, fitZoom));
    let center = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    if (fitZoom < FRAME_MIN_ZOOM) {
      const target = focus && focus.nonempty() ? focus.boundingBox() : null;
      center = target
        ? { x: Math.max(box.x1 + areaW / zoom / 2, Math.min(box.x2 - areaW / zoom / 2, (target.x1 + target.x2) / 2)), y: Math.max(box.y1 + areaH / zoom / 2, Math.min(box.y2 - areaH / zoom / 2, (target.y1 + target.y2) / 2)) }
        : { x: box.x1 + areaW / zoom / 2, y: box.y1 + areaH / zoom / 2 };
    }
    this.moveCamera(zoom, { x: inset.left + areaW / 2 - center.x * zoom, y: inset.top + areaH / 2 - center.y * zoom });
  }

  // Suivi du direct : si le sujet courant (celui du dernier nœud ajouté) n'est pas entièrement visible,
  // un seul mouvement le cadre en entier ; sinon la vue ne bouge pas.
  followLatest(fresh) {
    const cy = this.cy;
    const newest = fresh && fresh.nonempty() ? fresh[fresh.length - 1] : null;
    let topicNode = newest ? cy.getElementById(newest.data("parent")) : null;
    if (!topicNode || topicNode.empty()) topicNode = this.topics.length ? cy.getElementById(this.topics[this.topics.length - 1].id) : null;
    if (!topicNode || topicNode.empty()) return;
    this.frame(topicNode.union(topicNode.descendants()), { focus: fresh });
  }

  // « Tout voir » : la carte remplit le panneau (marges de 24 px), sans plafond de zoom bas.
  fit(animate) {
    this.follow = true;
    const cy = this.cy;
    cy.resize();
    const eles = cy.elements().filter(":visible");
    if (eles.empty()) return;
    const box = eles.boundingBox({ includeEdges: true, includeLabels: true, includeOverlays: false });
    const inset = this.viewInsets();
    const areaW = cy.width() - inset.left - inset.right;
    const areaH = cy.height() - inset.top - inset.bottom;
    if (areaW <= 0 || areaH <= 0 || box.w <= 0 || box.h <= 0) return;
    const zoom = Math.min(areaW / box.w, areaH / box.h, 1.5);
    const pan = { x: inset.left + areaW / 2 - ((box.x1 + box.x2) / 2) * zoom, y: inset.top + areaH / 2 - ((box.y1 + box.y2) / 2) * zoom };
    if (animate) this.moveCamera(zoom, pan);
    else {
      this.frameToken++;
      this.programmatic = true;
      cy.zoom(zoom);
      cy.pan(pan);
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
