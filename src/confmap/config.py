"""Chargement de la configuration (`config.toml`) en modèles Pydantic."""

from __future__ import annotations

import platform
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


# Whisper (direct, secours, finalisation) : mlx sur Mac Apple Silicon, faster-whisper ailleurs.
if sys.platform == "darwin" and platform.machine() == "arm64":
    _WHISPER_DEFAULTS = (
        "mlx-community/whisper-large-v3-turbo",
        "mlx-community/whisper-small-mlx",
        "mlx-community/whisper-large-v3-mlx",
    )
else:
    _WHISPER_DEFAULTS = ("large-v3-turbo", "small", "large-v3")


class ModelsConfig(BaseModel):
    """Modèles utilisés par chaque étape."""

    translate: str = "claude-haiku-5-5"
    map: str = "claude-sonnet-5-5"
    vision: str = "claude-sonnet-5-5"
    summary: str = "claude-sonnet-5-5"
    whisper_live: str = _WHISPER_DEFAULTS[0]
    whisper_fallback: str = _WHISPER_DEFAULTS[1]
    whisper_final: str = _WHISPER_DEFAULTS[2]


class MapConfig(BaseModel):
    """Rythme et taille de la carte des idées."""

    interval_seconds: float = 20
    min_gap_seconds: float = 8
    max_nodes_per_topic: int = 8
    max_topic_seconds: float = 300


class PathsConfig(BaseModel):
    """Emplacements sur disque."""

    # Sans cela, Pydantic ne passe pas les valeurs par défaut au validateur : « ~ » resterait littéral.
    model_config = ConfigDict(validate_default=True)

    # Dossier des notes ; absent : choix fait dans l'interface, ou vault Obsidian par défaut.
    vault: Path | None = None
    sessions: Path = PROJECT_ROOT / "sessions"
    # Choix de l'utilisateur fait dans l'interface (dossier des notes).
    preferences: Path = PROJECT_ROOT / "preferences.json"

    @field_validator("vault", "sessions", "preferences", mode="after")
    @classmethod
    def _expand_user(cls, path: Path | None) -> Path | None:
        return path.expanduser() if path is not None else None


class LlmConfig(BaseModel):
    """Backend des appels à Claude.

    `auto` : la CLI Claude Code si `claude` est dans le PATH, sinon OpenRouter
    si `OPENROUTER_API_KEY` est définie.
    """

    backend: Literal["auto", "claude", "openrouter"] = "auto"


class ServerConfig(BaseModel):
    """Serveur web."""

    host: str = "0.0.0.0"
    port: int = 8010


class Settings(BaseModel):
    """Configuration complète de l'application."""

    models: ModelsConfig = ModelsConfig()
    map: MapConfig = MapConfig()
    paths: PathsConfig = PathsConfig()
    llm: LlmConfig = LlmConfig()
    server: ServerConfig = ServerConfig()


def load_settings(config_path: Path | None = None) -> Settings:
    """Lit `config.toml` ; les valeurs absentes prennent leur valeur par défaut.

    Args:
        config_path: Chemin du fichier ; par défaut `config.toml` à la racine du projet.

    Returns:
        La configuration validée.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Settings()
    with path.open("rb") as config_file:
        return Settings.model_validate(tomllib.load(config_file))
