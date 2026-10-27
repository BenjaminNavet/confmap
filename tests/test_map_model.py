"""Tests de la logique de carte."""

import pytest

from confmap.map_model import (
    KINDS,
    UPDATE_JSON_SCHEMA,
    MapUpdate,
    apply_update,
    describe_map,
    is_full,
    restore_topics,
)


def make_update(nodes=(), edges=(), **extra) -> MapUpdate:
    return MapUpdate.model_validate(
        {
            "add": {
                "nodes": [
                    {"id": i, "label": label, "emoji": emoji}
                    for i, label, emoji in nodes
                ],
                "edges": [{"from": a, "to": b, "label": lab} for a, b, lab in edges],
            },
            **extra,
        }
    )


def make_topic(
    topic_id="t1", title="Titre", kind="process", started_at=0.0, node_count=0
):
    return {
        "id": topic_id,
        "title": title,
        "kind": kind,
        "started_at": started_at,
        "nodes": [
            {"id": f"{topic_id}n{k}", "label": f"nœud {k}", "emoji": "", "sources": []}
            for k in range(1, node_count + 1)
        ],
        "edges": [],
    }


def test_empty_map_creates_first_topic():
    topics = []
    added = apply_update(topics, make_update([("a", "Idée", "💡")]), 12.0, ["e1"])
    assert added == ["t1n1"]
    assert topics[0]["id"] == "t1"
    assert topics[0]["title"] == "Sujet 1"
    assert topics[0]["started_at"] == 12.0
    assert topics[0]["nodes"][0] == {
        "id": "t1n1",
        "label": "Idée",
        "emoji": "💡",
        "sources": ["e1"],
    }


def test_empty_update_changes_nothing():
    topics = []
    assert apply_update(topics, make_update(), 0, ["e1"]) == []
    assert topics == []


def test_simple_add_with_edge_to_current_topic():
    topics = [make_topic()]
    update = make_update(
        [("a", "Alpha", ""), ("b", "Beta", "")], [("a", "b", "mène à")]
    )
    added = apply_update(topics, update, 10, ["e1"])
    assert added == ["t1n1", "t1n2"]
    assert topics[0]["edges"] == [{"from": "t1n1", "to": "t1n2", "label": "mène à"}]


def test_label_dedupe_and_sources_merge():
    topics = [make_topic()]
    apply_update(topics, make_update([("a", "Graphe de connaissances", "")]), 1, ["e1"])
    added = apply_update(
        topics,
        make_update([("z", "  graphe  de CONNAISSANCES. ", "")]),
        2,
        ["e2", "e1"],
    )
    assert added == []
    assert len(topics[0]["nodes"]) == 1
    assert topics[0]["nodes"][0]["sources"] == ["e1", "e2"]


def test_accents_are_kept_in_normalization():
    topics = [make_topic()]
    update = make_update([("a", "été", ""), ("b", "ete", "")])
    assert len(apply_update(topics, update, 1, ["e1"])) == 2


def test_edge_to_existing_node_by_map_id():
    topics = [make_topic(node_count=1)]
    update = make_update([("x", "Nouveau", "")], [("t1n1", "x", "cause")])
    apply_update(topics, update, 1, ["e1"])
    assert topics[0]["edges"] == [{"from": "t1n1", "to": "t1n2", "label": "cause"}]


def test_invalid_self_and_duplicate_edges_dropped():
    topics = [make_topic()]
    update = make_update(
        [("a", "A", ""), ("b", "B", "")],
        [
            ("a", "inconnu", "x"),
            ("a", "a", "x"),
            ("a", "b", "un"),
            ("a", "b", "deux"),
            ("b", "a", "retour"),
        ],
    )
    apply_update(topics, update, 1, ["e1"])
    assert [(e["from"], e["to"], e["label"]) for e in topics[0]["edges"]] == [
        ("t1n1", "t1n2", "un"),
        ("t1n2", "t1n1", "retour"),
    ]


def test_duplicate_edge_against_existing_edge_dropped():
    topics = [make_topic(node_count=2)]
    topics[0]["edges"].append({"from": "t1n1", "to": "t1n2", "label": "ok"})
    apply_update(topics, make_update(edges=[("t1n1", "t1n2", "bis")]), 1, ["e1"])
    assert len(topics[0]["edges"]) == 1


