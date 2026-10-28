"""Dossier où s'écrivent les notes de conférence.

Ordre de priorité : `[paths] vault` dans `config.toml`, puis le dossier choisi
dans l'interface (`preferences.json`), puis le vault Obsidian par défaut si
Obsidian est installé. Sans rien de tout cela, l'utilisateur doit choisir.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from confmap.config import Settings
from confmap.preferences import load_preferences, update_preferences

OBSIDIAN_DEFAULT = Path("~/Documents/Obsidian Vault/Conferences").expanduser()
SUGGESTED_FOLDER = Path("~/Documents/confmap").expanduser()

Source = Literal["config", "choice", "obsidian"]


def obsidian_settings_file() -> Path:
    """Fichier de réglages d'Obsidian (liste des vaults) selon le système."""
    if sys.platform == "darwin":
        return Path("~/Library/Application Support/obsidian/obsidian.json").expanduser()
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA", "~")).expanduser()
            / "obsidian"
            / "obsidian.json"
        )
    return Path("~/.config/obsidian/obsidian.json").expanduser()


def obsidian_installed() -> bool:
    """Vrai si Obsidian a déjà été lancé sur cette machine."""
    return obsidian_settings_file().exists()


class Destination:
    """Résout, et enregistre au besoin, le dossier des notes.

    Args:
        settings: Configuration chargée.
        obsidian: Présence d'Obsidian ; détectée si None (paramètre pour les tests).
    """

    def __init__(self, settings: Settings, obsidian: bool | None = None) -> None:
        """Garde la configuration ; la résolution se fait à chaque appel."""
        self.settings = settings
        self.obsidian = obsidian_installed() if obsidian is None else obsidian

    def _chosen(self) -> Path | None:
        folder = load_preferences(self.settings.paths.preferences).get("notes_folder")
        return Path(folder) if folder else None

    def resolve(self) -> tuple[Path | None, Source | None]:
        """Dossier des notes et d'où il vient, ou (None, None) s'il faut choisir."""
        if self.settings.paths.vault is not None:
            return self.settings.paths.vault, "config"
        chosen = self._chosen()
        if chosen is not None:
            return chosen, "choice"
        if self.obsidian:
            return OBSIDIAN_DEFAULT, "obsidian"
        return None, None

    @property
    def folder(self) -> Path | None:
        """Dossier des notes, ou None s'il faut choisir."""
        return self.resolve()[0]

    def choose(self, folder: str) -> Path:
        """Crée le dossier, vérifie qu'on peut y écrire et l'enregistre.

        Raises:
            ValueError: Chemin vide, relatif ou impossible à créer.
        """
        if not folder.strip():
            raise ValueError("chemin vide")
        path = Path(folder.strip()).expanduser()
        if not path.is_absolute():
            raise ValueError("indiquer un chemin complet (ex. ~/Documents/confmap)")
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".confmap-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as error:
            raise ValueError(f"dossier inutilisable : {error}") from error
        update_preferences(self.settings.paths.preferences, notes_folder=str(path))
        return path

    def describe(self) -> dict:
        """État pour l'interface."""
        folder, source = self.resolve()
        return {
            "folder": str(folder) if folder else None,
            "source": source,
            "obsidian": self.obsidian,
            "suggestion": str(SUGGESTED_FOLDER),
        }
