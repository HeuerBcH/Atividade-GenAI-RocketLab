from __future__ import annotations

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


def test_accepts_numbers_present_in_the_data_in_any_brazilian_format() -> None:
    answers = [
        "Blue Beetle (2023) lidera com popularidade 2.994,4.",
        "O índice é 2994.36, seguido de 2.680,6.",
        "Blue Beetle tem popularidade 2 994,36.",
        "A receita foi de R$ 12,4 bilhões, ou R$ 12 bilhões, ou R$ 12,39 bi.",
        "A receita foi de R$ 12.390.136.500,54.",
        "Notas 7,8 e 8,2 no IMDb. Margem de 52% (ou 52,34%).",
        "A dupla fez 37 filmes juntos. A margem mínima chega a -54.090,86.",
        "Ranking:\n1. Blue Beetle (2023)\n2. Gran Turismo (2023)",
        "Em 1º lugar, Blue Beetle; em 2º, Gran Turismo.",
    ]
    assert {a: ungrounded_numbers(a, OBSERVED) for a in answers} == {a: [] for a in answers}


def test_rejects_invented_or_derived_numbers() -> None:
    cases = {
        "Avatar tem popularidade 10.000.": ["10.000"],
        "A receita foi de R$ 15 bilhões.": ["15 bilhões"],
        "A receita foi de R$ 99 bi.": ["99 bi"],
        "Nota 9,1 no IMDb.": ["9,1"],
        "Juntos, os dois somam 5674,95.": ["5674,95"],  # conta de cabeça: tem que vir da SQL
        "Margem de 60%.": ["60%"],
        "São 7 filmes ao todo.": ["7"],
    }
    assert {a: ungrounded_numbers(a, OBSERVED) for a in cases} == cases


def test_accepts_names_present_in_the_data() -> None:
    answers = [
        "Blue Beetle e Gran Turismo lideram o ranking.",
        "A dupla **Joe Anoa'i** e **Kevin Dunn** trabalhou junta.",
        "O líder é Avatar: The Way Of Water.",
        "Segundo Christopher Nolan, a Marvel Studios lidera.",
        "Segundo o IMDb e o TMDB, a nota é alta. Há 2 pessoas na base.",
        "O gênero Ficção Científica (Science Fiction) lidera.",
        "Filtrei status_filme = 'Lançado'. Filtramos também o ano.",
    ]
    found = {a: ungrounded_names(a, OBSERVED, allowed_terms=["Ficção Científica"]) for a in answers}
    assert found == {a: [] for a in answers}


def test_rejects_names_not_in_the_data() -> None:
    cases = {
        "Os mais populares são Avatar e Titanic e Vingadores Ultimato.": ["Vingadores Ultimato"],
        "O líder é Avatar: O Caminho da Água.": ["Avatar: O Caminho da Água"],  # traduzido
        "Greta Gerwig dirigiu o filme.": ["Greta Gerwig"],
    }
    assert {a: ungrounded_names(a, OBSERVED) for a in cases} == cases
