import json

import httpx
import pytest

from confmap.llm import ImageInput, LlmError, LlmTimeout, NetworkUnavailable
from confmap.openrouter import OpenRouterClient, openrouter_model_id


def make_client(handler):
    return OpenRouterClient(api_key="k", transport=httpx.MockTransport(handler))


def ok_body(content, cost=0.01):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
    }


def test_model_ids():
    assert openrouter_model_id("claude-sonnet-5-5") == "anthropic/claude-sonnet-5.5"
    assert openrouter_model_id("claude-haiku-5-5") == "anthropic/claude-haiku-5.5"
    assert openrouter_model_id("openai/gpt-5") == "openai/gpt-5"


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LlmError):
        OpenRouterClient()


async def test_structured_output_and_cost():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=ok_body('```json\n{"a": 1}\n```', cost=0.25))

    schema = {"type": "object"}
    result = await make_client(handler).complete(
        "claude-sonnet-5-5", "sys", "hi", schema
    )
    assert result.data == {"a": 1}
    assert result.cost_usd == 0.25
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    body = seen["body"]
    assert seen["auth"] == "Bearer k"
    assert body["model"] == "anthropic/claude-sonnet-5.5"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["provider"] == {"require_parameters": True}


async def test_images_are_data_urls():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body("texte"))

    result = await make_client(handler).complete(
        "m", "sys", "décris", images=[ImageInput(b"\x89PNG", "image/png")]
    )
    assert result.text == "texte" and result.data is None
    content = seen["body"]["messages"][1]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[-1] == {"type": "text", "text": "décris"}


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, NetworkUnavailable), (503, NetworkUnavailable), (400, LlmError)],
)
async def test_http_errors(status, error):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "non"}})

    with pytest.raises(error) as raised:
        await make_client(handler).complete("m", "s", "p")
    assert status != 400 or not isinstance(raised.value, NetworkUnavailable)


async def test_network_errors():
    def refuse(request):
        raise httpx.ConnectError("refusé")

    def slow(request):
        raise httpx.ReadTimeout("lent")

    with pytest.raises(NetworkUnavailable):
        await make_client(refuse).complete("m", "s", "p")
    with pytest.raises(LlmTimeout):
        await make_client(slow).complete("m", "s", "p")


async def test_invalid_json():
    def handler(request):
        return httpx.Response(200, json=ok_body("pas du json"))

    with pytest.raises(LlmError):
        await make_client(handler).complete("m", "s", "p", schema={"type": "object"})


def test_backend_selection(monkeypatch):
    from confmap import cli
    from confmap.llm import ClaudeCliClient

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LlmError):
        cli.resolve_llm_backend("auto")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert cli.resolve_llm_backend("auto") == "openrouter"
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    assert cli.resolve_llm_backend("auto") == "claude"
    assert cli.resolve_llm_backend("openrouter") == "openrouter"
    assert isinstance(cli.create_llm_client("claude"), ClaudeCliClient)
    assert isinstance(cli.create_llm_client("openrouter"), OpenRouterClient)
