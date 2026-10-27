"""Écriture de la note Obsidian et du canvas JSON Canvas d'une conférence."""

from __future__ import annotations

import datetime
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

TOPIC_ICONS = {
    "process": "⚙️",
    "timeline": "⏳",
    "concept": "💡",
    "comparison": "⚖️",
}
# Sens de lecture du diagramme Mermaid selon la nature du sujet.
MERMAID_DIRECTIONS = {"process": "LR", "timeline": "LR"}
DEFAULT_MERMAID_DIRECTION = "TD"
MAX_TITLE_LENGTH = 80
FALLBACK_TITLE = "Conférence"
PARAGRAPH_MAX_SECONDS = 45.0
PARAGRAPH_MAX_GAP_SECONDS = 4.0

FALLBACK_COLUMN_WIDTH = 320
FALLBACK_COLUMN_GAP = 80
FALLBACK_NODE_SPACING = 100
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
# Les boîtes du canvas Obsidian sont plus grandes que celles de l'app : on écarte
# les positions de l'app pour garder la même disposition sans chevauchement.
POSITION_SCALE_X = 1.7
POSITION_SCALE_Y = 2.2
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


class Summary(BaseModel):
    """Résumé final de la conférence."""

    overview: str
    key_points: list[str]
    open_questions: list[str] = []


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


def _render_summary(summary: Summary) -> str:
    parts = ["## Résumé", "", summary.overview.strip()]
    if summary.key_points:
        parts += ["", "**Points clés**", ""]
        parts += [f"- {point}" for point in summary.key_points]
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
        lines.append(f'    {mermaid_ids[node["id"]]}["{_mermaid_text(_node_text(node))}"]')
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


def _render_notes(notes: list[NoteItem]) -> str:
    parts = ["## Mes notes et slides", ""]
    if not notes:
        parts.append("_Aucune_")
        return "\n".join(parts)
    for note in sorted(notes, key=lambda item: item.ts):
        prefix = "📝" if note.kind == "note" else "📷 Slide :"
        first, *rest = _flatten_markdown(note.text).splitlines() or [""]
        parts.append(f"- **[{format_timestamp(note.ts)}]** {prefix} {first}")
        # Lignes suivantes indentées pour rester dans l'élément de liste.
        parts += [f"    {line}" for line in rest if line.strip()]
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
    parts = ["## Transcription"]
    for paragraph in _group_paragraphs(data.transcript):
        french_text = " ".join(line.text_fr.strip() for line in paragraph)
        parts += ["", f"**[{format_timestamp(paragraph[0].t0)}]** {french_text}"]
        if data.source_lang != "fr":
            original_text = " ".join(line.text_original.strip() for line in paragraph)
            parts += ["", f"> *{original_text}*"]
    return "\n".join(parts)


def render_markdown(data: FinalNoteData, canvas_filename: str) -> str:
    """Génère le contenu Markdown de la note de conférence.

    Args:
        data: Données finales de la conférence.
        canvas_filename: Nom du fichier canvas à intégrer dans la section Carte.

    Returns:
        Texte Markdown complet, frontmatter YAML compris.
    """
    sections = [
        _render_frontmatter(data),
        _render_summary(data.summary),
        _render_map_section(data, canvas_filename),
        _render_notes(data.notes),
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


def _topic_node_boxes(
    topic: dict, topic_index: int, positions: dict[str, tuple[float, float]]
) -> list[_Box]:
    """Calcule la boîte de chaque nœud d'un sujet, sans chevauchement."""
    nodes = topic.get("nodes", [])
    use_positions = bool(nodes) and all(node["id"] in positions for node in nodes)
    column_x = topic_index * (FALLBACK_COLUMN_WIDTH + FALLBACK_COLUMN_GAP)
    boxes = []
    for row, node in enumerate(nodes):
        text = _node_text(node)
        width = _node_width(text)
        height = _node_height(text, width)
        if use_positions:
            center_x, center_y = positions[node["id"]]
            x = round(center_x * POSITION_SCALE_X - width / 2)
            y = round(center_y * POSITION_SCALE_Y - height / 2)
        else:
            x = column_x + GROUP_PADDING
            y = GROUP_PADDING + GROUP_LABEL_EXTRA + row * FALLBACK_NODE_SPACING
        boxes.append(_Box(node, text, x, y, width, height))
    return _resolve_overlaps(boxes)


def _resolve_overlaps(boxes: list[_Box]) -> list[_Box]:
    """Décale vers le bas les boîtes qui se chevauchent encore (avec une marge)."""
    placed: list[_Box] = []
    for box in sorted(boxes, key=lambda b: (b.y, b.x)):
        moved = True
        while moved:
            moved = False
            for other in placed:
                overlap_x = box.x < other.x + other.width + BOX_MARGIN and other.x < box.x + box.width + BOX_MARGIN
                overlap_y = box.y < other.y + other.height + BOX_MARGIN and other.y < box.y + box.height + BOX_MARGIN
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

    topic_boxes = [
        _topic_node_boxes(topic, topic_index, data.positions)
        for topic_index, topic in enumerate(data.topics)
    ]
    _pack_groups(topic_boxes)
    for topic_index, (topic, boxes) in enumerate(zip(data.topics, topic_boxes, strict=True)):
        if not boxes:
            continue
        canvas_ids: dict[str, str] = {}
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
    markdown_path = folder / f"{safe_title}.md"
    markdown_path.write_text(render_markdown(data, canvas_filename), encoding="utf-8")
    (folder / canvas_filename).write_text(
        json.dumps(render_canvas(data), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return markdown_path
