"""O verificador precisa barrar invenções sem barrar respostas corretas bem formatadas."""

from __future__ import annotations

import pytest

from cinedata_agent.grounding import Evidence, ungrounded_names, ungrounded_numbers

OBSERVED = Evidence(
    numbers=[2994.357, 2680.593, 12390136500.54, 7.8, 8.2, 0.5234, 37, 5, 2023, 2017, -54090.86],
    texts=[
        "Blue Beetle",
        "Gran Turismo",
        "Christopher Nolan",
        "Kevin Dunn",
        "Joe Anoa'i",
        "Avatar: The Way Of Water",
        "Marvel Studios",
        "Science Fiction",
    ],
)


@pytest.mark.parametrize(
    "answer",
    [
        "Blue Beetle (2023) lidera com popularidade 2.994,4.",
        "O índice é 2994.36, seguido de 2.680,6.",
        "A receita foi de R$ 12,4 bilhões.",
        "A receita foi de R$ 12 bilhões.",
        "A receita foi de R$ 12.390.136.500,54.",
        "Notas 7,8 e 8,2 no IMDb.",
        "Margem de 52% (ou 52,34%).",
        "A dupla fez 37 filmes juntos.",
        "Os 5 primeiros são estes.",
        "A margem mínima chega a -54.090,86.",
        "Ranking:\n1. Blue Beetle (2023)\n2. Gran Turismo (2023)",
        "Em 1º lugar, Blue Beetle; em 2º, Gran Turismo.",
    ],
)
def test_accepts_numbers_present_in_the_data(answer: str) -> None:
    assert ungrounded_numbers(answer, OBSERVED) == []


@pytest.mark.parametrize(
    ("answer", "invented"),
    [
        ("Avatar tem popularidade 10.000.", ["10.000"]),
        ("A receita foi de R$ 15 bilhões.", ["15 bilhões"]),
        ("Nota 9,1 no IMDb.", ["9,1"]),
        ("Juntos, os dois somam 5674,95.", ["5674,95"]),  # derivado de cabeça: deve vir da SQL
        ("Margem de 60%.", ["60%"]),
        ("São 7 filmes ao todo.", ["7"]),  # contagem pequena inventada não passa
    ],
)
def test_rejects_numbers_not_in_the_data(answer: str, invented: list[str]) -> None:
    assert ungrounded_numbers(answer, OBSERVED) == invented


@pytest.mark.parametrize(
    "answer",
    [
        "Blue Beetle e Gran Turismo lideram o ranking.",
        "A dupla **Joe Anoa'i** e **Kevin Dunn** trabalhou junta.",
        "O líder é Avatar: The Way Of Water.",
        "Christopher Nolan dirigiu os filmes; a Marvel Studios lidera.",
        "Segundo o IMDb e o TMDB, a nota é alta.",
        "O gênero Ficção Científica (Science Fiction) lidera.",
        "Há 2 pessoas na base.",
        "Segundo Christopher Nolan, o filme é bom.",
    ],
)
def test_accepts_names_present_in_the_data(answer: str) -> None:
    assert ungrounded_names(answer, OBSERVED, allowed_terms=["Ficção Científica"]) == []


@pytest.mark.parametrize(
    ("answer", "invented"),
    [
        ("Os mais populares são Avatar e Titanic e Vingadores Ultimato.", ["Vingadores Ultimato"]),
        ("O líder é Avatar: O Caminho da Água.", ["Avatar: O Caminho da Água"]),
        ("Greta Gerwig dirigiu o filme.", ["Greta Gerwig"]),
    ],
)
def test_rejects_names_not_in_the_data(answer: str, invented: list[str]) -> None:
    assert ungrounded_names(answer, OBSERVED) == invented
