"""Chargement de la configuration (`config.toml`) en modèles Pydantic."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


class ModelsConfig(BaseModel):
    """Modèles utilisés par chaque étape."""

    translate: str = "claude-haiku-5-5"
    map: str = "claude-sonnet-5-5"
    vision: str = "claude-sonnet-5-5"
    summary: str = "claude-sonnet-5-5"
    whisper_live: str = "mlx-community/whisper-large-v3-turbo"
    whisper_fallback: str = "mlx-community/whisper-small-mlx"
    whisper_final: str = "mlx-community/whisper-large-v3-mlx"


class MapConfig(BaseModel):
    """Rythme et taille de la carte des idées."""

    interval_seconds: float = 20
    min_gap_seconds: float = 8
    max_nodes_per_topic: int = 10
    max_topic_seconds: float = 300


class PathsConfig(BaseModel):
    """Emplacements sur disque."""

    # Sans cela, Pydantic ne passe pas les valeurs par défaut au validateur : « ~ » resterait littéral.
    model_config = ConfigDict(validate_default=True)

    vault: Path = Path("~/Documents/Obsidian Vault/Conferences")
    sessions: Path = PROJECT_ROOT / "sessions"

    @field_validator("vault", "sessions", mode="after")
    @classmethod
    def _expand_user(cls, path: Path) -> Path:
        return path.expanduser()


class ServerConfig(BaseModel):
    """Serveur web."""

    host: str = "0.0.0.0"
    port: int = 8010


class Settings(BaseModel):
    """Configuration complète de l'application."""

    models: ModelsConfig = ModelsConfig()
    map: MapConfig = MapConfig()
    paths: PathsConfig = PathsConfig()
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
