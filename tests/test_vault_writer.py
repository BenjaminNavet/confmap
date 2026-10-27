import datetime
import json

from confmap.vault_writer import (
    FinalNoteData,
    NoteItem,
    Summary,
    TranscriptLine,
    format_timestamp,
    render_canvas,
    render_markdown,
    sanitize_title,
    write_conference,
)


def make_topics():
    return [
        {
            "id": "t1",
            "title": "Pipeline (v2) [beta]",
            "kind": "process",
            "started_at": 0,
            "nodes": [
                {"id": "a", "label": "Étape A", "emoji": "🅰️", "sources": []},
                {"id": "b", "label": "Étape B", "emoji": "", "sources": []},
            ],
            "edges": [{"from": "a", "to": "b", "label": "puis"}],
        },
        {
            "id": "t2",
            "title": "Histoire",
            "kind": "timeline",
            "started_at": 60,
            "nodes": [{"id": "c", "label": "1999", "emoji": "", "sources": []}],
            "edges": [],
        },
    ]


def make_data(**overrides):
    values = {
        "title": "Ma Conf",
        "speaker": "Ada",
        "date": datetime.date(2026, 10, 27),
        "source_lang": "en",
        "duration_seconds": 52 * 60,
        "audio_path": "/x/audio.wav",
        "summary": Summary(
            overview="Un aperçu.", key_points=["P1", "P2"], open_questions=["Q1"]
        ),
        "topics": make_topics(),
        "notes": [
            NoteItem(ts=70, kind="slide", text="Slide titre"),
            NoteItem(ts=5, kind="note", text="Première note"),
        ],
        "transcript": [
            TranscriptLine(
                t0=0, t1=5, text_original="Hello", text_fr="Bonjour", lang="en"
            ),
            TranscriptLine(
                t0=5, t1=9, text_original="World", text_fr="Monde", lang="en"
            ),
        ],
    }
    values.update(overrides)
    return FinalNoteData(**values)


def test_frontmatter_and_sections():
    markdown = render_markdown(make_data(), "Ma Conf.canvas")
    assert markdown.startswith("---\ntype: conference\n")
    assert 'titre: "Ma Conf"' in markdown
    assert 'duree: "52min"' in markdown
    assert "date: 2026-10-27" in markdown
    assert "tags: [conference]" in markdown
    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Résumé",
        "## Carte",
        "## Mes notes et slides",
        "## Transcription",
    ]
    assert "**Points clés**" in markdown and "- P2" in markdown
    assert "**Questions ouvertes**" in markdown and "- Q1" in markdown
    assert "[[Ma Conf.canvas|carte complète]]" in markdown


def test_yaml_quotes_safely():
    markdown = render_markdown(make_data(title='Il a dit "oui": ok'), "x.canvas")
    assert 'titre: "Il a dit \\"oui\\": ok"' in markdown


def test_no_open_questions_section_when_empty():
    data = make_data(summary=Summary(overview="o", key_points=[]))
    assert "Questions ouvertes" not in render_markdown(data, "x.canvas")


def mermaid_blocks(markdown):
    return [part.split("```")[0] for part in markdown.split("```mermaid")[1:]]


def test_map_section_has_one_flowchart_per_topic_with_nodes():
    markdown = render_markdown(make_data(), "x.canvas")
    assert "[[x.canvas|carte complète]]" in markdown
    assert "### ⚙️ Pipeline (v2) [beta]" in markdown and "### ⏳ Histoire" in markdown
    pipeline, history = mermaid_blocks(markdown)
    assert "flowchart LR" in pipeline
    assert 'n0["🅰️ Étape A"]' in pipeline and 'n1["Étape B"]' in pipeline
    assert 'n0 -->|"puis"| n1' in pipeline
    assert 'n0["1999"]' in history


