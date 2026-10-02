"""Significado de negócio das tabelas Gold. Alimenta o prompt e o dicionário de dados."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]


def _cols(*pairs: tuple[str, str]) -> tuple[Column, ...]:
    return tuple(Column(name, description) for name, description in pairs)


TABLES: tuple[Table, ...] = (
    Table(
        "dim_movies",
        "Um registro por filme (95.645 filmes, lançados entre 2016 e 2029).",
        _cols(
            ("sk_movie_id", "Chave substituta (hash). Usar só em JOINs; nunca exibir."),
            ("id_filme", "Identificador do filme na fonte (TMDB)."),
            ("titulo", "Título original. NÃO é único: exibir junto com ano_lancamento."),
            ("data_lancamento", "Data de lançamento (texto 'AAAA-MM-DD')."),
            ("ano_lancamento", "Ano de lançamento (inteiro)."),
            ("duracao_minutos", "Duração em minutos."),
            ("idioma_original", "Sempre NULL nesta base. Não usar."),
            (
                "status_filme",
                "'Lançado', 'Pós-Produção', 'Em Produção' ou 'Planejado' (com acentos).",
            ),
            ("sinopse", "Sinopse em inglês."),
            ("url_poster", "URL do pôster."),
            ("url_backdrop", "URL da imagem de fundo."),
        ),
    ),
    Table(
        "fact_movies_performance",
        "Métricas financeiras e de popularidade; exatamente 1 linha por filme.",
        _cols(
            ("sk_movie_id", "FK para dim_movies."),
            ("orcamento_usd", "Orçamento em US$. NULL quando não informado."),
            ("receita_usd", "Receita/bilheteria em US$. NULL quando não informada."),
            ("lucro_usd", "Lucro em US$ (ver regras de lucro: nunca é NULL)."),
            ("orcamento_brl", "Orçamento em R$ (câmbio histórico por filme)."),
            ("receita_brl", "Receita/bilheteria em R$. Informada em só ~3,4 mil filmes."),
            ("lucro_brl", "Lucro em R$ (ver regras de lucro: nunca é NULL)."),
            ("popularidade", "Índice de popularidade do TMDB (quanto maior, mais popular)."),
            ("nota_tmdb", "Nota média no TMDB (0 a 10). Vale 0 quando qtd_tmdb = 0."),
            ("qtd_tmdb", "Quantidade de votos no TMDB."),
            ("nota_imdb", "Nota média no IMDb (0 a 10). NULL quando não há votos."),
            ("qtd_imdb", "Quantidade de votos no IMDb."),
        ),
    ),
    Table(
        "dim_genres",
        "Os 19 gêneros, com nomes em INGLÊS (ex.: 'Action', 'Science Fiction').",
        _cols(
            ("sk_genre_id", "Chave substituta (hash)."),
            ("nome_genero", "Nome do gênero em inglês."),
        ),
    ),
    Table(
        "dim_people",
        "Pessoas do elenco e da equipe. A mesma pessoa tem uma linha por papel.",
        _cols(
            ("sk_person_id", "Chave substituta (hash)."),
            ("nome_pessoa", "Nome. Pode se repetir entre papéis (ex.: ator que também dirige)."),
            ("tipo_pessoa", "Papel: 'Ator', 'Diretor' ou 'Roteirista'."),
        ),
    ),
    Table(
        "dim_companies",
        "Produtoras.",
        _cols(
            ("sk_company_id", "Chave substituta (hash)."),
            ("nome_produtora", "Nome da produtora (único)."),
        ),
    ),
    Table(
        "dim_reviews",
        "Resumo das avaliações de usuários: 1 linha por filme avaliado (40.267 filmes).",
        _cols(
            ("sk_review_id", "Chave substituta (hash)."),
            ("sk_movie_id", "FK para dim_movies (única)."),
            ("qtd_avaliacoes_usuarios", "Quantidade de avaliações (1 a 13; 93% têm só 1)."),
            ("nota_media_usuarios", "Nota média dos usuários (0 a 10)."),
        ),
    ),
    Table(
        "movie_reviews",
        "Avaliações individuais de usuários, com texto em português.",
        _cols(
            ("id", "Identificador numérico da avaliação."),
            ("sk_movie_review_id", "Chave substituta (hash)."),
            ("sk_movie_id", "FK para dim_movies."),
            ("name", "Nome do usuário que avaliou."),
            ("rating", "Nota dada pelo usuário (0 a 10)."),
            ("text", "Texto da avaliação."),
            ("created_at", "Data/hora da avaliação."),
        ),
    ),
    Table(
        "bridge_movie_genre",
        "Filme N:N gênero. ~20 mil filmes não têm gênero.",
        _cols(("sk_movie_id", "FK para dim_movies."), ("sk_genre_id", "FK para dim_genres.")),
    ),
    Table(
        "bridge_movie_person",
        "Filme N:N pessoa. O papel vem de dim_people.tipo_pessoa.",
        _cols(("sk_movie_id", "FK para dim_movies."), ("sk_person_id", "FK para dim_people.")),
    ),
    Table(
        "bridge_movie_company",
        "Filme N:N produtora.",
        _cols(
            ("sk_movie_id", "FK para dim_movies."),
            ("sk_company_id", "FK para dim_companies."),
        ),
    ),
)

JOIN_PATHS: tuple[str, ...] = (
    "Filme -> métricas: dim_movies JOIN fact_movies_performance USING (sk_movie_id)",
    "Filme -> gênero: dim_movies JOIN bridge_movie_genre USING (sk_movie_id) "
    "JOIN dim_genres USING (sk_genre_id)",
    "Filme -> pessoa: dim_movies JOIN bridge_movie_person USING (sk_movie_id) "
    "JOIN dim_people USING (sk_person_id), filtrando dim_people.tipo_pessoa",
    "Filme -> produtora: dim_movies JOIN bridge_movie_company USING (sk_movie_id) "
    "JOIN dim_companies USING (sk_company_id)",
    "Filme -> avaliações de usuários: dim_movies JOIN dim_reviews USING (sk_movie_id)",
    "Dupla ator-diretor: bridge_movie_person (ator) JOIN bridge_movie_person (diretor) "
    "no mesmo sk_movie_id, cada lado com seu dim_people filtrado por tipo_pessoa",
)

# Constantes das convenções: usadas no prompt e nas SQLs de referência (eval/golden.yaml).
MIN_RATING_VOTES = 100
MIN_USER_REVIEWS = 3

BUSINESS_RULES: tuple[str, ...] = (
    # Precedência
    "Critério explícito na pergunta SEMPRE prevalece sobre as convenções padrão abaixo.",
    # Finanças
    "'Receita', 'faturamento' e 'bilheteria' são sinônimos: receita_brl / receita_usd.",
    "Moeda padrão: R$ (colunas *_brl). Use *_usd só se a pergunta pedir dólar. "
    "Nunca converta moeda manualmente: o câmbio é histórico e varia por filme.",
    "Receita só é informada em ~3,4 mil dos 95,6 mil filmes: filtre receita_brl IS NOT NULL "
    "em perguntas de receita.",
    "lucro_brl nunca é NULL, mas só é confiável com receita informada: vale 0 sem receita e "
    "orçamento, -orçamento sem receita, e = receita quando falta orçamento. Em perguntas de "
    "lucro, filtre no mínimo receita_brl IS NOT NULL.",
    "Margem de lucro = lucro_brl / receita_brl, só entre filmes com receita_brl > 0 e "
    "orcamento_brl > 0. Orçamentos abaixo de R$ 10 mil são provavelmente erro na fonte: "
    "avise o usuário quando aparecerem no topo.",
    "Margem média = AVG(lucro_brl / receita_brl). Ela é muito sensível a outliers (receitas "
    "ínfimas geram margens de -50.000x): ao responder, avise que a média é distorcida por eles.",
    # Notas e popularidade
    "'Nota' sem especificação = nota_imdb. 'Mais popular' = maior popularidade.",
    f"Ao comparar ou ranquear notas sem critério na pergunta, exija qtd_imdb >= "
    f"{MIN_RATING_VOTES} e, se usar TMDB, qtd_tmdb >= {MIN_RATING_VOTES}.",
    f"Comparações com a nota dos usuários (dim_reviews) exigem qtd_avaliacoes_usuarios >= "
    f"{MIN_USER_REVIEWS}, salvo critério na pergunta.",
    "'Mais avaliados pelos usuários' = maior qtd_avaliacoes_usuarios (há muitos empates).",
    "Divergência entre notas = ABS(nota_a - nota_b), ambas não nulas.",
    # Tempo
    "'Últimos N anos' = data_lancamento entre date('now', '-N years') e date('now').",
    "Filmes com data futura ou status diferente de 'Lançado' ainda não foram lançados.",
    # Entidades
    "Gêneros estão em inglês: traduza o termo do usuário (ex.: Ação -> Action, Ficção "
    "Científica -> Science Fiction, Comédia -> Comedy, Terror -> Horror).",
    "Agrupe por chaves sk_* (não por nome/título, que se repetem) e exiba nomes legíveis.",
    "Contagens de filmes por entidade usam COUNT(DISTINCT sk_movie_id).",
    "Nunca exiba colunas sk_* nem hashes no resultado.",
    # Qualidade de dados conhecida (não corrigir; avisar o usuário quando afetar a resposta)
    "Popularidade corrompida em 4 filmes, com valor igual a um ano (ex.: 'La Fellinette' = "
    "2020.0, 'Battipaglia 1969' = 1969.0). NÃO os exclua da consulta: mantenha-os no "
    "resultado e, se aparecerem no topo, avise na resposta que é erro da fonte.",
    "Há cadastros duplicados na fonte (ex.: dezenas de 'Die Hart 2: Die Harter' de 2024). "
    "NÃO deduplique nem filtre: mantenha o resultado e avise quando duplicatas o dominarem.",
)

# Campos que a ferramenta `buscar_valores` pode consultar: (tabela, coluna, coluna extra exibida).
# Allowlist fechada: o LLM escolhe um nome lógico e nunca injeta identificadores na SQL.
SEARCHABLE_FIELDS: dict[str, tuple[str, str, str | None]] = {
    "filme": ("dim_movies", "titulo", "ano_lancamento"),
    "pessoa": ("dim_people", "nome_pessoa", "tipo_pessoa"),
    "produtora": ("dim_companies", "nome_produtora", None),
    "genero": ("dim_genres", "nome_genero", None),
    "status": ("dim_movies", "status_filme", None),
}

GENRE_TRANSLATIONS: dict[str, str] = {
    "Ação": "Action",
    "Aventura": "Adventure",
    "Animação": "Animation",
    "Comédia": "Comedy",
    "Crime": "Crime",
    "Documentário": "Documentary",
    "Drama": "Drama",
    "Família": "Family",
    "Fantasia": "Fantasy",
    "História": "History",
    "Terror": "Horror",
    "Música": "Music",
    "Mistério": "Mystery",
    "Romance": "Romance",
    "Ficção Científica": "Science Fiction",
    "Thriller / Suspense": "Thriller",
    "Filme para TV": "Tv Movie",
    "Guerra": "War",
    "Faroeste": "Western",
}


def render_markdown() -> str:
    lines = ["## Tabelas", ""]
    for table in TABLES:
        lines += [f"### `{table.name}`", "", table.description, ""]
        lines += ["| Coluna | Descrição |", "|---|---|"]
        lines += [f"| `{col.name}` | {col.description} |" for col in table.columns]
        lines.append("")
    lines += ["## Caminhos de JOIN", ""]
    lines += [f"- {path}" for path in JOIN_PATHS]
    lines += ["", "## Regras de negócio", ""]
    lines += [f"{i}. {rule}" for i, rule in enumerate(BUSINESS_RULES, start=1)]
    lines += ["", "## Gêneros (português -> valor no banco)", ""]
    lines += ["| Português | `nome_genero` |", "|---|---|"]
    lines += [f"| {pt} | `{en}` |" for pt, en in GENRE_TRANSLATIONS.items()]
    return "\n".join(lines) + "\n"


def _is_obvious(description: str) -> bool:
    return description.startswith(("Chave substituta", "FK para"))


def render_prompt() -> str:
    # versão enxuta para o prompt: o Groq gratuito limita tokens por minuto
    lines = ["Tabelas:"]
    for table in TABLES:
        lines.append(
            f"- {table.name}({', '.join(c.name for c in table.columns)}): {table.description}"
        )
        lines += [
            f"    {c.name}: {c.description}"
            for c in table.columns
            if not _is_obvious(c.description)
        ]
    lines += ["", "Joins:", *(f"- {path}" for path in JOIN_PATHS)]
    lines += ["", "Regras de negócio:", *(f"- {rule}" for rule in BUSINESS_RULES)]
    genres = ", ".join(f"{pt}={en}" for pt, en in GENRE_TRANSLATIONS.items())
    lines += ["", f"Gêneros (português=valor no banco): {genres}"]
    return "\n".join(lines)


def render_data_dictionary() -> str:
    header = (
        "# Dicionário de dados — camada Gold CineData\n\n"
        "> Arquivo gerado por `scripts/gen_data_dictionary.py` a partir de\n"
        "> `src/cinedata_agent/semantic_layer.py`. Não edite à mão.\n\n"
    )
    return header + render_markdown()
