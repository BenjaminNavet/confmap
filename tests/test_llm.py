import base64
import json

import pytest

from confmap import llm
from confmap.llm import (
    ClaudeCliClient,
    ImageInput,
    LlmError,
    NetworkUnavailable,
    parse_cli_output,
)


def result_line(**fields):
    return {"type": "result", "is_error": False, **fields}


def test_structured_output():
    stdout = json.dumps(
        result_line(
            result="",
            structured_output={"a": 1},
            total_cost_usd=0.25,
            duration_ms=1200,
        )
    )
    parsed = parse_cli_output(stdout, "", expect_json=True)
    assert parsed.data == {"a": 1}
    assert parsed.cost_usd == 0.25
    assert parsed.duration_ms == 1200


def test_json_in_code_fence():
    text = '```json\n{"b": 2}\n```'
    parsed = parse_cli_output(json.dumps(result_line(result=text)), "", True)
    assert parsed.data == {"b": 2}


def test_invalid_json_text_raises():
    with pytest.raises(LlmError):
        parse_cli_output(json.dumps(result_line(result="pas du json")), "", True)


def test_text_without_schema():
    parsed = parse_cli_output(json.dumps(result_line(result="bonjour")), "", False)
    assert parsed.text == "bonjour"
    assert parsed.data is None


def test_stream_json_last_result_wins():
    lines = [
        {"type": "system", "subtype": "init"},
        result_line(result="premier"),
        {"type": "assistant", "message": {}},
        result_line(result="dernier", total_cost_usd=1.5),
    ]
    stdout = "\n".join(json.dumps(line) for line in lines)
    parsed = parse_cli_output(stdout, "", False)
    assert parsed.text == "dernier"
    assert parsed.cost_usd == 1.5


def test_json_array_output():
    stdout = json.dumps([{"type": "system"}, result_line(result="dans liste")])
    assert parse_cli_output(stdout, "", False).text == "dans liste"


def test_error_network_vs_other():
    network = json.dumps(
        {"type": "result", "is_error": True, "result": "API Error: Connection refused"}
    )
    with pytest.raises(NetworkUnavailable):
        parse_cli_output(network, "", False)
    other = json.dumps({"type": "result", "is_error": True, "result": "rate limited"})
    with pytest.raises(LlmError) as excinfo:
        parse_cli_output(other, "", False)
    assert not isinstance(excinfo.value, NetworkUnavailable)


def test_empty_stdout_enotfound_is_network():
    with pytest.raises(NetworkUnavailable):
        parse_cli_output("", "getaddrinfo ENOTFOUND api.anthropic.com", False)


def test_empty_stdout_other_is_llm_error():
    with pytest.raises(LlmError) as excinfo:
        parse_cli_output("", "boom", False)
    assert not isinstance(excinfo.value, NetworkUnavailable)


def test_usage_sums_cache_tokens():
    usage = {
        "input_tokens": 10,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 1000,
        "output_tokens": 7,
    }
    parsed = parse_cli_output(
        json.dumps(result_line(result="x", usage=usage)), "", False
    )
    assert parsed.input_tokens == 1110
    assert parsed.output_tokens == 7


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: f"/bin/{name}")
    return ClaudeCliClient()


def test_build_args_schema(client):
    without = client.build_args("m", "sys", None, with_images=False)
    assert "--json-schema" not in without
    assert without[without.index("--output-format") + 1] == "json"
    assert "--input-format" not in without

    schema = {"type": "object"}
    with_schema = client.build_args("m", "sys", schema, with_images=False)
    assert with_schema[with_schema.index("--json-schema") + 1] == json.dumps(schema)
    assert with_schema[with_schema.index("--model") + 1] == "m"
    assert with_schema[with_schema.index("--system-prompt") + 1] == "sys"


def test_build_args_images_use_stream_json(client):
    args = client.build_args("m", "sys", None, with_images=True)
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert "--verbose" in args


def test_constructor_requires_cli(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with pytest.raises(LlmError):
        ClaudeCliClient()


def test_build_stdin_text_and_image(client):
    assert client.build_stdin("bonjour", None) == b"bonjour"
    raw = b"\x89PNGdata"
    stdin = client.build_stdin("décris", [ImageInput(raw, "image/png")])
    assert stdin.endswith(b"\n")
    assert stdin.count(b"\n") == 1
    message = json.loads(stdin)
    content = message["message"]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert base64.b64decode(content[0]["source"]["data"]) == raw
    assert content[-1] == {"type": "text", "text": "décris"}
