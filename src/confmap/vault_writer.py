"""Écriture de la note Obsidian et du canvas JSON Canvas d'une conférence."""

from __future__ import annotations

import datetime
import json
import logging
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

log = logging.getLogger(__name__)

TOPIC_ICONS = {
    "process": "⚙️",
    "timeline": "⏳",
    "concept": "💡",
    "comparison": "⚖️",
}
# Sens de lecture du diagramme Mermaid selon la nature du sujet.
MERMAID_DIRECTIONS = {"process": "LR", "timeline": "LR", "comparison": "LR"}
DEFAULT_MERMAID_DIRECTION = "TD"
MAX_TITLE_LENGTH = 80
FALLBACK_TITLE = "Conférence"
SUMMARY_DISCLAIMER = (
    "*Généré automatiquement par Claude à partir de la transcription — à vérifier.*"
)
PARAGRAPH_MAX_SECONDS = 45.0
PARAGRAPH_MAX_GAP_SECONDS = 4.0

NODE_HEIGHT = 60
NODE_LINE_HEIGHT = 26
NODE_VERTICAL_PADDING = 28
NODE_HORIZONTAL_PADDING = 24
CHAR_WIDTH = 9
NODE_MIN_WIDTH = 120
NODE_MAX_WIDTH = 260
# Les groupes (un par sujet) sont rangés en grille plutôt que sur une seule ligne.
CANVAS_MAX_ROW_WIDTH = 3000
GROUP_GAP = 120
GROUP_PADDING = 40
GROUP_LABEL_EXTRA = 40
# Disposition hiérarchique : écarts entre niveaux et entre nœuds d'un même niveau.
HORIZONTAL_KINDS = ("timeline", "process", "comparison")
LEVEL_GAP = 90
LEVEL_NODE_GAP = 50
BOX_MARGIN = 30

_FORBIDDEN_TITLE_CHARS = re.compile(r'[/\\:*?"<>|#^\[\]]')
# Entités Mermaid : une étiquette entre guillemets ne doit contenir ni " ni # brut.
_MERMAID_ENTITIES = str.maketrans(
    {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "\n": " ", "\r": " "}
)


class TranscriptLine(BaseModel):
    """Une ligne de transcription horodatée."""

    t0: float
    t1: float
    text_original: str
    text_fr: str
    lang: str


class NoteItem(BaseModel):
    """Une note ou une slide de l'utilisateur."""

    ts: float
    kind: Literal["note", "slide"]
    text: str
    image_path: str = ""
    """Photo d'origine d'une slide (copiée dans le dossier de la note à l'écriture)."""


class RecallQuestion(BaseModel):
    """Question de rappel factuelle, avec sa réponse courte et le passage concerné."""

    question: str
    answer: str
    timestamp: str = ""


class Summary(BaseModel):
    """Résumé final de la conférence."""

    overview: str
    key_points: list[str]
    open_questions: list[str] = []
    recall_questions: list[RecallQuestion] = []


class FinalNoteData(BaseModel):
    """Toutes les données nécessaires à l'écriture dans le vault."""

    title: str
    speaker: str = ""
    date: datetime.date
    source_lang: str
    duration_seconds: float
    audio_path: str = ""
    summary: Summary
    topics: list[dict]
    positions: dict[str, tuple[float, float]] = {}
    notes: list[NoteItem] = []
    transcript: list[TranscriptLine] = []