def test_mermaid_labels_are_escaped():
    topic = {
        "id": "t1",
        "title": "T",
        "kind": "concept",
        "nodes": [
            {"id": "x", "label": 'Dit "oui" #1 <b>', "emoji": ""},
            {"id": "y", "label": "f(x) [a]", "emoji": ""},
        ],
        "edges": [{"from": "x", "to": "y", "label": 'a "b"'}, {"from": "x", "to": "?"}],
    }
    (block,) = mermaid_blocks(render_markdown(make_data(topics=[topic]), "x"))
    assert "flowchart TD" in block
    assert 'n0["Dit #quot;oui#quot; #35;1 #lt;b#gt;"]' in block
    assert 'n1["f(x) [a]"]' in block
    assert 'n0 -->|"a #quot;b#quot;"| n1' in block
    assert block.count("-->") == 1


def test_topic_without_nodes_has_heading_but_no_diagram():
    topic = {"id": "t1", "title": "Vide", "kind": "concept", "nodes": [], "edges": []}
    markdown = render_markdown(make_data(topics=[topic]), "x")
    assert "### 💡 Vide" in markdown and "```mermaid" not in markdown


def test_notes_sorted_and_formatted():
    markdown = render_markdown(make_data(), "x")
    assert markdown.index("- **[00:05]** 📝 Première note") < markdown.index(
        "- **[01:10]** 📷 Slide : Slide titre"
    )


def test_empty_notes_and_topics():
    data = make_data(notes=[], topics=[], transcript=[])
    markdown = render_markdown(data, "x")
    assert "_Aucune_" in markdown
    assert render_canvas(data) == {"nodes": [], "edges": []}


def test_timestamp_formats():
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3600) == "01:00:00"
    assert format_timestamp(3725.9) == "01:02:05"


def test_transcript_paragraph_single_with_original():
    markdown = render_markdown(make_data(), "x")
    assert "**[00:00]** Bonjour Monde" in markdown
    assert "> *Hello World*" in markdown


def test_paragraph_split_on_gap():
    lines = [
        TranscriptLine(t0=0, t1=3, text_original="a", text_fr="A", lang="en"),
        TranscriptLine(t0=8, t1=10, text_original="b", text_fr="B", lang="en"),
    ]
    markdown = render_markdown(make_data(transcript=lines), "x")
    assert "**[00:00]** A" in markdown and "**[00:08]** B" in markdown


def test_paragraph_split_on_duration():
    lines = [
        TranscriptLine(
            t0=i * 10, t1=i * 10 + 10, text_original=f"o{i}", text_fr=f"f{i}", lang="en"
        )
        for i in range(10)
    ]
    markdown = render_markdown(make_data(transcript=lines), "x")
    assert "**[00:00]** f0 f1 f2 f3 f4" in markdown
    assert "**[00:50]** f5 f6 f7 f8 f9" in markdown


def test_french_source_has_no_blockquote():
    markdown = render_markdown(make_data(source_lang="fr"), "x")
    assert "> > *" not in markdown
    assert "Bonjour Monde" in markdown


def test_hour_timestamp_in_transcript():
    lines = [
        TranscriptLine(t0=3700, t1=3705, text_original="o", text_fr="f", lang="en")
    ]
    assert "**[01:01:40]** f" in render_markdown(make_data(transcript=lines), "x")


def assert_canvas_valid(canvas):
    ids = [node["id"] for node in canvas["nodes"]]
    assert len(ids) == len(set(ids))
    for node in canvas["nodes"]:
        assert isinstance(node["id"], str)
        assert all(isinstance(node[key], int) for key in ("x", "y", "width", "height"))
    for edge in canvas["edges"]:
        assert edge["fromNode"] in ids and edge["toNode"] in ids
    json.dumps(canvas)


def contains(group, node):
    return (
        group["x"] <= node["x"]
        and group["y"] <= node["y"]
        and node["x"] + node["width"] <= group["x"] + group["width"]
        and node["y"] + node["height"] <= group["y"] + group["height"]
    )


