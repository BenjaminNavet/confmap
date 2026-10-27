"""Logique pure de la carte des idées : fusion d'une réponse LLM dans la carte.

Aucune I/O ni appel LLM. Les topics sont des dicts simples, envoyés tels quels
au navigateur.
"""

from __future__ import annotations

import re
import string
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.functional_validators import BeforeValidator

KINDS: tuple[str, ...] = ("process", "timeline", "concept", "comparison")
DEFAULT_KIND = "process"
MAX_LABEL_CHARS = 60
MAX_EMOJI_CHARS = 8
MAX_RESTORED_TOPICS = 50

_CONTINUATION_PATTERN = re.compile(r"^(?P<base>.*?)\s*\((?P<number>\d+)\)$")
_LEADING_NUMBERING_PATTERN = re.compile(r"^\s*\d+\s*[.)]\s+")


def _coerce_to_str(value: object) -> object:
    """Convertit les ids numériques en chaînes."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return str(value)
    return value


IdString = Annotated[str, BeforeValidator(_coerce_to_str)]


class MapNode(BaseModel):
    """Nœud tel que produit par le LLM."""

    id: IdString
    label: str
    emoji: str = ""


class MapEdge(BaseModel):
    """Flèche telle que produite par le LLM."""

    model_config = ConfigDict(populate_by_name=True)

    from_: IdString = Field(alias="from")
    to: IdString
    label: str = ""


class MapGraph(BaseModel):
    """Ensemble de nœuds et de flèches."""

    nodes: list[MapNode] = Field(default_factory=list)
    edges: list[MapEdge] = Field(default_factory=list)


class MapUpdate(BaseModel):
    """Réponse structurée du LLM pour un appel de mise à jour."""

    add: MapGraph = Field(default_factory=MapGraph)
    new_topic_title: str = ""
    new_topic_kind: str = DEFAULT_KIND
    new_topic: MapGraph = Field(default_factory=MapGraph)

    @field_validator("new_topic_kind", mode="after")
    @classmethod
    def _fallback_unknown_kind(cls, kind: str) -> str:
        return kind if kind in KINDS else DEFAULT_KIND


def _graph_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "emoji": {"type": "string"},
                    },
                    "required": ["id", "label", "emoji"],
                    "additionalProperties": False,
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["from", "to", "label"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["nodes", "edges"],
        "additionalProperties": False,
    }


UPDATE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "add": _graph_schema(),
        "new_topic_title": {"type": "string"},
        "new_topic_kind": {"type": "string", "enum": list(KINDS)},
        "new_topic": _graph_schema(),
    },
    "required": ["add", "new_topic_title", "new_topic_kind", "new_topic"],
    "additionalProperties": False,
}


# --- Validation de la carte persistée -------------------------------------


class _StoredNode(BaseModel):
    id: str
    label: str
    emoji: str = ""
    sources: list[str] = Field(default_factory=list)


class _StoredEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    label: str = ""


class _StoredTopic(BaseModel):
    id: str
    title: str
    kind: Literal["process", "timeline", "concept", "comparison"]
    started_at: float
    nodes: list[_StoredNode] = Field(default_factory=list)
    edges: list[_StoredEdge] = Field(default_factory=list)


def restore_topics(raw: object) -> list[dict]:
    """Valide une liste de topics persistée et la renvoie sous forme de dicts.

    Args:
        raw: Données brutes (typiquement lues depuis un fichier JSON).

    Returns:
        Les topics validés, avec les flèches sous la clé ``from``.

    Raises:
        ValueError: Si ``raw`` n'est pas une liste de ≤ 50 topics valides.
    """
    if not isinstance(raw, list):
        raise ValueError("les topics doivent être une liste")
    if len(raw) > MAX_RESTORED_TOPICS:
        raise ValueError(f"trop de topics ({len(raw)} > {MAX_RESTORED_TOPICS})")
    # pydantic.ValidationError hérite de ValueError.
    return [_StoredTopic.model_validate(item).model_dump(by_alias=True) for item in raw]


# --- Utilitaires de texte -------------------------------------------------


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _normalize_label(label: str) -> str:
    """Minuscule, ponctuation retirée, espaces réduits ; accents conservés."""
    lowered = unicodedata.normalize("NFC", label).lower()
    without_punctuation = "".join(
        " "
        if (char in string.punctuation or unicodedata.category(char).startswith("P"))
        else char
        for char in lowered
    )
    return _collapse_whitespace(without_punctuation)


def _clean_label(label: str) -> str:
    return _collapse_whitespace(label)[:MAX_LABEL_CHARS].strip()


MAX_EDGE_LABEL_WORDS = 3
_EMPTY_EDGE_LABELS = {"est", "sont", "a", "ont", "être"}


def _clean_edge_label(label: str) -> str:
    """Ramène une étiquette de flèche à un verbe court (3 mots au plus, sans virgule)."""
    first_clause = _collapse_whitespace(label).split(",")[0]
    words = first_clause.split()[:MAX_EDGE_LABEL_WORDS]
    cleaned = " ".join(words).strip(" .;:")
    if cleaned.lower() in _EMPTY_EDGE_LABELS:
        return ""
    return cleaned


def _clean_emoji(emoji: str) -> str:
    stripped = emoji.strip()
    if len(stripped) > MAX_EMOJI_CHARS or any(char.isalnum() for char in stripped):
        return ""
    return stripped


def _clean_title(title: str) -> str:
    return _collapse_whitespace(_LEADING_NUMBERING_PATTERN.sub("", title.strip()))


# --- Règles de remplissage ------------------------------------------------


def is_full(
    topic: dict, now: float, max_nodes: int = 10, max_seconds: float = 300
) -> bool:
    """Indique si un topic est plein (trop de nœuds ou trop ancien).

    Args:
        topic: Topic à tester.
        now: Temps de session courant en secondes.
        max_nodes: Nombre de nœuds à partir duquel le topic est plein.
        max_seconds: Durée à partir de laquelle le topic est plein.

    Returns:
        True si le topic est plein.
    """
    return len(topic["nodes"]) >= max_nodes or now - topic["started_at"] >= max_seconds


def _continuation_title(previous_title: str) -> str:
    match = _CONTINUATION_PATTERN.match(previous_title)
    if match and match.group("base"):
        return f"{match.group('base')} ({int(match.group('number')) + 1})"
    return f"{previous_title} (2)"


def _create_topic(topics: list[dict], title: str, kind: str, now: float) -> dict:
    topic_id = f"t{len(topics) + 1}"
    topic = {
        "id": topic_id,
        "title": title or f"Sujet {len(topics) + 1}",
        "kind": kind if kind in KINDS else DEFAULT_KIND,
        "started_at": now,
        "nodes": [],
        "edges": [],
    }
    topics.append(topic)
    return topic


def _merge_graph(topic: dict, graph: MapGraph, source_ids: list[str]) -> list[str]:
    """Fusionne un graphe LLM dans un topic ; renvoie les ids des nœuds créés."""
    nodes_by_normalized_label = {
        _normalize_label(node["label"]): node for node in topic["nodes"]
    }
    known_node_ids = {node["id"] for node in topic["nodes"]}
    llm_id_to_node_id: dict[str, str] = {}
    added_node_ids: list[str] = []

    for llm_node in graph.nodes:
        label = _clean_label(llm_node.label)
        normalized = _normalize_label(label)
        if not normalized:
            continue
        existing = nodes_by_normalized_label.get(normalized)
        if existing is None:
            existing = {
                "id": f"{topic['id']}n{len(topic['nodes']) + 1}",
                "label": label,
                "emoji": _clean_emoji(llm_node.emoji),
                "sources": [],
            }
            topic["nodes"].append(existing)
            nodes_by_normalized_label[normalized] = existing
            known_node_ids.add(existing["id"])
            added_node_ids.append(existing["id"])
        for source_id in source_ids:
            if source_id not in existing["sources"]:
                existing["sources"].append(source_id)
        llm_id_to_node_id[llm_node.id] = existing["id"]

    existing_pairs = {(edge["from"], edge["to"]) for edge in topic["edges"]}
    for llm_edge in graph.edges:
        source_node = llm_id_to_node_id.get(llm_edge.from_, llm_edge.from_)
        target_node = llm_id_to_node_id.get(llm_edge.to, llm_edge.to)
        if source_node not in known_node_ids or target_node not in known_node_ids:
            continue
        if source_node == target_node or (source_node, target_node) in existing_pairs:
            continue
        existing_pairs.add((source_node, target_node))
        topic["edges"].append(
            {
                "from": source_node,
                "to": target_node,
                "label": _clean_edge_label(llm_edge.label),
            }
        )
    return added_node_ids


def apply_update(
    topics: list[dict],
    update: MapUpdate,
    now: float,
    source_ids: list[str],
    max_nodes: int = 10,
    max_seconds: float = 300,
) -> list[str]:
    """Fusionne une réponse LLM dans la carte (modification en place).

    Les nœuds de ``add`` vont dans le topic courant (le dernier), ou dans une
    continuation s'il n'existe pas ou s'il est plein. ``new_topic`` crée un
    nouveau topic. Les éléments invalides sont ignorés silencieusement.

    Args:
        topics: Carte courante, modifiée en place.
        update: Réponse validée du LLM.
        now: Temps de session courant en secondes.
        source_ids: Ids des évènements à l'origine de cette réponse.
        max_nodes: Capacité en nœuds d'un topic.
        max_seconds: Durée de vie maximale d'un topic.

    Returns:
        Les ids des nœuds ajoutés (les nœuds réutilisés n'y figurent pas).
    """
    added_node_ids: list[str] = []
    new_topic_has_nodes = any(
        _clean_label(node.label) for node in update.new_topic.nodes
    )
    cleaned_title = _clean_title(update.new_topic_title)

    if any(_clean_label(node.label) for node in update.add.nodes):
        current = topics[-1] if topics else None
        if current is None or is_full(current, now, max_nodes, max_seconds):
            if current is None or cleaned_title and not new_topic_has_nodes:
                title, kind = cleaned_title, update.new_topic_kind
            else:
                title, kind = _continuation_title(current["title"]), current["kind"]
            current = _create_topic(topics, title, kind, now)
        added_node_ids += _merge_graph(current, update.add, source_ids)

    if new_topic_has_nodes:
        created = _create_topic(topics, cleaned_title, update.new_topic_kind, now)
        added_node_ids += _merge_graph(created, update.new_topic, source_ids)

    return added_node_ids


def describe_map(topics: list[dict], current_full: bool) -> str:
    """Décrit la carte en français, de façon compacte, pour le prompt.

    Args:
        topics: Carte courante.
        current_full: Si le topic courant est plein.

    Returns:
        Le texte à insérer dans le prompt.
    """
    if not topics:
        return "CARTE : vide (début de la conférence)"
    lines: list[str] = []
    previous = topics[:-1]
    if previous:
        listing = "; ".join(
            f"{index}. {topic['title']}" for index, topic in enumerate(previous, 1)
        )
        lines.append(f"SUJETS PRÉCÉDENTS (terminés) : {listing}")
    current = topics[-1]
    header = f"SUJET COURANT : {len(topics)}. {current['title']} ({current['kind']})"
    if current_full:
        header += " — PLEIN : mettre la suite dans un nouveau sujet"
    lines.append(header)
    lines.append("Boîtes :")
    lines += [f"- {node['id']}: {node['label']}" for node in current["nodes"]]
    lines.append("Flèches :")
    if current["edges"]:
        lines += [
            f"- {edge['from']} -> {edge['label']} -> {edge['to']}"
            for edge in current["edges"]
        ]
    else:
        lines.append("- (aucune)")
    return "\n".join(lines)
