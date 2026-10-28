"""Choix faits dans l'interface (dossier des notes, modèles), dans `preferences.json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_preferences(path: Path) -> dict[str, Any]:
    """Contenu du fichier, ou {} s'il est absent ou illisible."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def update_preferences(path: Path, **changes: Any) -> None:
    """Fusionne `changes` dans le fichier (les autres clés sont gardées)."""
    data = load_preferences(path)
    data.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