def test_empty_labels_skipped():
    topics = [make_topic()]
    update = make_update([("a", "   ", ""), ("b", "Vrai", "")], [("a", "b", "x")])
    assert apply_update(topics, update, 1, ["e1"]) == ["t1n1"]
    assert topics[0]["edges"] == []


def test_is_full_by_node_count_and_duration():
    topic = make_topic(node_count=10)
    assert is_full(topic, now=1)
    assert not is_full(make_topic(node_count=9), now=1)
    assert is_full(make_topic(started_at=100), now=400)
    assert not is_full(make_topic(started_at=100), now=399)
    assert is_full(make_topic(node_count=3), now=5, max_nodes=3)


def test_full_by_node_count_creates_continuation():
    topics = [make_topic(title="Sujet X", kind="timeline", node_count=10)]
    apply_update(topics, make_update([("a", "Autre", "")]), 20, ["e1"])
    assert len(topics) == 2
    assert topics[1]["title"] == "Sujet X (2)"
    assert topics[1]["kind"] == "timeline"
    assert topics[1]["id"] == "t2"
    assert topics[1]["nodes"][0]["id"] == "t2n1"
    assert topics[1]["started_at"] == 20


def test_full_by_duration_creates_continuation():
    topics = [make_topic(title="X", started_at=0, node_count=2)]
    apply_update(topics, make_update([("a", "Autre", "")]), 301, ["e1"])
    assert topics[1]["title"] == "X (2)"
    assert len(topics[0]["nodes"]) == 2


def test_continuation_numbering_increments():
    topics = [make_topic(title="X (2)", node_count=10)]
    apply_update(topics, make_update([("a", "Autre", "")]), 1, ["e1"])
    assert topics[1]["title"] == "X (3)"


def test_full_topic_with_new_title_uses_it():
    topics = [make_topic(title="X", node_count=10)]
    update = make_update(
        [("a", "Autre", "")], new_topic_title="Nouveau thème", new_topic_kind="concept"
    )
    apply_update(topics, update, 1, ["e1"])
    assert topics[1]["title"] == "Nouveau thème"
    assert topics[1]["kind"] == "concept"


def test_numbered_title_cleaned_and_empty_title_defaults():
    topics = [make_topic()]
    update = make_update(
        new_topic={"nodes": [{"id": "a", "label": "A", "emoji": ""}], "edges": []},
        new_topic_title="2. Le  titre",
    )
    apply_update(topics, update, 1, ["e1"])
    assert topics[1]["title"] == "Le titre"
    update = make_update(
        new_topic={"nodes": [{"id": "a", "label": "B", "emoji": ""}], "edges": []},
        new_topic_title="3) Autre",
    )
    apply_update(topics, update, 1, ["e1"])
    assert topics[2]["title"] == "Autre"
    update = make_update(
        new_topic={"nodes": [{"id": "a", "label": "C", "emoji": ""}], "edges": []},
    )
    apply_update(topics, update, 1, ["e1"])
    assert topics[3]["title"] == "Sujet 4"


def test_unknown_kind_falls_back_to_process():
    assert (
        MapUpdate.model_validate({"new_topic_kind": "banane"}).new_topic_kind
        == "process"
    )
    assert (
        MapUpdate.model_validate({"new_topic_kind": "timeline"}).new_topic_kind
        == "timeline"
    )


def test_emoji_filtering():
    topics = [make_topic()]
    update = make_update(
        [("a", "A", "🔥"), ("b", "B", "ab"), ("c", "C", "🔥" * 9), ("d", "D", "1️⃣")]
    )
    apply_update(topics, update, 1, ["e1"])
    assert [node["emoji"] for node in topics[0]["nodes"]] == ["🔥", "", "", ""]


def test_label_whitespace_and_truncation():
    topics = [make_topic()]
    apply_update(topics, make_update([("a", "mot   " + "x" * 100, "")]), 1, ["e1"])
    label = topics[0]["nodes"][0]["label"]
    assert len(label) == 60
    assert label.startswith("mot xxx")


def test_ids_are_coerced_to_str():
    update = MapUpdate.model_validate(
        {
            "add": {
                "nodes": [{"id": 1, "label": "A"}, {"id": 2, "label": "B"}],
                "edges": [{"from": 1, "to": 2}],
            }
        }
    )
    topics = [make_topic()]
    apply_update(topics, update, 1, ["e1"])
    assert len(topics[0]["edges"]) == 1


