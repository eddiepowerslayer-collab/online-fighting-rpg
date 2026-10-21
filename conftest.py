import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Tests must never touch the real saves/game.db."""
    monkeypatch.setenv("RPG_DB_PATH", str(tmp_path / "test.db"))
