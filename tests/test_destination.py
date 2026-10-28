import json

import pytest

from confmap.config import Settings
from confmap.destination import OBSIDIAN_DEFAULT, Destination


@pytest.fixture
def settings(tmp_path):
    settings = Settings()
    settings.paths.preferences = tmp_path / "preferences.json"
    return settings


def test_priority_order(settings, tmp_path):
    assert Destination(settings, obsidian=False).resolve() == (None, None)
    assert Destination(settings, obsidian=True).resolve() == (
        OBSIDIAN_DEFAULT,
        "obsidian",
    )
    chosen = Destination(settings, obsidian=True).choose(str(tmp_path / "notes"))
    assert Destination(settings, obsidian=True).resolve() == (chosen, "choice")
    settings.paths.vault = tmp_path / "config"
    assert Destination(settings, obsidian=False).resolve() == (
        tmp_path / "config",
        "config",
    )


def test_choose_creates_and_saves(settings, tmp_path):
    folder = tmp_path / "a" / "b"
    Destination(settings, obsidian=False).choose(str(folder))
    assert folder.is_dir()
    saved = json.loads(settings.paths.preferences.read_text(encoding="utf-8"))
    assert saved == {"notes_folder": str(folder)}


@pytest.mark.parametrize("bad", ["", "   ", "relatif/dossier"])
def test_choose_rejects(settings, bad):
    with pytest.raises(ValueError):
        Destination(settings, obsidian=False).choose(bad)
