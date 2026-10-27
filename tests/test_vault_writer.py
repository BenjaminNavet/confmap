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
    assert "![[Ma Conf.canvas]]" in markdown


def test_yaml_quotes_safely():
    markdown = render_markdown(make_data(title='Il a dit "oui": ok'), "x.canvas")
    assert 'titre: "Il a dit \\"oui\\": ok"' in markdown


def test_no_open_questions_section_when_empty():
    data = make_data(summary=Summary(overview="o", key_points=[]))
    assert "Questions ouvertes" not in render_markdown(data, "x.canvas")


def test_mermaid_escaping_and_icons():
    markdown = render_markdown(make_data(title="Conf (spéciale)"), "x.canvas")
    block = markdown.split("```mermaid")[1].split("```")[0]
    assert "root((Conf （spéciale）))" in block
    assert "⚙️ Pipeline （v2） ［beta］" in block
    assert "⏳ Histoire" in block
    assert "(v2)" not in block


def test_mermaid_max_25_topics():
    topics = [
        {
            "id": f"t{i}",
            "title": f"T{i}",
            "kind": "concept",
            "started_at": 0,
            "nodes": [],
            "edges": [],
        }
        for i in range(30)
    ]
    block = (
        render_markdown(make_data(topics=topics), "x")
        .split("```mermaid")[1]
        .split("```")[0]
    )
    assert block.count("💡") == 25


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
    assert "> *" not in markdown
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
    assert by_id["b"]["y"] - by_id["a"]["y"] == 100
    assert by_id["c"]["x"] - by_id["a"]["x"] == 400
    assert by_id["a"]["text"] == "🅰️ Étape A" and by_id["b"]["text"] == "Étape B"
    assert 120 <= by_id["a"]["width"] <= 260 and by_id["a"]["height"] == 60
    (edge,) = canvas["edges"]
    assert edge["label"] == "puis" and "fromSide" not in edge


def test_canvas_uses_positions():
    from confmap.vault_writer import POSITION_SCALE_X, POSITION_SCALE_Y

    positions = {"a": (500.0, 300.0), "b": (900.5, 700.0), "c": (0.0, 0.0)}
    canvas = render_canvas(make_data(positions=positions))
    assert_canvas_valid(canvas)
    by_id = {node["id"]: node for node in canvas["nodes"]}
    node_a = by_id["a"]
    # Les positions de l'app sont écartées pour les boîtes plus grandes du canvas.
    assert node_a["x"] + node_a["width"] / 2 == 500 * POSITION_SCALE_X
    assert node_a["y"] + node_a["height"] / 2 == 300 * POSITION_SCALE_Y
    assert contains(by_id["g-t1"], by_id["a"]) and contains(by_id["g-t1"], by_id["b"])


def test_canvas_partial_positions_fall_back():
    canvas = render_canvas(make_data(positions={"a": (5000.0, 5000.0)}))
    by_id = {node["id"]: node for node in canvas["nodes"]}
    assert by_id["a"]["x"] < 1000


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
    assert "![[AB test.canvas]]" in markdown_path.read_text(encoding="utf-8")


def test_existing_folder_gets_suffix_and_is_untouched(tmp_path):
    first = write_conference(make_data(), tmp_path)
    original_content = first.read_text(encoding="utf-8")
    second = write_conference(make_data(speaker="Autre"), tmp_path)
    third = write_conference(make_data(), tmp_path)
    assert second.parent.name == "2026-10-27 Ma Conf (2)"
    assert third.parent.name == "2026-10-27 Ma Conf (3)"
    assert first.read_text(encoding="utf-8") == original_content


def test_canvas_boxes_never_overlap_even_with_tight_app_positions():
    from confmap.vault_writer import NODE_HEIGHT, _topic_node_boxes

    topic = {"id": "t1", "nodes": [{"id": f"n{i}", "label": f"Idée assez longue numéro {i}"} for i in range(6)]}
    tight = {f"n{i}": (i * 20.0, (i % 2) * 10.0) for i in range(6)}
    boxes = _topic_node_boxes(topic, 0, tight)
    for i, (_, _, x1, y1, w1) in enumerate(boxes):
        for _, _, x2, y2, w2 in boxes[i + 1 :]:
            assert not (x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + NODE_HEIGHT and y2 < y1 + NODE_HEIGHT)
