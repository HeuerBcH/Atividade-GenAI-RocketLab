"""Monta o system prompt a partir do template e da camada semântica."""

from __future__ import annotations

import hashlib
from datetime import date
from functools import cache
from importlib.resources import files

from .semantic_layer import render_prompt


@cache
def _template() -> str:
    return files("cinedata_agent").joinpath("prompts/system_prompt.md").read_text("utf-8")


def build_instructions(today: date | None = None) -> str:
    today = today or date.today()
    return _template().format(today=today.isoformat(), semantic_layer=render_prompt())


@cache
def prompt_version() -> str:
    content = _template() + render_prompt()
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
