"""Écriture de la note Obsidian et du canvas JSON Canvas d'une conférence."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

TOPIC_ICONS = {
    "process": "⚙️",
    "timeline": "⏳",
    "concept": "💡",
    "comparison": "⚖️",
}
MAX_MERMAID_TOPICS = 25
MAX_TITLE_LENGTH = 80
FALLBACK_TITLE = "Conférence"
PARAGRAPH_MAX_SECONDS = 45.0
PARAGRAPH_MAX_GAP_SECONDS = 4.0

FALLBACK_COLUMN_WIDTH = 320
FALLBACK_COLUMN_GAP = 80
FALLBACK_NODE_SPACING = 100
NODE_HEIGHT = 60
NODE_MIN_WIDTH = 120
NODE_MAX_WIDTH = 260
GROUP_PADDING = 40
GROUP_LABEL_EXTRA = 40
# Les boîtes du canvas Obsidian sont plus grandes que celles de l'app : on écarte
# les positions de l'app pour garder la même disposition sans chevauchement.
POSITION_SCALE_X = 1.7
POSITION_SCALE_Y = 2.2
BOX_MARGIN = 30

_FORBIDDEN_TITLE_CHARS = re.compile(r'[/\\:*?"<>|#^\[\]]')
_MERMAID_ESCAPES = str.maketrans(
    {
        "(": "（",
        ")": "）",
        "[": "［",
        "]": "］",
        "{": "｛",
        "}": "｝",
        '"': "'",
        "\n": " ",
        "\r": " ",
    }
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


def _escape_mermaid(label: str) -> str:
    """Neutralise les caractères qui cassent la syntaxe mindmap Mermaid."""
    return label.translate(_MERMAID_ESCAPES).strip()


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


def _render_map_section(data: FinalNoteData, canvas_filename: str) -> str:
    mindmap = ["```mermaid", "mindmap", f"  root(({_escape_mermaid(data.title)}))"]
    for topic in data.topics[:MAX_MERMAID_TOPICS]:
        mindmap.append(f"    {_escape_mermaid(_topic_label(topic))}")
    mindmap.append("```")
    return "\n".join(["## Carte", "", *mindmap, "", f"![[{canvas_filename}]]"])


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


def _topic_node_boxes(
    topic: dict, topic_index: int, positions: dict[str, tuple[float, float]]
) -> list[tuple[dict, str, int, int, int]]:
    """Calcule (noeud, texte, x, y, largeur) du coin haut-gauche de chaque noeud."""
    nodes = topic.get("nodes", [])
    texts = [
        f"{node.get('emoji', '')} {node.get('label', '')}".strip() for node in nodes
    ]
    widths = [_node_width(text) for text in texts]
    use_positions = bool(nodes) and all(node["id"] in positions for node in nodes)
    boxes = []
    column_x = topic_index * (FALLBACK_COLUMN_WIDTH + FALLBACK_COLUMN_GAP)
    for row, (node, text, width) in enumerate(zip(nodes, texts, widths, strict=True)):
        if use_positions:
            center_x, center_y = positions[node["id"]]
            center_x *= POSITION_SCALE_X
            center_y *= POSITION_SCALE_Y
            x = round(center_x - width / 2)
            y = round(center_y - NODE_HEIGHT / 2)
        else:
            x = column_x + GROUP_PADDING
            y = GROUP_PADDING + GROUP_LABEL_EXTRA + row * FALLBACK_NODE_SPACING
        boxes.append((node, text, x, y, width))
    return _resolve_overlaps(boxes)


def _resolve_overlaps(
    boxes: list[tuple[dict, str, int, int, int]],
) -> list[tuple[dict, str, int, int, int]]:
    """Décale vers le bas les boîtes qui se chevauchent encore (avec une marge)."""
    placed: list[list] = []
    for box in sorted(boxes, key=lambda b: (b[3], b[2])):
        node, text, x, y, width = box
        moved = True
        while moved:
            moved = False
            for _, _, other_x, other_y, other_width in placed:
                overlap_x = x < other_x + other_width + BOX_MARGIN and other_x < x + width + BOX_MARGIN
                overlap_y = y < other_y + NODE_HEIGHT + BOX_MARGIN and other_y < y + NODE_HEIGHT + BOX_MARGIN
                if overlap_x and overlap_y:
                    y = other_y + NODE_HEIGHT + BOX_MARGIN
                    moved = True
        placed.append([node, text, x, y, width])
    order = {id(b[0]): i for i, b in enumerate(boxes)}
    return [tuple(b) for b in sorted(placed, key=lambda b: order[id(b[0])])]


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

    for topic_index, topic in enumerate(data.topics):
        boxes = _topic_node_boxes(topic, topic_index, data.positions)
        if not boxes:
            continue
        canvas_ids: dict[str, str] = {}
        for node, text, x, y, width in boxes:
            canvas_id = _unique_id(str(node["id"]), used_ids)
            canvas_ids[node["id"]] = canvas_id
            text_nodes.append(
                {
                    "id": canvas_id,
                    "type": "text",
                    "text": text,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": NODE_HEIGHT,
                }
            )
        min_x = min(x for _, _, x, _, _ in boxes)
        min_y = min(y for _, _, _, y, _ in boxes)
        max_x = max(x + width for _, _, x, _, width in boxes)
        max_y = max(y + NODE_HEIGHT for _, _, _, y, _ in boxes)
        group_x = min_x - GROUP_PADDING
        group_y = min_y - GROUP_PADDING - GROUP_LABEL_EXTRA
        group_nodes.append(
            {
                "id": _unique_id(f"g-{topic.get('id', topic_index)}", used_ids),
                "type": "group",
                "label": _topic_label(topic),
                "x": group_x,
                "y": group_y,
                "width": max_x + GROUP_PADDING - group_x,
                "height": max_y + GROUP_PADDING - group_y,
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
