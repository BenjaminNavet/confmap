"""Appels LLM via l'API OpenRouter (clé `OPENROUTER_API_KEY`), voir ADR 0004.

Alternative à la CLI Claude Code pour qui n'a pas d'abonnement : même interface
`LlmClient`, sortie structurée par `response_format` (JSON Schema), images en
`data:` URL et coût réel lu dans `usage.cost`.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any

import httpx

from confmap.llm import (
    ImageInput,
    LlmError,
    LlmResult,
    LlmTimeout,
    NetworkUnavailable,
    _strip_code_fence,
)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_VARIABLE = "OPENROUTER_API_KEY"
_ANTHROPIC_VERSION = re.compile(r"-(\d+)-(\d+)$")

# Modèles par défaut avec OpenRouter : DeepSeek Pro, sauf pour les photos de
# slides (DeepSeek Pro ne lit pas les images).
DEFAULT_MODELS = {
    "translate": "deepseek/deepseek-v4-pro",
    "map": "deepseek/deepseek-v4-pro",
    "summary": "deepseek/deepseek-v4-pro",
    "vision": "deepseek/deepseek-v4.1-flash",
}


def openrouter_model_id(model: str) -> str:
    """Traduit un nom de modèle Anthropic en identifiant OpenRouter.

    `claude-sonnet-5-5` devient `anthropic/claude-sonnet-5.5` ; un identifiant
    qui contient déjà `/` (par exemple `openai/gpt-5`) est gardé tel quel.
    """
    if "/" in model:
        return model
    return "anthropic/" + _ANTHROPIC_VERSION.sub(r"-\1.\2", model)


class OpenRouterClient:
    """Backend qui appelle l'API OpenRouter (facturation à l'usage).

    Args:
        api_key: Clé OpenRouter ; par défaut la variable `OPENROUTER_API_KEY`.
        transport: Transport httpx (tests).
    """

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Vérifie que la clé est disponible."""
        api_key = api_key or os.environ.get(API_KEY_VARIABLE)
        if not api_key:
            raise LlmError(
                f"variable {API_KEY_VARIABLE} absente (fichier .env ou environnement)"
            )
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Title": "confmap",
        }
        self._transport = transport

    @staticmethod
    def build_payload(
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None,
        images: list[ImageInput] | None,
    ) -> dict[str, Any]:
        """Corps de la requête `chat/completions`."""
        content: str | list[dict[str, Any]] = prompt
        if images:
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.media_type};base64,"
                        + base64.b64encode(image.data).decode("ascii")
                    },
                }
                for image in images
            ] + [{"type": "text", "text": prompt}]
        payload: dict[str, Any] = {
            "model": openrouter_model_id(model),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "usage": {"include": True},
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": schema},
            }
            # Seuls les fournisseurs qui respectent la sortie structurée sont retenus.
            payload["provider"] = {"require_parameters": True}
        return payload

    async def complete(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        images: list[ImageInput] | None = None,
        timeout: float = 60.0,
    ) -> LlmResult:
        """Envoie la requête et interprète la réponse."""
        payload = self.build_payload(model, system, prompt, schema, images)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=timeout
            ) as http:
                response = await http.post(API_URL, json=payload, headers=self._headers)
        except httpx.TimeoutException as error:
            raise LlmTimeout(f"pas de réponse en {timeout:.0f} s") from error
        except httpx.TransportError as error:
            raise NetworkUnavailable(f"OpenRouter injoignable : {error}") from error
        duration_ms = int((time.monotonic() - started) * 1000)
        return parse_response(response, schema is not None, duration_ms)


def parse_response(
    response: httpx.Response, expect_json: bool, duration_ms: int = 0
) -> LlmResult:
    """Interprète une réponse OpenRouter (erreurs, texte, JSON, coût)."""
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    if response.status_code >= 400 or error:
        message = (
            str(error.get("message")) if isinstance(error, dict) else response.text
        )[:500]
        # 408, 429 et 5xx : surcharge ou panne passagère, l'appel peut être retenté.
        if response.status_code in (408, 429) or response.status_code >= 500:
            raise NetworkUnavailable(f"OpenRouter {response.status_code} : {message}")
        raise LlmError(f"OpenRouter {response.status_code} : {message}")
    choices = body.get("choices") or []
    if not choices:
        raise LlmError("réponse OpenRouter sans contenu")
    text = str((choices[0].get("message") or {}).get("content") or "")
    usage = body.get("usage") or {}
    result = LlmResult(
        text=text,
        cost_usd=float(usage.get("cost") or 0.0),
        duration_ms=duration_ms,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        raw=body,
    )
    if expect_json:
        try:
            data = json.loads(_strip_code_fence(text))
        except json.JSONDecodeError as error:
            raise LlmError(f"JSON attendu, reçu : {text[:300]}") from error
        if not isinstance(data, dict):
            raise LlmError("la sortie structurée n'est pas un objet JSON")
        result.data = data
    return result
