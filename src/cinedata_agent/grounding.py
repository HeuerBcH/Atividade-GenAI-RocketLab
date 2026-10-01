"""Verificação de fundamentação: a resposta só pode citar o que veio do banco.

Tolerância zero a alucinação, garantida por código e não por instrução ao modelo:

- **Números:** todo número citado no texto precisa corresponder a um valor observado nos
  resultados das ferramentas (ou na pergunta, ou numa constante documentada das regras de
  negócio). Formatos brasileiros ("R$ 12,4 bilhões", "2.994,4", "52%") e arredondamentos
  legítimos são aceitos; números derivados de cabeça (somas, diferenças) não: devem vir da SQL.
- **Nomes próprios:** sequências de 2+ palavras capitalizadas (ex.: "Blue Beetle",
  "Christopher Nolan") precisam aparecer nos dados observados ou na pergunta.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_NUMBER = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    r"(\s*%|\s*(?:mil|milh(?:ão|ões|ao|oes)|bilh(?:ão|ões|ao|oes)|trilh(?:ão|ões|ao|oes))\b)?",
    re.IGNORECASE,
)
_SCALES = {"mil": 1e3, "milh": 1e6, "bilh": 1e9, "trilh": 1e12}

# Nome próprio: 2+ palavras capitalizadas, admitindo conectivos e pontuação de títulos.
_WORD = r"[A-ZÀ-Ý0-9][\w'\u2019À-ÿ.-]*:?"
_CONNECTOR = r"(?:de|da|do|das|dos|e|of|the|and|a|an|in|on|to|for|vs\.?|[:&-])"
_PROPER_NAME = re.compile(rf"{_WORD}(?:\s+(?:{_CONNECTOR}\s+)*{_WORD})+")
# Separadores de enumeração ("Blue Beetle e Gran Turismo" são dois nomes, não um).
_LIST_SEPARATOR = re.compile(r"\s+(?:e|and|&)\s+|,\s*")

# Termos do domínio que não são entidades do banco.
_ALWAYS_ALLOWED = {
    "imdb",
    "tmdb",
    "cinedata",
    "cinedata analytics",
    "camada gold",
    "r$",
    "us$",
    "sql",
}


@dataclass(frozen=True)
class _Reading:
    """Uma interpretação possível de um número escrito no texto."""

    value: float  # na unidade escrita (ex.: 12.4 para "12,4 bilhões")
    unit: float  # multiplicador da unidade (1e9 para bilhões; 0.01 para %)
    decimals: int  # casas decimais escritas (para aceitar arredondamento)


def _readings(token: str, suffix: str | None) -> list[_Reading]:
    suffix = (suffix or "").strip().lower()
    units = [1.0]
    if suffix == "%":
        units = [0.01, 1.0]  # 52% pode vir do banco como 0.52 ou 52
    elif suffix:
        units = [next(v for k, v in _SCALES.items() if suffix.startswith(k))]

    interpretations: list[tuple[float, int]] = []
    if "," in token:  # padrão brasileiro: 1.234,5
        integer, decimal = token.replace(".", "").split(",")
        interpretations.append((float(f"{integer}.{decimal}"), len(decimal)))
    elif "." in token:  # ambíguo: 2.994 = 2994 (milhar) ou 2,994 (decimal)
        if all(len(group) == 3 for group in token.split(".")[1:]):
            interpretations.append((float(token.replace(".", "")), 0))
        interpretations.append((float(token), len(token.split(".")[-1])))
    else:
        interpretations.append((float(token), 0))
    return [_Reading(v, u, d) for v, d in interpretations for u in units]


# Marcadores de posição em listas ("1. Blue Beetle", "2) ...", "1º lugar") não são dados.
_LIST_MARKER = re.compile(r"(?m)(?:^|(?<=[\s:;]))\d{1,2}(?:[.)](?=\s)|[ºª°])")


def extract_numbers(text: str) -> list[tuple[str, list[_Reading]]]:
    text = _LIST_MARKER.sub(" ", text)
    return [(m.group(0).strip(), _readings(m.group(1), m.group(2))) for m in _NUMBER.finditer(text)]


def _matches(reading: _Reading, observed: float) -> bool:
    scaled = abs(observed) / reading.unit
    if math.isclose(round(scaled, reading.decimals), reading.value, abs_tol=1e-9):
        return True
    return math.isclose(scaled, reading.value, rel_tol=0.005)


def collect_values(content: object) -> tuple[list[float], list[str]]:
    """Achata o conteúdo das ferramentas em números e textos observados."""
    numbers: list[float] = []
    texts: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, int | float):
            numbers.append(float(item))
        elif isinstance(item, str):
            texts.append(item)
            for _, readings in extract_numbers(item):  # números dentro de títulos ("2049")
                numbers.extend(r.value * r.unit for r in readings if r.unit == 1.0)
        elif isinstance(item, dict):
            for value in item.values():
                walk(value)
        elif isinstance(item, list | tuple):
            for value in item:
                walk(value)

    walk(content)
    return numbers, texts


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("\u2019", "'"))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True)
class Evidence:
    """Tudo que a resposta pode citar: dados observados, pergunta e constantes permitidas."""

    numbers: list[float]
    texts: list[str]


def ungrounded_numbers(text: str, evidence: Evidence) -> list[str]:
    return [
        literal
        for literal, readings in extract_numbers(text)
        if not any(_matches(r, o) for r in readings for o in evidence.numbers)
    ]


def _capitalized_words(words: list[str]) -> int:
    return sum(1 for w in words if w[:1].isalpha() and w[:1].isupper())


def ungrounded_names(text: str, evidence: Evidence, allowed_terms: Iterable[str] = ()) -> list[str]:
    haystack = _normalize(" | ".join(evidence.texts))
    allowed = {_normalize(t) for t in (*_ALWAYS_ALLOWED, *allowed_terms)}

    def grounded(words: list[str]) -> bool:
        # Descarta palavras iniciais (ex.: "Segundo Christopher Nolan") enquanto restar um nome.
        while _capitalized_words(words) >= 2:
            normalized = _normalize(" ".join(words).strip(" .:-"))
            if normalized in haystack or any(normalized in a or a in normalized for a in allowed):
                return True
            words = words[1:]
        return False

    missing = []
    for match in _PROPER_NAME.finditer(text.replace("**", "")):
        for piece in _LIST_SEPARATOR.split(match.group(0)):
            words = piece.strip(" .:-").split()
            if _capitalized_words(words) >= 2 and not grounded(words):
                missing.append(" ".join(words))
    return missing
