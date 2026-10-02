from __future__ import annotations

from pathlib import Path

from cinedata_agent.config import PROJECT_ROOT, Settings


def test_settings(tmp_path: Path) -> None:
    assert Settings(_env_file=None, db_path=Path("data/x.db")).db_path == PROJECT_ROOT / "data/x.db"
    assert Settings(_env_file=None, db_path=tmp_path / "x.db").db_path == tmp_path / "x.db"

    settings = Settings(_env_file=None, groq_api_key="gsk_segredo", model_name="a, b")
    assert settings.model_chain == ["a", "b"]
    assert "gsk_segredo" not in repr(settings)
