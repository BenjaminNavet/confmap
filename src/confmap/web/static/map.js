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
  }

  styles() {
    const kindColor = (ele) => cssVar("--" + (ele.data("kind") || "process"));
    return [
      {
        selector: "node.topic",
        style: {
          shape: "round-rectangle",
          "background-color": cssVar("--group-bg"),
          "border-color": kindColor,
          "border-width": 2,
          label: "data(label)",
          "text-valign": "top",
          "text-halign": "center",
          "text-margin-y": -6,
          "font-size": 15,
          "font-weight": 700,
          color: kindColor,
          padding: 24,
        },
      },
      {
        selector: "node.idea",
        style: {
          shape: "round-rectangle",
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
          width: 1.4,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": cssVar("--faint"),
          "target-arrow-color": cssVar("--faint"),
          label: "data(label)",
          "font-size": 13,
          color: cssVar("--muted"),
          "text-background-color": cssVar("--bg"),
          "text-background-opacity": 0.9,
          "text-background-padding": 3,
          "text-wrap": "wrap",
          "text-max-width": 140,
        },
      },
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
    cy.batch(() => {
      for (const topic of this.topics) {
        const signature = JSON.stringify([topic.title, topic.nodes.map((n) => n.id), topic.edges.map((e) => e.from + ">" + e.to)]);
        if (this.signatures.get(topic.id) === signature) continue;
        this.signatures.set(topic.id, signature);
        changed.push(topic.id);
        const info = KIND_INFO[topic.kind] || KIND_INFO.process;
        if (cy.getElementById(topic.id).empty()) {
          cy.add({ group: "nodes", data: { id: topic.id, label: `${info.icon} ${topic.title}`, kind: topic.kind }, classes: "topic" });
        } else {
          cy.getElementById(topic.id).data("label", `${info.icon} ${topic.title}`);
        }
        for (const node of topic.nodes) {
          if (!cy.getElementById(node.id).empty()) continue;
          const label = `${node.emoji ? node.emoji + " " : ""}${node.label}`;
          cy.add({ group: "nodes", data: { id: node.id, parent: topic.id, label, kind: topic.kind, sources: node.sources || [], ...this.nodeSize(label) }, classes: "idea" });
          this.newIds.add(node.id);
        }
        for (const edge of topic.edges) {
          const id = `${edge.from}->${edge.to}`;
          if (!cy.getElementById(id).empty()) continue;
          if (cy.getElementById(edge.from).empty() || cy.getElementById(edge.to).empty()) continue;
          cy.add({ group: "edges", data: { id, source: edge.from, target: edge.to, label: edge.label || "" } });
        }
      }
    });
    if (changed.length) this.layoutTopics(changed);
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
        this.runTopicLayout(topic, kids);
        if (kept.size === 0) {
          // Nouveau sujet : à droite du précédent, en haut.
          const box = kids.boundingBox();
          const dx = this.topicAnchorX(index) - box.x1;
          const dy = 0 - box.y1;
          kids.positions((k) => ({ x: k.position("x") + dx, y: k.position("y") + dy }));
        } else {
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
    // Un sujet qui a grandi ne doit pas recouvrir le suivant : on décale les suivants.
    this.topics.forEach((topic, index) => {
      if (index === 0) return;
      const kids = cy.getElementById(topic.id).children();
      if (kids.empty()) return;
      const minX = this.topicAnchorX(index);
      const box = kids.boundingBox();
      if (box.x1 < minX) kids.positions((k) => ({ x: k.position("x") + (minX - box.x1), y: k.position("y") }));
    });
    this.reportPositions();
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

  // Comparaison en colonnes : un élément comparé par colonne, ses caractéristiques
  // dessous ; les caractéristiques partagées sont centrées entre leurs éléments, plus bas.
  layoutComparison(kids) {
    const edges = kids.connectedEdges();
    const sources = kids.filter((n) => edges.some((e) => e.source().same(n)) && !edges.some((e) => e.target().same(n)));
    if (sources.length < 2) return false;
    const columnWidth = Math.max(...kids.map((n) => n.data("w"))) + 50;
    const centers = new Map();
    sources.forEach((n, i) => { centers.set(n.id(), i * columnWidth); n.position({ x: i * columnWidth, y: 0 }); });
    const groups = new Map();
    kids.difference(sources).forEach((n) => {
      const linked = edges.filter((e) => e.target().same(n) && centers.has(e.source().id())).map((e) => e.source().id());
      const key = linked.sort((a, b) => centers.get(a) - centers.get(b)).join("|");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(n);
    });
    const top = Math.max(...sources.map((n) => n.data("h"))) + 70;
    let bottom = top;
    for (const [key, members] of groups) {
      const linked = key ? key.split("|") : [];
      if (linked.length !== 1) continue;
      let y = top;
      for (const n of members) { n.position({ x: centers.get(linked[0]), y: y + n.data("h") / 2 }); y += n.data("h") + 24; }
      bottom = Math.max(bottom, y);
    }
    let y = bottom + 40;
    for (const [key, members] of groups) {
      const linked = key ? key.split("|") : [];
      if (linked.length === 1) continue;
      const x = linked.length ? linked.reduce((sum, id) => sum + centers.get(id), 0) / linked.length : ((sources.length - 1) * columnWidth) / 2;
      for (const n of members) { n.position({ x, y: y + n.data("h") / 2 }); y += n.data("h") + 24; }
    }
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

  followLatest(fresh) {
    // Suivi du direct : on cadre le sujet courant en entier si le texte reste lisible
    // (zoom ≥ MIN_FOLLOW_ZOOM) ; sinon on garde ce zoom et on centre sur les derniers ajouts.
    const cy = this.cy;
    const last = this.topics.length ? cy.getElementById(this.topics[this.topics.length - 1].id) : null;
    if (!last || last.empty()) return;
    const topic = last.union(last.descendants());
    const padding = 30;
    const box = topic.boundingBox();
    const fitZoom = Math.min((cy.width() - 2 * padding) / box.w, (cy.height() - 2 * padding) / box.h);
    this.programmatic = true;
    if (fitZoom >= 0.6) {
      // Le sujet entier reste visible, quitte à descendre un peu sous le zoom de lecture.
      cy.zoom(Math.min(1.3, fitZoom));
      cy.center(topic);
    } else {
      cy.zoom(MIN_FOLLOW_ZOOM);
      cy.center(fresh && fresh.nonempty() ? fresh : topic);
    }
    this.programmatic = false;
  }

  fit(animate) {
    this.follow = true;
    if (this.cy.elements().empty()) return;
    this.programmatic = true;
    if (animate) {
      this.cy.animate({ fit: { eles: this.cy.elements(), padding: 40 } }, { duration: 300, complete: () => { this.programmatic = false; } });
    } else {
      this.cy.fit(this.cy.elements(), 40);
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