def sanitize_title(title: str) -> str:
    """Rend un titre utilisable comme nom de fichier et de dossier Obsidian.

    Args:
        title: Titre brut.

    Returns:
        Titre sans caractères interdits, espaces réduits, 80 caractères max,
        ou "Conférence" si le résultat est vide.
    """
    cleaned = _FORBIDDEN_TITLE_CHARS.sub("", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned[:MAX_TITLE_LENGTH].strip()
    return cleaned or FALLBACK_TITLE


def format_timestamp(seconds: float) -> str:
    """Formate des secondes en ``mm:ss``, ou ``hh:mm:ss`` à partir d'une heure.

    Args:
        seconds: Durée en secondes.

    Returns:
        Chaîne horodatée.
    """
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _yaml_string(value: str) -> str:
    """Retourne une chaîne YAML entre guillemets doubles (échappement JSON)."""
    return json.dumps(value, ensure_ascii=False)


def _mermaid_text(label: str) -> str:
    """Rend une étiquette sûre à placer entre guillemets dans un flowchart Mermaid."""
    return re.sub(r"\s+", " ", label.translate(_MERMAID_ENTITIES)).strip()


def _topic_icon(topic: dict) -> str:
    return TOPIC_ICONS.get(topic.get("kind", ""), "")


def _topic_label(topic: dict) -> str:
    return f"{_topic_icon(topic)} {topic.get('title', '')}".strip()


def _render_frontmatter(data: FinalNoteData) -> str:
    duration_minutes = round(data.duration_seconds / 60)
    lines = [
        "---",
        "type: conference",
        f"titre: {_yaml_string(data.title)}",
        f"orateur: {_yaml_string(data.speaker)}",
        f"date: {data.date.isoformat()}",
        f"langue_source: {_yaml_string(data.source_lang)}",
        f"duree: {_yaml_string(f'{duration_minutes}min')}",
        f"audio: {_yaml_string(data.audio_path)}",
        "tags: [conference]",
        "---",
    ]
    return "\n".join(lines)


_TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")


def _parse_timestamp(text: str) -> float:
    """Convertit ``mm:ss`` ou ``hh:mm:ss`` en secondes."""
    seconds = 0
    for part in text.split(":"):
        seconds = seconds * 60 + int(part)
    return float(seconds)


def _block_id(seconds: float) -> str:
    """Identifiant de bloc Obsidian d'un paragraphe de transcription (``t-0130``)."""
    return "t-" + format_timestamp(seconds).replace(":", "")


class _TranscriptAnchors:
    """Liens vers les paragraphes de transcription, par horodatage."""

    def __init__(self, transcript: list[TranscriptLine]) -> None:
        self.starts = [
            int(paragraph[0].t0) for paragraph in _group_paragraphs(transcript)
        ]

    def link(self, seconds: float) -> str:
        """Lien ``[[#^t-mmss|mm:ss]]`` vers le paragraphe le plus proche avant l'instant.

        Sans transcription, retourne l'horodatage en clair.
        """
        label = format_timestamp(seconds)
        candidates = [start for start in self.starts if start <= int(seconds)]
        if not self.starts:
            return label
        target = candidates[-1] if candidates else self.starts[0]
        return f"[[#^{_block_id(target)}|{label}]]"

    def linkify(self, text: str) -> str:
        """Remplace chaque ``[mm:ss]`` du texte par un lien vers la transcription."""
        if not self.starts:
            return text
        return _TIMESTAMP_PATTERN.sub(
            lambda match: f"[{self.link(_parse_timestamp(match.group(1)))}]", text
        )


def _render_recall_questions(
    questions: list[RecallQuestion], anchors: _TranscriptAnchors
) -> list[str]:
    parts = ["", "### Testez-vous", ""]
    for index, item in enumerate(questions):
        if index:
            parts.append("")
        parts.append(f"> [!question]- {item.question.strip()}")
        answer = f"> Réponse : {item.answer.strip()}"
        stamp = item.timestamp.strip("[] ")
        if _TIMESTAMP_PATTERN.fullmatch(f"[{stamp}]"):
            answer += f" [{anchors.link(_parse_timestamp(stamp))}]"
        parts.append(answer)
    return parts


def _render_summary(summary: Summary, anchors: _TranscriptAnchors) -> str:
    parts = ["## Résumé", "", SUMMARY_DISCLAIMER, "", summary.overview.strip()]
    if summary.key_points:
        parts += ["", "**Points clés**", ""]
        parts += [f"- {anchors.linkify(point)}" for point in summary.key_points]
    if summary.recall_questions:
        parts += _render_recall_questions(summary.recall_questions, anchors)
    if summary.open_questions:
        parts += ["", "**Questions ouvertes**", ""]
        parts += [f"- {question}" for question in summary.open_questions]
    return "\n".join(parts)


def _node_text(node: dict) -> str:
    return f"{node.get('emoji', '')} {node.get('label', '')}".strip()


def _render_topic_flowchart(topic: dict) -> list[str]:
    """Traduit un sujet de la carte en flowchart Mermaid (nœuds et flèches)."""
    direction = MERMAID_DIRECTIONS.get(topic.get("kind", ""), DEFAULT_MERMAID_DIRECTION)
    mermaid_ids = {
        node["id"]: f"n{index}" for index, node in enumerate(topic.get("nodes", []))
    }
    lines = ["```mermaid", f"flowchart {direction}"]
    for node in topic.get("nodes", []):
        lines.append(
            f'    {mermaid_ids[node["id"]]}["{_mermaid_text(_node_text(node))}"]'
        )
    for edge in topic.get("edges", []):
        source = mermaid_ids.get(edge.get("from"))
        target = mermaid_ids.get(edge.get("to"))
        if source is None or target is None:
            continue
        label = _mermaid_text(edge.get("label", ""))
        arrow = f'-->|"{label}"|' if label else "-->"
        lines.append(f"    {source} {arrow} {target}")
    lines.append("```")
    return lines


def _render_map_section(data: FinalNoteData, canvas_filename: str) -> str:
    parts = ["## Carte", "", f"Vue d'ensemble : [[{canvas_filename}|carte complète]]"]
    for topic in data.topics:
        parts += ["", f"### {_topic_label(topic)}"]
        if topic.get("nodes"):
            parts += ["", *_render_topic_flowchart(topic)]
    return "\n".join(parts)


def _slide_image_filename(note: NoteItem) -> str:
    """Nom du fichier image d'une slide dans le dossier de la note."""
    return f"slide-{_block_id(note.ts)[2:]}.{_image_extension(note.image_path)}"


def _image_extension(path: str) -> str:
    """Extension déduite des premiers octets (les photos de session n'en ont pas)."""
    try:
        header = Path(path).read_bytes()[:12]
    except OSError:
        return "jpg"
    if header.startswith(b"\x89PNG"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _render_notes(notes: list[NoteItem], anchors: _TranscriptAnchors) -> str:
    parts = ["## Mes notes et slides"]
    if not notes:
        return "\n".join([*parts, "", "_Aucune_"])
    for note in sorted(notes, key=lambda item: item.ts):
        callout = "note" if note.kind == "note" else "example"
        label = "" if note.kind == "note" else "Slide"
        first, *rest = _flatten_markdown(note.text).splitlines() or [""]
        title = (
            f"{anchors.link(note.ts)} {label} {first}"
            if label
            else (f"{anchors.link(note.ts)} {first}")
        )
        body = []
        if note.kind == "slide" and note.image_path:
            body.append(f"![[{_slide_image_filename(note)}]]")
        body += [line for line in rest if line.strip()]
        parts += ["", f"> [!{callout}] {title.strip()}"]
        parts += [f"> {line}" for line in body]
    return "\n".join(parts)


def _flatten_markdown(text: str) -> str:
    """Transforme les titres Markdown en gras (un titre ne peut pas vivre dans une liste)."""
    lines = []
    for line in text.strip().splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        lines.append(
            f"**{heading.group(1).strip('* ')}**" if heading else line.rstrip()
        )
    return "\n".join(lines)


def _group_paragraphs(lines: list[TranscriptLine]) -> list[list[TranscriptLine]]:
    """Regroupe les lignes en paragraphes (durée >= 45 s ou silence > 4 s)."""
    paragraphs: list[list[TranscriptLine]] = []
    current: list[TranscriptLine] = []
    for line in lines:
        if current:
            accumulated = current[-1].t1 - current[0].t0
            gap = line.t0 - current[-1].t1
            if accumulated >= PARAGRAPH_MAX_SECONDS or gap > PARAGRAPH_MAX_GAP_SECONDS:
                paragraphs.append(current)
                current = []
        current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


def _render_transcript(data: FinalNoteData) -> str:
    """Section Transcription repliée : original puis français, un bloc ancré par paragraphe."""
    body = []
    for paragraph in _group_paragraphs(data.transcript):
        french_text = " ".join(line.text_fr.strip() for line in paragraph)
        original_text = " ".join(line.text_original.strip() for line in paragraph)
        stamp = format_timestamp(paragraph[0].t0)
        block = _block_id(paragraph[0].t0)
        if data.source_lang == "fr":
            body += ["", f"**[{stamp}]** {french_text} ^{block}"]
        else:
            body += ["", f"**[{stamp}]** {original_text} ^{block}", "", french_text]
    header = "> [!quote]- Transcription (original | français)"
    quoted = [f"> {line}" if line else ">" for line in body]
    return "\n".join(["## Transcription", "", header, *quoted])


def render_markdown(data: FinalNoteData, canvas_filename: str) -> str:
    """Génère le contenu Markdown de la note de conférence.

    Args:
        data: Données finales de la conférence.
        canvas_filename: Nom du fichier canvas à intégrer dans la section Carte.

    Returns:
        Texte Markdown complet, frontmatter YAML compris.
    """
    anchors = _TranscriptAnchors(data.transcript)
    sections = [
        _render_frontmatter(data),
        _render_summary(data.summary, anchors),
        _render_map_section(data, canvas_filename),
        _render_notes(data.notes, anchors),
        _render_transcript(data),
    ]
    return "\n\n".join(sections) + "\n"


def _node_width(text: str) -> int:
    return max(NODE_MIN_WIDTH, min(NODE_MAX_WIDTH, 40 + 8 * len(text)))


def _node_height(text: str, width: int) -> int:
    """Hauteur suffisante pour afficher tout le texte (retour à la ligne compris)."""
    chars_per_line = max(1, (width - NODE_HORIZONTAL_PADDING) // CHAR_WIDTH)
    line_count = max(1, math.ceil(len(text) / chars_per_line))
    return max(NODE_HEIGHT, NODE_VERTICAL_PADDING + NODE_LINE_HEIGHT * line_count)


@dataclass
class _Box:
    """Boîte d'un nœud sur le canvas (coin haut-gauche)."""

    node: dict
    text: str
    x: int
    y: int
    width: int
    height: int


def _node_levels(topic: dict) -> dict[str, int]:
    """Niveau hiérarchique de chaque nœud (distance BFS depuis les racines).

    Les racines sont les nœuds sans arête entrante ; à défaut (cycle), le nœud
    de plus haut degré. Les nœuds inaccessibles deviennent de nouvelles racines.
    """
    node_ids = [node["id"] for node in topic.get("nodes", [])]
    known = set(node_ids)
    successors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    incoming = dict.fromkeys(node_ids, 0)
    degree = dict.fromkeys(node_ids, 0)
    for edge in topic.get("edges", []):
        source, target = edge.get("from"), edge.get("to")
        if source not in known or target not in known:
            continue
        successors[source].append(target)
        incoming[target] += 1
        degree[source] += 1
        degree[target] += 1

    levels: dict[str, int] = {}
    roots = [node_id for node_id in node_ids if incoming[node_id] == 0]
    while len(levels) < len(node_ids):
        if not roots:
            unvisited = [node_id for node_id in node_ids if node_id not in levels]
            roots = [max(unvisited, key=lambda node_id: degree[node_id])]
        queue = [root for root in roots if root not in levels]
        for root in queue:
            levels[root] = 0
        roots = []
        while queue:
            current = queue.pop(0)
            for target in successors[current]:
                if target not in levels:
                    levels[target] = levels[current] + 1
                    queue.append(target)
    return levels


def _order_by_barycenter(topic: dict, boxes_by_level: dict[int, list[_Box]]) -> None:
    """Range chaque niveau selon la position moyenne des parents (moins de croisements)."""
    parents: dict[str, list[str]] = {}
    for edge in topic.get("edges", []):
        parents.setdefault(edge.get("to"), []).append(edge.get("from"))
    rank: dict[str, float] = {}
    for level in sorted(boxes_by_level):
        level_boxes = boxes_by_level[level]
        for index, box in enumerate(level_boxes):
            ranks = [rank[p] for p in parents.get(box.node["id"], []) if p in rank]
            box_key = sum(ranks) / len(ranks) if ranks else float(index)
            rank.setdefault(box.node["id"], box_key)
        level_boxes.sort(key=lambda b: rank[b.node["id"]])
        for index, box in enumerate(level_boxes):
            rank[box.node["id"]] = float(index)


def _comparison_groups(
    topic: dict,
) -> tuple[list[str], dict[tuple[str, ...], list[str]]]:
    """Éléments comparés (sources des flèches) et caractéristiques groupées par éléments liés."""
    node_ids = [node["id"] for node in topic.get("nodes", [])]
    targets = {edge.get("to") for edge in topic.get("edges", [])}
    sources = [
        node_id
        for node_id in node_ids
        if node_id not in targets
        and any(edge.get("from") == node_id for edge in topic.get("edges", []))
    ]
    groups: dict[tuple[str, ...], list[str]] = {}
    for node_id in node_ids:
        if node_id in sources:
            continue
        linked = tuple(
            sorted(
                (
                    e.get("from")
                    for e in topic.get("edges", [])
                    if e.get("to") == node_id and e.get("from") in sources
                ),
                key=sources.index,
            )
        )
        groups.setdefault(linked, []).append(node_id)
    return sources, groups


def _comparison_boxes(topic: dict) -> list[_Box] | None:
    """Dispose une comparaison de gauche à droite (None si moins de deux éléments comparés).

    Les éléments comparés sont empilés à gauche ; à droite, une colonne de
    caractéristiques : celles du premier élément, puis les partagées, puis celles
    du suivant... Chaque élément est centré face aux siennes : les flèches
    (droite → gauche) s'ouvrent en éventail sans traverser de boîte.
    """
    sources, groups = _comparison_groups(topic)
    if len(sources) < 2:
        return None
    boxes: dict[str, _Box] = {}
    for node in topic.get("nodes", []):
        text = _node_text(node)
        width = _node_width(text)
        boxes[node["id"]] = _Box(node, text, 0, 0, width, _node_height(text, width))
    column_x = max(boxes[s].width for s in sources) + 2 * LEVEL_GAP
    ordered: list[str] = []
    for source in sources:
        ordered += groups.get((source,), [])
        for linked, members in groups.items():
            if len(linked) > 1 and linked[0] == source:
                ordered += members
    ordered += groups.get((), [])
    cursor = 0
    for member in ordered:
        box = boxes[member]
        box.x, box.y = column_x, cursor
        cursor += box.height + LEVEL_NODE_GAP // 2
    previous_bottom = -LEVEL_NODE_GAP
    for source in sources:
        linked = [
            boxes[e.get("to")]
            for e in topic.get("edges", [])
            if e.get("from") == source and e.get("to") in boxes
        ]
        box = boxes[source]
        center = sum(b.y + b.height / 2 for b in linked) / len(linked)
        box.x = 0
        box.y = max(int(center - box.height / 2), previous_bottom + LEVEL_NODE_GAP)
        previous_bottom = box.y + box.height
    return list(boxes.values())


def _topic_node_boxes(topic: dict) -> list[_Box]:
    """Dispose les nœuds d'un sujet en niveaux réguliers, sans chevauchement.

    Un niveau par rangée (de haut en bas), ou par colonne (de gauche à droite)
    pour les sujets « timeline » et « process ».
    """
    if topic.get("kind") == "comparison":
        comparison = _comparison_boxes(topic)
        if comparison is not None:
            return comparison
    nodes = topic.get("nodes", [])
    horizontal = topic.get("kind") in HORIZONTAL_KINDS
    levels = _node_levels(topic)
    boxes_by_level: dict[int, list[_Box]] = {}
    for node in nodes:
        text = _node_text(node)
        width = _node_width(text)
        box = _Box(node, text, 0, 0, width, _node_height(text, width))
        boxes_by_level.setdefault(levels[node["id"]], []).append(box)

    def extent(box: _Box) -> int:
        return box.height if horizontal else box.width

    def thickness(box: _Box) -> int:
        return box.width if horizontal else box.height

    _order_by_barycenter(topic, boxes_by_level)
    level_sizes = {
        level: sum(extent(b) for b in level_boxes)
        + LEVEL_NODE_GAP * (len(level_boxes) - 1)
        for level, level_boxes in boxes_by_level.items()
    }
    widest = max(level_sizes.values(), default=0)
    cursor = 0
    for level in sorted(boxes_by_level):
        level_boxes = boxes_by_level[level]
        offset = (widest - level_sizes[level]) // 2
        for box in level_boxes:
            if horizontal:
                box.x, box.y = cursor, offset
            else:
                box.x, box.y = offset, cursor
            offset += extent(box) + LEVEL_NODE_GAP
        cursor += max(thickness(b) for b in level_boxes) + LEVEL_GAP
    return _resolve_overlaps(
        [box for level in sorted(boxes_by_level) for box in boxes_by_level[level]]
    )


def _resolve_overlaps(boxes: list[_Box]) -> list[_Box]:
    """Décale vers le bas les boîtes qui se chevauchent encore (avec une marge)."""
    placed: list[_Box] = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        moved = True
        while moved:
            moved = False
            for other in placed:
                overlap_x = (
                    box.x < other.x + other.width + BOX_MARGIN
                    and other.x < box.x + box.width + BOX_MARGIN
                )
                overlap_y = (
                    box.y < other.y + other.height + BOX_MARGIN
                    and other.y < box.y + box.height + BOX_MARGIN
                )
                if overlap_x and overlap_y:
                    box.y = other.y + other.height + BOX_MARGIN
                    moved = True
        placed.append(box)
    return boxes


def _pack_groups(topic_boxes: list[list[_Box]]) -> None:
    """Range les sujets en grille (lignes de largeur bornée), en place.

    La disposition interne de chaque sujet est conservée ; seuls les sujets
    sont déplacés, pour éviter un canvas d'une seule ligne très large.
    """
    cursor_x = cursor_y = row_height = 0
    for boxes in topic_boxes:
        if not boxes:
            continue
        min_x = min(b.x for b in boxes) - GROUP_PADDING
        min_y = min(b.y for b in boxes) - GROUP_PADDING - GROUP_LABEL_EXTRA
        width = max(b.x + b.width for b in boxes) + GROUP_PADDING - min_x
        height = max(b.y + b.height for b in boxes) + GROUP_PADDING - min_y
        if cursor_x and cursor_x + width > CANVAS_MAX_ROW_WIDTH:
            cursor_x, cursor_y, row_height = 0, cursor_y + row_height + GROUP_GAP, 0
        for box in boxes:
            box.x += cursor_x - min_x
            box.y += cursor_y - min_y
        cursor_x += width + GROUP_GAP
        row_height = max(row_height, height)


def _unique_id(wanted: str, used_ids: set[str]) -> str:
    candidate = wanted
    suffix = 2
    while candidate in used_ids:
        candidate = f"{wanted}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def render_canvas(data: FinalNoteData) -> dict[str, Any]:
    """Génère le canvas JSON Canvas 1.0 de la carte.

    Args:
        data: Données finales de la conférence (topics, positions).

    Returns:
        Dictionnaire ``{"nodes": [...], "edges": [...]}`` sérialisable en JSON.
    """
    group_nodes: list[dict[str, Any]] = []
    text_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    topic_boxes = [_topic_node_boxes(topic) for topic in data.topics]
    _pack_groups(topic_boxes)
    for topic_index, (topic, boxes) in enumerate(
        zip(data.topics, topic_boxes, strict=True)
    ):
        if not boxes:
            continue
        canvas_ids: dict[str, str] = {}
        horizontal = topic.get("kind") in HORIZONTAL_KINDS
        from_side, to_side = ("right", "left") if horizontal else ("bottom", "top")
        for box in boxes:
            canvas_id = _unique_id(str(box.node["id"]), used_ids)
            canvas_ids[box.node["id"]] = canvas_id
            text_nodes.append(
                {
                    "id": canvas_id,
                    "type": "text",
                    "text": box.text,
                    "x": box.x,
                    "y": box.y,
                    "width": box.width,
                    "height": box.height,
                }
            )
        group_x = min(b.x for b in boxes) - GROUP_PADDING
        group_y = min(b.y for b in boxes) - GROUP_PADDING - GROUP_LABEL_EXTRA
        group_nodes.append(
            {
                "id": _unique_id(f"g-{topic.get('id', topic_index)}", used_ids),
                "type": "group",
                "label": _topic_label(topic),
                "x": group_x,
                "y": group_y,
                "width": max(b.x + b.width for b in boxes) + GROUP_PADDING - group_x,
                "height": max(b.y + b.height for b in boxes) + GROUP_PADDING - group_y,
            }
        )
        for edge_index, edge in enumerate(topic.get("edges", [])):
            source = canvas_ids.get(edge.get("from"))
            target = canvas_ids.get(edge.get("to"))
            if source is None or target is None:
                continue
            canvas_edge: dict[str, Any] = {
                "id": _unique_id(f"e-{source}-{target}-{edge_index}", used_ids),
                "fromNode": source,
                "fromSide": from_side,
                "toSide": to_side,
                "toNode": target,
            }
            if edge.get("label"):
                canvas_edge["label"] = edge["label"]
            edges.append(canvas_edge)

    return {"nodes": group_nodes + text_nodes, "edges": edges}


def _create_unique_folder(vault_root: Path, folder_name: str) -> Path:
    """Crée le dossier, avec suffixe " (n)" s'il existe déjà (jamais d'écrasement)."""
    vault_root.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        name = folder_name if attempt == 1 else f"{folder_name} ({attempt})"
        folder = vault_root / name
        try:
            folder.mkdir()
        except FileExistsError:
            attempt += 1
            continue
        return folder


def write_conference(data: FinalNoteData, vault_root: Path) -> Path:
    """Écrit la note ``.md`` et le ``.canvas`` d'une conférence dans le vault.

    Args:
        data: Données finales de la conférence.
        vault_root: Dossier racine des conférences dans le vault.

    Returns:
        Chemin du fichier Markdown écrit.
    """
    safe_title = sanitize_title(data.title)
    folder = _create_unique_folder(
        Path(vault_root), f"{data.date.isoformat()} {safe_title}"
    )
    canvas_filename = f"{safe_title}.canvas"
    for note in data.notes:
        if note.kind == "slide" and note.image_path:
            try:
                shutil.copyfile(note.image_path, folder / _slide_image_filename(note))
            except OSError:
                log.warning("photo de slide introuvable : %s", note.image_path)
    markdown_path = folder / f"{safe_title}.md"
    markdown_path.write_text(render_markdown(data, canvas_filename), encoding="utf-8")
    (folder / canvas_filename).write_text(
        json.dumps(render_canvas(data), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return markdown_path
