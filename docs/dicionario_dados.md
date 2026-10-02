# Dicionário de dados — camada Gold CineData

> Arquivo gerado por `scripts/gen_data_dictionary.py` a partir de
> `src/cinedata_agent/semantic_layer.py`. Não edite à mão.

## Tabelas

### `dim_movies`

Um registro por filme (95.645 filmes, lançados entre 2016 e 2029).

| Coluna | Descrição |
|---|---|
| `sk_movie_id` | Chave substituta (hash). Usar só em JOINs; nunca exibir. |
| `id_filme` | Identificador do filme na fonte (TMDB). |
| `titulo` | Título original. NÃO é único: exibir junto com ano_lancamento. |
| `data_lancamento` | Data de lançamento (texto 'AAAA-MM-DD'). |
| `ano_lancamento` | Ano de lançamento (inteiro). |
| `duracao_minutos` | Duração em minutos. |
| `idioma_original` | Sempre NULL nesta base. Não usar. |
| `status_filme` | 'Lançado', 'Pós-Produção', 'Em Produção' ou 'Planejado' (com acentos). |
| `sinopse` | Sinopse em inglês. |
| `url_poster` | URL do pôster. |
| `url_backdrop` | URL da imagem de fundo. |

### `fact_movies_performance`

Métricas financeiras e de popularidade; exatamente 1 linha por filme.

| Coluna | Descrição |
|---|---|
| `sk_movie_id` | FK para dim_movies. |
| `orcamento_usd` | Orçamento em US$. NULL quando não informado. |
| `receita_usd` | Receita/bilheteria em US$. NULL quando não informada. |
| `lucro_usd` | Lucro em US$ (ver regras de lucro: nunca é NULL). |
| `orcamento_brl` | Orçamento em R$ (câmbio histórico por filme). |
| `receita_brl` | Receita/bilheteria em R$. Informada em só ~3,4 mil filmes. |
| `lucro_brl` | Lucro em R$ (ver regras de lucro: nunca é NULL). |
| `popularidade` | Índice de popularidade do TMDB (quanto maior, mais popular). |
| `nota_tmdb` | Nota média no TMDB (0 a 10). |
| `qtd_tmdb` | Quantidade de votos no TMDB. |
| `nota_imdb` | Nota média no IMDb (0 a 10). NULL quando não há votos. |
| `qtd_imdb` | Quantidade de votos no IMDb. |

### `dim_genres`

Os 19 gêneros, com nomes em INGLÊS (ex.: 'Action', 'Science Fiction').

| Coluna | Descrição |
|---|---|
| `sk_genre_id` | Chave substituta (hash). |
| `nome_genero` | Nome do gênero em inglês. |

### `dim_people`

Pessoas do elenco e da equipe. A mesma pessoa tem uma linha por papel.

| Coluna | Descrição |
|---|---|
| `sk_person_id` | Chave substituta (hash). |
| `nome_pessoa` | Nome. Pode se repetir entre papéis (ex.: ator que também dirige). |
| `tipo_pessoa` | Papel: 'Ator', 'Diretor' ou 'Roteirista'. |

### `dim_companies`

Produtoras.

| Coluna | Descrição |
|---|---|
| `sk_company_id` | Chave substituta (hash). |
| `nome_produtora` | Nome da produtora (único). |

### `dim_reviews`

Resumo das avaliações de usuários: 1 linha por filme avaliado (40.267 filmes).

| Coluna | Descrição |
|---|---|
| `sk_review_id` | Chave substituta (hash). |
| `sk_movie_id` | FK para dim_movies (única). |
| `qtd_avaliacoes_usuarios` | Quantidade de avaliações (1 a 13; 93% têm só 1). |
| `nota_media_usuarios` | Nota média dos usuários (0 a 10). |

### `movie_reviews`

Avaliações individuais de usuários, com texto em português.

| Coluna | Descrição |
|---|---|
| `id` | Identificador numérico da avaliação. |
| `sk_movie_review_id` | Chave substituta (hash). |
| `sk_movie_id` | FK para dim_movies. |
| `name` | Nome do usuário que avaliou. |
| `rating` | Nota dada pelo usuário (0 a 10). |
| `text` | Texto da avaliação. |
| `created_at` | Data/hora da avaliação. |

### `bridge_movie_genre`

Filme N:N gênero. ~20 mil filmes não têm gênero.

| Coluna | Descrição |
|---|---|
| `sk_movie_id` | FK para dim_movies. |
| `sk_genre_id` | FK para dim_genres. |

### `bridge_movie_person`

Filme N:N pessoa. O papel vem de dim_people.tipo_pessoa.

