"""Modèle utilisé à chaque étape, et catalogue des modèles avec leurs prix.

Ordre de priorité par étape : `[models]` dans `config.toml`, puis le choix fait
dans l'interface (`preferences.json`, par backend), puis le défaut du backend.
Le coût affiché vient de chaque réponse (CLI Claude ou OpenRouter) : il suit
donc le modèle réellement utilisé. Le catalogue sert à choisir en voyant les prix.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx

from confmap.config import Settings
from confmap.openrouter import DEFAULT_MODELS
from confmap.preferences import load_preferences, update_preferences

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CATALOG_TTL_SECONDS = 3600

# Étapes réglables, avec leur libellé dans l'interface.
STEPS = {
    "translate": "Traduction",
    "map": "Carte des idées",
    "vision": "Photos de slides",
    "summary": "Résumé final",
}

Source = Literal["config", "choice", "default"]


def claude_cli_id(openrouter_id: str) -> str:
    """`anthropic/claude-sonnet-5.5` devient `claude-sonnet-5-5` (nom pour la CLI)."""
    return openrouter_id.removeprefix("anthropic/").replace(".", "-")


def parse_catalog(payload: dict[str, Any], backend: str) -> list[dict[str, Any]]:
    """Modèles utilisables (sortie structurée), prix en $ par million de tokens.

    Avec la CLI Claude, seuls les modèles Claude sont gardés, sous leur nom CLI.
    """
    models = []
    for item in payload.get("data") or []:
        model_id = str(item.get("id") or "")
        if ":" in model_id or "structured_outputs" not in (
            item.get("supported_parameters") or []
        ):
            continue
        if backend == "claude":
            if not model_id.startswith("anthropic/claude"):
                continue
            model_id = claude_cli_id(model_id)
        pricing = item.get("pricing") or {}
        try:
            input_price = float(pricing.get("prompt") or 0) * 1e6
            output_price = float(pricing.get("completion") or 0) * 1e6
        except ValueError:
            continue
        if input_price < 0 or output_price < 0:  # prix variable (routeurs)
            continue
        models.append(
            {
                "id": model_id,
                "name": str(item.get("name") or model_id),
                "input_price": round(input_price, 4),
                "output_price": round(output_price, 4),
                "images": "image"
                in ((item.get("architecture") or {}).get("input_modalities") or []),
            }
        )
    return sorted(models, key=lambda model: model["id"])


class ModelChoices:
    """Modèles par étape pour un backend, modifiables depuis l'interface.

    Args:
        settings: Configuration partagée ; `settings.models` est modifié en place,
            donc un changement vaut dès l'appel suivant.
        backend: `claude` ou `openrouter`.
        transport: Transport httpx (tests).
    """

    def __init__(
        self,
        settings: Settings,
        backend: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Applique les choix enregistrés et les défauts du backend."""
        self.settings = settings
        self.backend = backend
        self._transport = transport
        # Lu avant toute modification : une affectation ajoute le champ à cet ensemble.
        self.configured = set(settings.models.model_fields_set) & set(STEPS)
        self.defaults = (
            dict(DEFAULT_MODELS)
            if backend == "openrouter"
            else {step: getattr(settings.models, step) for step in STEPS}
        )
        self._catalog: list[dict[str, Any]] = []
        self._catalog_time = 0.0
        for step in STEPS:
            if step not in self.configured:
                setattr(
                    settings.models,
                    step,
                    self._chosen().get(step) or self.defaults[step],
                )

    def _chosen(self) -> dict[str, str]:
        choices = load_preferences(self.settings.paths.preferences).get("models") or {}
        return dict(choices.get(self.backend) or {})

    def source(self, step: str) -> Source:
        """D'où vient le modèle de l'étape."""
        if step in self.configured:
            return "config"
        return "choice" if step in self._chosen() else "default"

    def choose(self, step: str, model: str) -> None:
        """Enregistre le modèle d'une étape ; une valeur vide revient au défaut.

        Raises:
            KeyError: Étape inconnue.
            PermissionError: Modèle fixé dans `config.toml`.
        """
        if step not in STEPS:
            raise KeyError(step)
        if step in self.configured:
            raise PermissionError(f"modèle fixé par [models] {step} dans config.toml")
        choices = load_preferences(self.settings.paths.preferences).get("models") or {}
        backend_choices = dict(choices.get(self.backend) or {})
        model = model.strip()
        if model:
            backend_choices[step] = model
        else:
            backend_choices.pop(step, None)
        choices[self.backend] = backend_choices
        update_preferences(self.settings.paths.preferences, models=choices)
        setattr(self.settings.models, step, model or self.defaults[step])

    async def catalog(self) -> list[dict[str, Any]]:
        """Catalogue OpenRouter (public, sans clé), gardé en mémoire une heure.

        Retourne [] si OpenRouter est injoignable : le choix reste possible à la main.
        """
        if (
            self._catalog
            and time.monotonic() - self._catalog_time < CATALOG_TTL_SECONDS
        ):
            return self._catalog
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=10) as http:
                response = await http.get(CATALOG_URL)
                response.raise_for_status()
                self._catalog = parse_catalog(response.json(), self.backend)
                self._catalog_time = time.monotonic()
        except (httpx.HTTPError, ValueError):
            return self._catalog
        return self._catalog

    async def describe(self) -> dict[str, Any]:
        """État pour l'interface : modèle et origine par étape, plus le catalogue."""
        return {
            "backend": self.backend,
            "steps": [
                {
                    "step": step,
                    "label": label,
                    "model": getattr(self.settings.models, step),
                    "source": self.source(step),
                    "default": self.defaults[step],
                    "needs_images": step == "vision",
                }
                for step, label in STEPS.items()
            ],
            "catalog": await self.catalog(),
        }
