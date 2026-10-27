// Carte des idées : un groupe par sujet, posés de gauche à droite.
// Les sujets terminés ne bougent plus ; seuls les sujets modifiés sont réorganisés.
"use strict";

const KIND_INFO = {
  process: { icon: "⚙️", layout: { name: "dagre", rankDir: "TB", nodeSep: 40, rankSep: 55 } },
  timeline: { icon: "⏳", layout: { name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 60 } },
  comparison: { icon: "⚖️", layout: { name: "dagre", rankDir: "TB", nodeSep: 30, rankSep: 80 } },
  concept: { icon: "💡", layout: null },
};
const TOPIC_GAP = 140;
const FRESH_MS = 4000;

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
    this.cy = cytoscape({
      container,
      wheelSensitivity: 0.25,
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
          "border-color": kindColor,
          "border-width": 1.5,
          label: "data(label)",
          "text-wrap": "wrap",
          "text-max-width": 150,
          "text-valign": "center",
          "font-size": 13,
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
          "font-size": 11,
          color: cssVar("--muted"),
          "text-background-color": cssVar("--bg"),
          "text-background-opacity": 0.9,
          "text-background-padding": 2,
          "text-rotation": "autorotate",
        },
      },
      { selector: "node.idea.fresh", style: { "underlay-color": cssVar("--fresh-glow"), "underlay-opacity": 0.55, "underlay-padding": 8 } },
      { selector: "node.idea.highlight", style: { "border-width": 3 } },
    ];
  }

  nodeSize(text) {
    const length = text.length;
    const width = Math.max(80, Math.min(170, 22 + length * 7.2));
    const lines = Math.ceil((length * 7.2) / 150);
    return { w: width, h: 30 + Math.max(0, lines - 1) * 16 };
  }

  setSavedPositions(positions) {
    this.savedPositions = Object.assign({}, positions || {});
  }

  render(topics, addedIds = [], sourceText = "") {
    this.topics = topics || [];
    if (sourceText) this.lastSource = sourceText;
    const cy = this.cy;
    const changed = [];
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
    if (fresh.nonempty()) {
      fresh.addClass("fresh");
      setTimeout(() => fresh.removeClass("fresh"), FRESH_MS);
    }
    if (this.follow) this.fit(false);
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
      const allSaved = !force && kids.every((k) => this.savedPositions[k.id()]);
      if (allSaved) {
        kids.forEach((k) => { const [x, y] = this.savedPositions[k.id()]; k.position({ x, y }); });
        return;
      }
      if (topic.kind === "concept") this.layoutConcept(kids);
      else kids.union(kids.connectedEdges()).layout({ ...(KIND_INFO[topic.kind] || KIND_INFO.process).layout, fit: false, animate: false }).run();
      // Place le sujet à droite du précédent, en haut.
      const box = kids.boundingBox();
      const dx = this.topicAnchorX(index) - box.x1;
      const dy = 0 - box.y1;
      kids.positions((k) => ({ x: k.position("x") + dx, y: k.position("y") + dy }));
    });
    // Les sujets suivants (rares : réorganisation) sont décalés pour ne pas se chevaucher.
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
    this.layoutTopics(this.topics.map((t) => t.id), true);
    this.fit(true);
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