| Coluna | Descrição |
|---|---|
| `sk_movie_id` | FK para dim_movies. |
| `sk_person_id` | FK para dim_people. |

### `bridge_movie_company`

Filme N:N produtora.

| Coluna | Descrição |
|---|---|
| `sk_movie_id` | FK para dim_movies. |
| `sk_company_id` | FK para dim_companies. |

## Caminhos de JOIN

- Filme -> métricas: dim_movies JOIN fact_movies_performance USING (sk_movie_id)
- Filme -> gênero: dim_movies JOIN bridge_movie_genre USING (sk_movie_id) JOIN dim_genres USING (sk_genre_id)
- Filme -> pessoa: dim_movies JOIN bridge_movie_person USING (sk_movie_id) JOIN dim_people USING (sk_person_id), filtrando dim_people.tipo_pessoa
- Filme -> produtora: dim_movies JOIN bridge_movie_company USING (sk_movie_id) JOIN dim_companies USING (sk_company_id)
- Filme -> avaliações de usuários: dim_movies JOIN dim_reviews USING (sk_movie_id)
- Dupla ator-diretor: bridge_movie_person (ator) JOIN bridge_movie_person (diretor) no mesmo sk_movie_id, cada lado com seu dim_people filtrado por tipo_pessoa

## Regras de negócio

1. A camada Gold já está tratada e é a fonte de verdade: use os valores como estão. Não exclua, corrija nem deduplique registros, não os classifique como erro e não acrescente filtros além dos pedidos na pergunta ou previstos nestas regras.
2. Critério explícito na pergunta SEMPRE prevalece sobre as convenções padrão abaixo.
3. NULL significa dado ausente: não o substitua por zero. Zero informado é um valor válido.
4. 'Receita', 'faturamento' e 'bilheteria' são sinônimos: receita_brl / receita_usd.
5. Moeda padrão: R$ (colunas *_brl). Use *_usd só se a pergunta pedir dólar. Nunca converta moeda manualmente: o câmbio é histórico e varia por filme.
6. Receita só é informada em ~3,4 mil dos 95,6 mil filmes: filtre receita_brl IS NOT NULL em perguntas de receita.
7. lucro_brl nunca é NULL: vale 0 sem receita e orçamento, -orçamento sem receita, e = receita quando falta orçamento. Em perguntas de lucro, filtre receita_brl IS NOT NULL AND orcamento_brl IS NOT NULL. Se a pergunta pedir só 'receita informada', filtre apenas receita_brl IS NOT NULL. Declare o filtro nas premissas.
8. Margem de lucro = lucro_brl / receita_brl, só entre filmes com receita_brl > 0 e orcamento_brl > 0.
9. Margem média = AVG(lucro_brl / receita_brl), a média das margens de cada filme.
10. 'Nota' sem especificação = nota_imdb. 'Mais popular' = maior popularidade.
11. Divergência entre notas = ABS(nota_a - nota_b), com as duas notas não nulas. Nota 0 é um valor informado: não a exclua e não filtre por qtd_tmdb, qtd_imdb ou qtd_avaliacoes_usuarios, salvo pedido explícito (ex.: 'com pelo menos 100 votos').
12. Médias de notas usam todos os filmes com nota não nula.
13. 'Mais avaliados pelos usuários' = maior qtd_avaliacoes_usuarios (há muitos empates).
14. 'Últimos N anos' = data_lancamento entre date('now', '-N years') e date('now').
15. Não filtre status_filme por padrão: todo o catálogo conta. Só use status_filme = 'Lançado' se a pergunta restringir a filmes já lançados.
16. Gêneros estão em inglês: traduza o termo do usuário (ex.: Ação -> Action, Ficção Científica -> Science Fiction, Comédia -> Comedy, Terror -> Horror).
17. Agrupe por chaves sk_* (não por nome/título, que se repetem) e exiba nomes legíveis.
18. Contagens de filmes por entidade usam COUNT(DISTINCT sk_movie_id).
19. Nunca exiba colunas sk_* nem hashes no resultado.

## Gêneros (português -> valor no banco)

| Português | `nome_genero` |
|---|---|
| Ação | `Action` |
| Aventura | `Adventure` |
| Animação | `Animation` |
| Comédia | `Comedy` |
| Crime | `Crime` |
| Documentário | `Documentary` |
| Drama | `Drama` |
| Família | `Family` |
| Fantasia | `Fantasy` |
| História | `History` |
| Terror | `Horror` |
| Música | `Music` |
| Mistério | `Mystery` |
| Romance | `Romance` |
| Ficção Científica | `Science Fiction` |
| Thriller / Suspense | `Thriller` |
| Filme para TV | `Tv Movie` |
| Guerra | `War` |
| Faroeste | `Western` |