def test_canvas_fallback_layout():
    canvas = render_canvas(make_data())
    assert_canvas_valid(canvas)
    by_id = {node["id"]: node for node in canvas["nodes"]}
    group1, group2 = by_id["g-t1"], by_id["g-t2"]
    assert group1["type"] == "group" and group1["label"] == "⚙️ Pipeline (v2) [beta]"
    assert contains(group1, by_id["a"]) and contains(group1, by_id["b"])
    assert contains(group2, by_id["c"]) and not contains(group1, by_id["c"])
    # Sujet « process » : niveaux de gauche à droite, nœuds alignés.
    assert by_id["b"]["x"] > by_id["a"]["x"] + by_id["a"]["width"]
    assert (
        by_id["b"]["y"] + by_id["b"]["height"] / 2
        == by_id["a"]["y"] + by_id["a"]["height"] / 2
        or by_id["b"]["y"] == by_id["a"]["y"]
    )
    assert by_id["a"]["text"] == "🅰️ Étape A" and by_id["b"]["text"] == "Étape B"
    assert 120 <= by_id["a"]["width"] <= 260 and by_id["a"]["height"] == 60
    (edge,) = canvas["edges"]
    assert edge["label"] == "puis"
    assert (edge["fromSide"], edge["toSide"]) == ("right", "left")


def test_canvas_vertical_levels_for_concept_topics():
    topic = {
        "id": "t1",
        "title": "T",
        "kind": "concept",
        "nodes": [{"id": i, "label": f"Nœud {i}"} for i in "abcd"],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "a", "to": "c"},
            {"from": "c", "to": "d"},
        ],
    }
    canvas = render_canvas(make_data(topics=[topic]))
    by_id = {n["id"]: n for n in canvas["nodes"]}
    assert by_id["b"]["y"] == by_id["c"]["y"] > by_id["a"]["y"]
    assert by_id["d"]["y"] > by_id["c"]["y"]
    assert all(
        (e["fromSide"], e["toSide"]) == ("bottom", "top") for e in canvas["edges"]
    )


def test_sanitize_title():
    assert sanitize_title('A/B\\C:D*E?F"G<H>I|J#K^L[M]N') == "ABCDEFGHIJKLMN"
    assert sanitize_title("  a    b  ") == "a b"
    assert len(sanitize_title("x" * 200)) == 80
    assert sanitize_title("///") == "Conférence"


def test_write_conference_files(tmp_path):
    markdown_path = write_conference(make_data(title="A/B: test"), tmp_path)
    folder = markdown_path.parent
    assert folder.name == "2026-10-27 AB test"
    assert markdown_path.name == "AB test.md"
    canvas = json.loads((folder / "AB test.canvas").read_text(encoding="utf-8"))
    assert_canvas_valid(canvas)
    assert "[[AB test.canvas|carte complète]]" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_existing_folder_gets_suffix_and_is_untouched(tmp_path):
    first = write_conference(make_data(), tmp_path)
    original_content = first.read_text(encoding="utf-8")
    second = write_conference(make_data(speaker="Autre"), tmp_path)
    third = write_conference(make_data(), tmp_path)
    assert second.parent.name == "2026-10-27 Ma Conf (2)"
    assert third.parent.name == "2026-10-27 Ma Conf (3)"
    assert first.read_text(encoding="utf-8") == original_content


def boxes_overlap(a, b):
    return (
        a["x"] < b["x"] + b["width"]
        and b["x"] < a["x"] + a["width"]
        and a["y"] < b["y"] + b["height"]
        and b["y"] < a["y"] + a["height"]
    )


def test_canvas_boxes_never_overlap():
    from confmap.vault_writer import _topic_node_boxes

    topic = {
        "id": "t1",
        "nodes": [
            {"id": f"n{i}", "label": f"Idée assez longue numéro {i}"} for i in range(6)
        ],
        "edges": [{"from": "n0", "to": f"n{i}"} for i in range(1, 6)],
    }
    boxes = [vars(box) for box in _topic_node_boxes(topic)]
    for i, first in enumerate(boxes):
        for second in boxes[i + 1 :]:
            assert not boxes_overlap(first, second)


def test_all_edges_have_sides_and_no_text_overlap():
    canvas = render_canvas(make_data())
    texts = [n for n in canvas["nodes"] if n["type"] == "text"]
    for i, first in enumerate(texts):
        for second in texts[i + 1 :]:
            assert not boxes_overlap(first, second)
    assert all("fromSide" in e and "toSide" in e for e in canvas["edges"])


