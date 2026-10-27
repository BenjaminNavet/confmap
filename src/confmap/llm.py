"""Appels LLM via la CLI Claude Code (`claude -p`), voir ADR 0001.

Chaque appel lance un sous-processus sans outils ni configuration utilisateur,
avec un prompt système dédié, et récupère texte ou JSON structuré plus le coût
équivalent API (`total_cost_usd`).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

NETWORK_HINTS = (
    "connection",
    "network",
    "enotfound",
    "econnrefused",
    "etimedout",
    "fetch failed",
    "socket",
    "dns",
)


class LlmError(RuntimeError):
    """Échec d'un appel LLM (réponse invalide, erreur du modèle...)."""


class NetworkUnavailable(LlmError):
    """Le service n'est pas joignable : l'appel peut être retenté plus tard."""


class LlmTimeout(NetworkUnavailable):
    """Pas de réponse dans le délai : réseau coupé, ou requête trop longue pour ce délai."""


@dataclass
class ImageInput:
    """Image envoyée au modèle."""

    data: bytes
    media_type: str = "image/jpeg"


@dataclass
class LlmResult:
    """Réponse d'un appel LLM."""

    text: str
    data: dict[str, Any] | None = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LlmClient(Protocol):
    """Interface commune des backends LLM (CLI, faux client de test...)."""

    async def complete(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        images: list[ImageInput] | None = None,
        timeout: float = 60.0,
    ) -> LlmResult:
        """Envoie un prompt et retourne la réponse (JSON validé si `schema`)."""
        ...


class ClaudeCliClient:
    """Backend qui utilise l'abonnement Claude Code via `claude -p`."""

    def __init__(self, executable: str = "claude") -> None:
        """Vérifie que la CLI est disponible."""
        resolved = shutil.which(executable)
        if resolved is None:
            raise LlmError(f"commande '{executable}' introuvable dans le PATH")
        self.executable = resolved
        # Dossier neutre : aucun CLAUDE.md de projet n'est chargé.
        self._workdir = tempfile.mkdtemp(prefix="confmap-llm-")

    def build_args(
        self, model: str, system: str, schema: dict[str, Any] | None, with_images: bool
    ) -> list[str]:
        """Arguments de la ligne de commande pour un appel."""
        args = [
            self.executable,
            "-p",
            "--model",
            model,
            "--output-format",
            "stream-json" if with_images else "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--system-prompt",
            system,
        ]
        if schema is not None:
            args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
        if with_images:
            args += ["--input-format", "stream-json", "--verbose"]
        return args

    @staticmethod
    def build_stdin(prompt: str, images: list[ImageInput] | None) -> bytes:
        """Contenu envoyé sur l'entrée standard (texte brut ou message stream-json)."""
        if not images:
            return prompt.encode("utf-8")
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append({"type": "text", "text": prompt})
        message = {"type": "user", "message": {"role": "user", "content": content}}
        return (json.dumps(message) + "\n").encode("utf-8")

    async def complete(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        images: list[ImageInput] | None = None,
        timeout: float = 60.0,
    ) -> LlmResult:
        """Lance `claude -p` et interprète sa sortie JSON."""
        args = self.build_args(model, system, schema, bool(images))
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workdir,
            )
        except OSError as error:
            raise LlmError(f"impossible de lancer claude : {error}") from error
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(self.build_stdin(prompt, images)), timeout
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise LlmTimeout(f"pas de réponse en {timeout:.0f} s") from error
        return parse_cli_output(
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
            schema is not None,
        )


def parse_cli_output(stdout: str, stderr: str, expect_json: bool) -> LlmResult:
    """Interprète la sortie de `claude -p --output-format json`.

    Avec `--input-format stream-json --verbose`, la sortie est une liste
    d'objets dont le dernier `type == "result"` porte la réponse.
    """
    payload = _find_result_payload(stdout)
    if payload is None:
        message = (stderr or stdout).strip()[:500]
        if any(hint in message.lower() for hint in NETWORK_HINTS):
            raise NetworkUnavailable(message)
        raise LlmError(f"sortie illisible de claude : {message}")
    text = str(payload.get("result") or "")
    if payload.get("is_error"):
        if any(hint in text.lower() for hint in NETWORK_HINTS):
            raise NetworkUnavailable(text[:500])
        raise LlmError(text[:500] or "erreur inconnue")
    usage = payload.get("usage") or {}
    result = LlmResult(
        text=text,
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
        duration_ms=int(payload.get("duration_ms") or 0),
        input_tokens=int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        raw=payload,
    )
    if expect_json:
        structured = payload.get("structured_output")
        if structured is None:
            try:
                structured = json.loads(_strip_code_fence(text))
            except json.JSONDecodeError as error:
                raise LlmError(f"JSON attendu, reçu : {text[:300]}") from error
        if not isinstance(structured, dict):
            raise LlmError("la sortie structurée n'est pas un objet JSON")
        result.data = structured
    return result


def _find_result_payload(stdout: str) -> dict[str, Any] | None:
    stdout = stdout.strip()
    if not stdout:
        return None
    candidates: list[Any] = []
    try:
        parsed = json.loads(stdout)
        candidates = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        for line in stdout.splitlines():
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    for item in reversed(candidates):
        if isinstance(item, dict) and item.get("type") == "result":
            return item
    return None


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.removesuffix("```").strip()
    return text
