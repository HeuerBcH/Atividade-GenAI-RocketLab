from __future__ import annotations

from pathlib import Path

from cinedata_agent.config import PROJECT_ROOT, Settings


def test_relative_db_path_is_anchored_at_project_root() -> None:
    settings = Settings(_env_file=None, db_path=Path("data/x.db"))
    assert settings.db_path == PROJECT_ROOT / "data" / "x.db"


def test_absolute_db_path_is_kept(tmp_path: Path) -> None:
    target = tmp_path / "gold.db"
    assert Settings(_env_file=None, db_path=target).db_path == target


def test_api_key_is_never_exposed_in_repr() -> None:
    settings = Settings(_env_file=None, openrouter_api_key="sk-or-v1-secret")
    assert "sk-or-v1-secret" not in repr(settings)