def test_transcript_is_collapsible_callout_and_summary_disclaimer():
    lines = [TranscriptLine(t0=0, t1=2, text_original="hi", text_fr="salut", lang="en")]
    markdown = render_markdown(make_data(transcript=lines), "x")
    assert "> [!quote]- Transcription (original | français)" in markdown
    assert "> **[00:00]** salut" in markdown
    assert "\n>\n> > *hi*" in markdown
    assert (
        "*Généré automatiquement par Claude à partir de la transcription — à vérifier.*"
        in markdown
    )
    assert "tags: [conference]" in markdown


def test_long_labels_get_taller_boxes():
    from confmap.vault_writer import NODE_HEIGHT

    topic = {
        "id": "t1",
        "title": "T",
        "kind": "concept",
        "nodes": [
            {"id": "short", "label": "Court"},
            {"id": "long", "label": "Mémoire conversationnelle personnelle (PCM)"},
        ],
        "edges": [],
    }
    by_id = {n["id"]: n for n in render_canvas(make_data(topics=[topic]))["nodes"]}
    assert by_id["short"]["height"] == NODE_HEIGHT
    assert by_id["long"]["height"] > NODE_HEIGHT


def test_canvas_groups_wrap_into_rows_without_overlap():
    from confmap.vault_writer import CANVAS_MAX_ROW_WIDTH

    topics = [
        {
            "id": f"t{i}",
            "title": f"T{i}",
            "kind": "concept",
            "nodes": [{"id": f"t{i}n{j}", "label": f"Nœud {j}"} for j in range(3)],
            "edges": [],
        }
        for i in range(20)
    ]
    canvas = render_canvas(make_data(topics=topics))
    assert_canvas_valid(canvas)
    groups = [n for n in canvas["nodes"] if n["type"] == "group"]
    assert (
        max(g["x"] + g["width"] for g in groups) - min(g["x"] for g in groups)
        <= CANVAS_MAX_ROW_WIDTH
    )
    assert len({g["y"] for g in groups}) > 1
    for i, first in enumerate(groups):
        for second in groups[i + 1 :]:
            assert not boxes_overlap(first, second)
    by_id = {n["id"]: n for n in canvas["nodes"]}
    for group in groups:
        topic_id = group["id"].removeprefix("g-")
        assert all(contains(group, by_id[f"{topic_id}n{j}"]) for j in range(3))


def test_canvas_levels_follow_parent_order() -> None:
    """Les enfants sont rangés comme leurs parents : pas de croisement évitable."""
    from confmap.vault_writer import _topic_node_boxes

    topic = {
        "kind": "comparison",
        "nodes": [{"id": i, "label": i} for i in ["A", "B", "a1", "b1"]],
        "edges": [{"from": "B", "to": "b1"}, {"from": "A", "to": "a1"}],
    }
    boxes = {box.node["id"]: box for box in _topic_node_boxes(topic)}
    assert (boxes["A"].x < boxes["B"].x) == (boxes["a1"].x < boxes["b1"].x)


def test_canvas_comparison_left_to_right() -> None:
    """Comparaison : éléments à gauche, caractéristiques à droite, partagée entre les deux."""
    from confmap.vault_writer import _topic_node_boxes

    topic = {
        "kind": "comparison",
        "nodes": [
            {"id": i, "label": i} for i in ["2018", "2026", "Google", "Huawei", "KG"]
        ],
        "edges": [
            {"from": "2018", "to": "Google"},
            {"from": "2026", "to": "Huawei"},
            {"from": "2018", "to": "KG"},
            {"from": "2026", "to": "KG"},
        ],
    }
    boxes = {box.node["id"]: box for box in _topic_node_boxes(topic)}
    assert (
        boxes["2018"].x
        == boxes["2026"].x
        < boxes["Google"].x
        == boxes["KG"].x
        == boxes["Huawei"].x
    )
    assert boxes["2018"].y < boxes["2026"].y
    assert boxes["Google"].y < boxes["KG"].y < boxes["Huawei"].y
