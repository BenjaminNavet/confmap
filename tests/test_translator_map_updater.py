import pytest

from confmap import map_updater, translator
from confmap.llm import LlmError, LlmResult
from confmap.map_model import describe_map
from confmap.map_updater import ContentItem
from confmap.translator import SegmentToTranslate, TranslatedPair


class StaticLlm:
    def __init__(self, data):
        self.data = data

    async def complete(
        self, model, system, prompt, schema=None, images=None, timeout=60
    ):
        return LlmResult(text="", data=self.data)


SEGMENTS = [
    SegmentToTranslate("s1", "en", "Hello"),
    SegmentToTranslate("s2", "de", "Welt"),
]


def test_translator_prompt():
    prompt = translator.build_prompt(
        "conférence X", [TranslatedPair("Before", "Avant")], SEGMENTS
    )
    assert "CONTEXTE : conférence X" in prompt
    assert "Before" in prompt and "→ Avant" in prompt
    assert "[s1] (en) Hello" in prompt
    assert "[s2] (de) Welt" in prompt
    assert "(aucun)" in translator.build_prompt("", [], SEGMENTS)


async def test_translate_batch_by_id():
    client = StaticLlm(
        {"translations": [{"id": "s2", "fr": "Monde"}, {"id": "s1", "fr": "Bonjour"}]}
    )
    translations, _ = await translator.translate_batch(client, "m", "", [], SEGMENTS)
    assert translations == {"s1": "Bonjour", "s2": "Monde"}


async def test_translate_batch_bracketed_ids():
    client = StaticLlm(
        {
            "translations": [
                {"id": "[s1]", "fr": "Bonjour"},
                {"id": "[s2]", "fr": "Monde"},
            ]
        }
    )
    translations, _ = await translator.translate_batch(client, "m", "", [], SEGMENTS)
    assert translations == {"s1": "Bonjour", "s2": "Monde"}


async def test_translate_batch_falls_back_to_order():
    client = StaticLlm(
        {"translations": [{"id": "1", "fr": "Bonjour"}, {"id": "2", "fr": "Monde"}]}
    )
    translations, _ = await translator.translate_batch(client, "m", "", [], SEGMENTS)
    assert translations == {"s1": "Bonjour", "s2": "Monde"}


async def test_translate_batch_wrong_count_gives_nothing():
    client = StaticLlm({"translations": [{"id": "1", "fr": "Bonjour"}]})
    translations, _ = await translator.translate_batch(client, "m", "", [], SEGMENTS)
    assert translations == {}


def test_map_updater_prompt():
    topics = [
        {
            "id": "t1",
            "title": "Sujet A",
            "kind": "process",
            "started_at": 0,
            "nodes": [{"id": "a", "label": "Boîte A", "emoji": "", "sources": []}],
            "edges": [],
        }
    ]
    covered = "ancien " * 200 + "FIN-COUVERTE"
    items = [
        ContentItem("1", "speech", "Parole traduite"),
        ContentItem("2", "note", "Ma note"),
        ContentItem("3", "slide", "Texte de slide"),
    ]
    prompt = map_updater.build_prompt("ctx", topics, False, covered, items)
    assert "CONTEXTE : ctx" in prompt
    assert describe_map(topics, False) in prompt
    assert "[NOTE] Ma note" in prompt
    assert "[SLIDE] Texte de slide" in prompt
    assert "\nParole traduite\n" in prompt
    covered_part = prompt.split("COUVRE DÉJÀ (contexte seulement) : ")[1].split("\n\n")[
        0
    ]
    assert "FIN-COUVERTE" in covered_part
    assert len(covered_part) <= map_updater.COVERED_TAIL_CHARS + 10


async def test_request_update_valid():
    client = StaticLlm({"add": {"nodes": [{"id": "a", "label": "X"}], "edges": []}})
    update, _ = await map_updater.request_update(
        client, "m", "", [], False, "", [ContentItem("1", "speech", "t")]
    )
    assert update.add.nodes[0].label == "X"


async def test_request_update_invalid_data_raises():
    client = StaticLlm({"add": "pas un objet"})
    with pytest.raises(LlmError):
        await map_updater.request_update(
            client, "m", "", [], False, "", [ContentItem("1", "speech", "t")]
        )