def test_new_topic_and_add_in_same_answer():
    topics = [make_topic(node_count=1)]
    update = MapUpdate.model_validate(
        {
            "add": {"nodes": [{"id": "a", "label": "Suite"}], "edges": []},
            "new_topic_title": "Autre sujet",
            "new_topic_kind": "comparison",
            "new_topic": {
                "nodes": [{"id": "a", "label": "Un"}, {"id": "b", "label": "Deux"}],
                "edges": [{"from": "a", "to": "b", "label": "vs"}],
            },
        }
    )
    added = apply_update(topics, update, 5, ["e1"])
    assert added == ["t1n2", "t2n1", "t2n2"]
    assert topics[1]["title"] == "Autre sujet"
    assert topics[1]["kind"] == "comparison"
    assert topics[1]["edges"] == [{"from": "t2n1", "to": "t2n2", "label": "vs"}]


def test_new_topic_title_not_used_for_continuation_when_new_topic_has_nodes():
    topics = [make_topic(title="X", node_count=10)]
    update = MapUpdate.model_validate(
        {
            "add": {"nodes": [{"id": "a", "label": "Suite"}]},
            "new_topic_title": "Neuf",
            "new_topic": {"nodes": [{"id": "a", "label": "Z"}]},
        }
    )
    apply_update(topics, update, 1, ["e1"])
    assert [t["title"] for t in topics] == ["X", "X (2)", "Neuf"]


def test_describe_empty_map():
    assert describe_map([], False) == "CARTE : vide (début de la conférence)"


def test_describe_map_with_previous_topics_and_edges():
    topics = [
        make_topic("t1", "A"),
        make_topic("t2", "B"),
        make_topic("t3", "C", "concept", node_count=2),
    ]
    topics[2]["edges"].append({"from": "t3n1", "to": "t3n2", "label": "cause"})
    text = describe_map(topics, current_full=True)
    assert text.splitlines() == [
        "SUJETS PRÉCÉDENTS (terminés) : 1. A; 2. B",
        "SUJET COURANT : 3. C (concept) — PLEIN : mettre la suite dans un nouveau sujet",
        "Boîtes :",
        "- t3n1: nœud 1",
        "- t3n2: nœud 2",
        "Flèches :",
        "- t3n1 -> cause -> t3n2",
    ]


def test_describe_single_topic_no_edges_not_full():
    text = describe_map([make_topic(node_count=1)], current_full=False)
    assert "SUJETS PRÉCÉDENTS" not in text
    assert "PLEIN" not in text
    assert text.endswith("Flèches :\n- (aucune)")


def test_restore_topics_roundtrip():
    topics = [make_topic(node_count=2)]
    topics[0]["edges"].append({"from": "t1n1", "to": "t1n2", "label": "x"})
    assert restore_topics(topics) == topics


@pytest.mark.parametrize(
    "raw",
    [
        "pas une liste",
        [{"id": "t1"}],
        [{"id": "t1", "title": "A", "kind": "banane", "started_at": 0}],
        [make_topic(f"t{k}") for k in range(51)],
    ],
)
def test_restore_topics_rejects_invalid(raw):
    with pytest.raises(ValueError):
        restore_topics(raw)


def test_update_json_schema_shape():
    schema = UPDATE_JSON_SCHEMA
    assert set(schema["required"]) == {
        "add",
        "new_topic_title",
        "new_topic_kind",
        "new_topic",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["new_topic_kind"]["enum"] == list(KINDS)
    graph = schema["properties"]["add"]
    assert graph["required"] == ["nodes", "edges"]
    assert set(graph["properties"]["nodes"]["items"]["required"]) == {
        "id",
        "label",
        "emoji",
    }
    edge_item = graph["properties"]["edges"]["items"]
    assert set(edge_item["required"]) == {"from", "to", "label"}
    assert edge_item["additionalProperties"] is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("adopté par", "adopté par"),
        ("n'exige aucune explication, concept", "n'exige aucune explication"),
        ("conduit très souvent à une chute", "conduit très souvent"),
        ("est", ""),
        ("Est", ""),
        ("  mène   à ", "mène à"),
    ],
)
def test_edge_labels_are_shortened_to_verb_phrases(raw, expected):
    topics = []
    apply_update(
        topics,
        make_update(nodes=[("a", "A", ""), ("b", "B", "")], edges=[("a", "b", raw)]),
        0.0,
        [],
    )
    assert topics[0]["edges"][0]["label"] == expected
