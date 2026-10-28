import httpx
import pytest

from confmap.config import Settings
from confmap.model_choice import ModelChoices, claude_cli_id, parse_catalog
from confmap.preferences import load_preferences

CATALOG = {
    "data": [
        {
            "id": "deepseek/deepseek-v4-pro",
            "name": "DeepSeek V4 Pro",
            "pricing": {"prompt": "0.00000096", "completion": "0.00000191"},
            "supported_parameters": ["structured_outputs"],
            "architecture": {"input_modalities": ["text"]},
        },
        {
            "id": "anthropic/claude-sonnet-5.5",
            "name": "Claude Sonnet 5.5",
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            "supported_parameters": ["structured_outputs"],
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "anthropic/claude-sonnet-5.5:batch",
            "supported_parameters": ["structured_outputs"],
        },
        {"id": "old/no-json", "supported_parameters": [], "pricing": {}},
        {
            "id": "openrouter/auto",
            "supported_parameters": ["structured_outputs"],
            "pricing": {"prompt": "-1", "completion": "-1"},
        },
    ]
}


def make_settings(tmp_path, models=None):
    settings = Settings.model_validate({"models": models or {}})
    settings.paths.preferences = tmp_path / "preferences.json"
    return settings


def test_parse_catalog_prices_and_filters():
    models = parse_catalog(CATALOG, "openrouter")
    assert [m["id"] for m in models] == [
        "anthropic/claude-sonnet-5.5",
        "deepseek/deepseek-v4-pro",
    ]
    deepseek = models[1]
    assert (deepseek["input_price"], deepseek["output_price"]) == (0.96, 1.91)
    assert models[0]["images"] and not deepseek["images"]


def test_claude_catalog_uses_cli_ids():
    assert claude_cli_id("anthropic/claude-haiku-5.5") == "claude-haiku-5-5"
    assert [m["id"] for m in parse_catalog(CATALOG, "claude")] == ["claude-sonnet-5-5"]


def test_openrouter_defaults_to_deepseek(tmp_path):
    settings = make_settings(tmp_path, {"summary": "anthropic/claude-sonnet-5.5"})
    choices = ModelChoices(settings, "openrouter")
    assert settings.models.map == "deepseek/deepseek-v4-pro"
    assert settings.models.translate == "deepseek/deepseek-v4-pro"
    assert settings.models.vision == "deepseek/deepseek-v4.1-flash"
    assert settings.models.summary == "anthropic/claude-sonnet-5.5"
    assert choices.source("summary") == "config" and choices.source("map") == "default"


def test_claude_keeps_its_defaults(tmp_path):
    settings = make_settings(tmp_path)
    ModelChoices(settings, "claude")
    assert settings.models.map == "claude-sonnet-5-5"


def test_choice_is_live_and_persisted_per_backend(tmp_path):
    settings = make_settings(tmp_path)
    choices = ModelChoices(settings, "openrouter")
    choices.choose("map", "openai/gpt-5")
    assert settings.models.map == "openai/gpt-5"
    assert choices.source("map") == "choice"
    assert load_preferences(settings.paths.preferences)["models"] == {
        "openrouter": {"map": "openai/gpt-5"}
    }

    reloaded = make_settings(tmp_path)
    ModelChoices(reloaded, "openrouter")
    assert reloaded.models.map == "openai/gpt-5"
    other = make_settings(tmp_path)
    ModelChoices(other, "claude")
    assert other.models.map == "claude-sonnet-5-5"

    choices.choose("map", "")
    assert settings.models.map == "deepseek/deepseek-v4-pro"
    assert choices.source("map") == "default"


def test_choose_rejects(tmp_path):
    choices = ModelChoices(make_settings(tmp_path, {"map": "x/y"}), "openrouter")
    with pytest.raises(KeyError):
        choices.choose("nope", "a/b")
    with pytest.raises(PermissionError):
        choices.choose("map", "a/b")


async def test_catalog_cached_and_offline(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json=CATALOG)

    choices = ModelChoices(
        make_settings(tmp_path), "openrouter", httpx.MockTransport(handler)
    )
    state = await choices.describe()
    await choices.catalog()
    assert len(calls) == 1 and len(state["catalog"]) == 2
    assert [s["step"] for s in state["steps"]] == [
        "translate",
        "map",
        "vision",
        "summary",
    ]

    def offline(request):
        raise httpx.ConnectError("hors ligne")

    offline_choices = ModelChoices(
        make_settings(tmp_path), "openrouter", httpx.MockTransport(offline)
    )
    assert await offline_choices.catalog() == []
