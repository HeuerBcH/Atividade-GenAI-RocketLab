# Relatório de avaliação

Gerado em 01/10/2026 21:44. Critério: o resultado da SQL do agente precisa bater com o da SQL de referência (`eval/golden.yaml`); recusas não podem executar consulta.

## Resumo

| Métrica | Valor |
|---|---|
| Acerto geral | 13/14 (93%) |
| Perguntas do enunciado | 13/14 (93%) |
| Casos avaliados / total | 14/22 |
| Chamadas ao LLM por pergunta (média) | 3.6 |
| Tokens por pergunta (média) | 13,604 |
| Latência por pergunta (média) | 27.8 s |
| Modelo(s) | openai/gpt-oss-120b |

## Por categoria

| Categoria | Acertos |
|---|---|
| Bilheteria e Finanças | 3/3 (100%) |
| Popularidade e Engajamento | 3/3 (100%) |
| Elenco e Equipe | 3/3 (100%) |
| Gêneros e Produtoras | 3/3 (100%) |
| Avaliações dos Usuários | 1/2 (50%) |

## Casos

### BIL-01 — OK

**Pergunta:** Quais são os 10 filmes com maior receita em R$?

- Verificação: ordem confere
- Resposta: Os 10 filmes com maior receita em reais são: 
1. Avatar: The Way Of Water (2022) – R$ 12.390.136.500,54;
2. Avengers: Endgame (2019) – R$ 11.094.720.000,00;
3. Spider‑Man: No Way Home (2021) – R$ 10.977.782.882,74;
4. Avengers: Infinity War (2018) – R$ 7.190.430.847,63;
5. Top Gun: Maverick (2022) – R$ 7.160.804.869,01;
6. Barbie (2023) – R$ 6.856.159.007,38;
7. The Super Mario Bros. Movie (2023) – R$ 6.838.413.799,10;
8. The Lion King (2019) – R$ 6.227.552.146,58;
9. Frozen II (2019) – R$ 6.094.028.191,32;
10. Jurassic World: Fallen Kingdom (2018) – R$ 4.934.822.930,85. 
Esses valores consideram apenas os filmes que têm a receita em reais registrada na base.
- Premissas: Filtrei apenas filmes com receita_brl não nula.; Ordenei pela receita em reais em ordem decrescente e limitei a 10 registros.
- Custo: 3 chamada(s), 11,245 tokens, 24.6 s

```sql
SELECT dm.titulo AS titulo, dm.ano_lancamento AS ano, fmp.receita_brl AS receita
FROM dim_movies dm
JOIN fact_movies_performance fmp USING (sk_movie_id)
WHERE fmp.receita_brl IS NOT NULL
ORDER BY fmp.receita_brl DESC
LIMIT 10
```

### BIL-02 — OK

**Pergunta:** Qual o lucro médio por gênero, considerando apenas filmes com receita informada?

- Verificação: mapeamento confere
- Resposta: O lucro médio dos filmes com receita informada varia bastante por gênero. O gênero com maior lucro médio é Science Fiction, com cerca de R$ 520.783.718,33, seguido por Adventure (R$ 514.678.791,39) e Action (R$ 343.223.021,87). Entre os menores estão Mystery (R$ 119.462.433,49) e Comedy (R$ 143.589.472,55).
- Premissas: Considerei apenas filmes onde receita_brl não é NULL; Calculei a média de lucro_brl por gênero
- Custo: 6 chamada(s), 22,901 tokens, 110.1 s

```sql
SELECT g.nome_genero AS genero, ROUND(AVG(f.lucro_brl), 2) AS lucro_medio_brl
FROM dim_movies m
JOIN fact_movies_performance f USING (sk_movie_id)
JOIN bridge_movie_genre bg USING (sk_movie_id)
JOIN dim_genres g USING (sk_genre_id)
WHERE f.receita_brl IS NOT NULL
GROUP BY g.nome_genero
ORDER BY lucro_medio_brl DESC
```

### BIL-03 — OK

**Pergunta:** Quais filmes têm a maior margem de lucro, entre os que possuem receita e orçamento informados?

- Verificação: valores conferem
- Resposta: Os filmes com a maior margem de lucro (lucro ÷ receita) são:
1. **Dad, I'm Sorry (2021)** – margem 100.0 %, lucro R$ 95 303 050.39, receita R$ 95 303 762.5.
2. **Etlb (2017)** – margem 100.0 %, lucro R$ 3 225 638.71, receita R$ 3 225 800.0.
3. **Jailbait (2017)** – margem 99.99 %, lucro R$ 23 777 152.36, receita R$ 23 778 840.8.
4. **Trivikrama (2022)** – margem 99.96 %, lucro R$ 52 307.07, receita R$ 52 328.0.
5. **The Good Neighbor (2022)** – margem 99.89 %, lucro R$ 486 410.88, receita R$ 486 949.61.

⚠️ Alguns desses títulos apresentam orçamentos muito baixos (por exemplo, valores de poucos reais), o que pode indicar erros de registro e inflar a margem de lucro.
- Premissas: Considerei apenas filmes com receita_brl e orçamento_brl informados e maiores que zero.; A margem foi calculada como (lucro_brl / receita_brl) × 100 e ordenada em ordem decrescente.
- Custo: 5 chamada(s), 21,621 tokens, 94.1 s

```sql
SELECT dm.titulo || ' (' || dm.ano_lancamento || ')' AS filme,
       ROUND(fmp.lucro_brl / fmp.receita_brl * 100, 2) AS margem_percentual,
       ROUND(fmp.lucro_brl, 2) AS lucro_brl,
       ROUND(fmp.receita_brl, 2) AS receita_brl,
       ROUND(fmp.orcamento_brl, 2) AS orcamento_brl
FROM dim_movies dm
JOIN fact_movies_performance fmp USING (sk_movie_id)
WHERE fmp.receita_brl IS NOT NULL
  AND fmp.receita_brl > 0
  AND fmp.orcamento_brl IS NOT NULL
  AND fmp.orcamento_brl > 0
ORDER BY margem_percentual DESC
LIMIT 10
```

### POP-01 — OK

**Pergunta:** Quais são os 5 filmes mais populares?

- Verificação: ordem confere
- Resposta: Os cinco filmes com maior índice de popularidade são: Blue Beetle (2023) com popularidade 2.994, Gran Turismo (2023) com 2.681, La Fellinette (2020) com 2.020, The Fear Footage 2: Curse Of The Tape (2020) com 2.019 e WWE Survivor Series 2018 (2018) com 2.018. Atenção: os últimos três apresentam valores de popularidade que correspondem ao ano de lançamento, o que indica um erro de registro na fonte.
- Premissas: Consideramos todos os filmes do catálogo, independentemente do status.; Ordenamos apenas pelo campo popularidade, sem filtros adicionais.
- Custo: 3 chamada(s), 10,685 tokens, 3.0 s

```sql
SELECT dm.titulo AS titulo, dm.ano_lancamento AS ano, fmp.popularidade AS popularidade
FROM dim_movies dm
JOIN fact_movies_performance fmp USING (sk_movie_id)
ORDER BY fmp.popularidade DESC
LIMIT 5
```

### POP-02 — OK

**Pergunta:** Quais filmes têm a maior divergência entre a nota TMDB e a nota IMDb?

- Verificação: valores conferem
- Resposta: Os 10 filmes com maior diferença entre a nota do TMDB e a do IMDb são, por exemplo, "Me Against You: Mr. S's Vendetta (2020)" com TMDB 8,13 e IMDb 1,7 (diferença 6,43), "5gang: A Different Kind Of Christmas (2019)" com TMDB 8,20 e IMDb 2,0 (diferença 6,20) e "Harry And Meghan: Escaping The Palace (2021)" com TMDB 6,76 e IMDb 2,6 (diferença 4,16). As demais listadas apresentam divergências entre 3,6 e 4,0 pontos.
- Premissas: Considerei apenas filmes que têm nota tanto no TMDB quanto no IMDb; Exigi pelo menos 100 votos em cada fonte (qtd_imdb >= 100 e qtd_tmdb >= 100) para garantir relevância das notas
- Custo: 4 chamada(s), 15,415 tokens, 26.2 s

```sql
SELECT dm.titulo || ' (' || dm.ano_lancamento || ')' AS filme,
       ROUND(fmp.nota_tmdb,2) AS nota_tmdb,
       ROUND(fmp.nota_imdb,2) AS nota_imdb,
       ROUND(ABS(fmp.nota_tmdb - fmp.nota_imdb),2) AS divergencia
FROM dim_movies dm
JOIN fact_movies_performance fmp USING (sk_movie_id)
WHERE fmp.nota_tmdb IS NOT NULL
  AND fmp.nota_imdb IS NOT NULL
  AND fmp.qtd_imdb >= 100
  AND fmp.qtd_tmdb >= 100
ORDER BY divergencia DESC
LIMIT 10
```

### POP-03 — OK

**Pergunta:** Qual a nota média IMDb por ano de lançamento?

- Verificação: mapeamento confere
- Resposta: A nota média no IMDb dos filmes lançados entre 2016 e 2025 varia pouco, ficando entre 6,15 e 6,58. O pico foi em 2025, com média de 6,58, enquanto 2024 registrou a menor média, 6,15. Nos demais anos a média ficou estável em torno de 6,2 a 6,3.
- Premissas: Considerei apenas filmes que têm nota IMDb registrada (nota_imdb IS NOT NULL).; Agrupei por ano de lançamento (ano_lancamento) e calculei a média arredondada em duas casas decimais.
- Custo: 3 chamada(s), 10,675 tokens, 20.3 s

```sql
SELECT dm.ano_lancamento AS ano,
       ROUND(AVG(fmp.nota_imdb), 2) AS media_nota_imdb
FROM dim_movies dm
JOIN fact_movies_performance fmp USING (sk_movie_id)
WHERE fmp.nota_imdb IS NOT NULL
GROUP BY dm.ano_lancamento
ORDER BY dm.ano_lancamento
```

### ELE-01 — OK

**Pergunta:** Qual ator teve mais participações em filmes lançados nos últimos 5 anos?

- Verificação: ordem confere
- Resposta: O ator com mais participações em filmes lançados nos últimos 5 anos foi Eric Roberts, com 65 filmes exibidos nesse período.
- Premissas: Considerei apenas filmes cujo status seja 'Lançado' e cuja data de lançamento esteja entre a data atual (2026-10-01) e 5 anos atrás.; Contagem de participações por ator foi feita usando COUNT(DISTINCT sk_movie_id).
- Custo: 3 chamada(s), 10,689 tokens, 14.8 s

```sql
WITH filmes_recente AS (
    SELECT dm.sk_movie_id, dm.titulo, dm.ano_lancamento
    FROM dim_movies dm
    WHERE dm.status_filme = 'Lançado'
      AND dm.data_lancamento BETWEEN date('now', '-5 years') AND date('now')
)
SELECT dp.nome_pessoa AS ator,
       COUNT(DISTINCT f.sk_movie_id) AS participacoes
FROM filmes_recente f
JOIN bridge_movie_person bmp ON bmp.sk_movie_id = f.sk_movie_id
JOIN dim_people dp ON dp.sk_person_id = bmp.sk_person_id
WHERE dp.tipo_pessoa = 'Ator'
GROUP BY dp.nome_pessoa
ORDER BY participacoes DESC, dp.nome_pessoa ASC
LIMIT 1
```

### ELE-02 — OK

**Pergunta:** Quais diretores têm a maior nota média, considerando um mínimo de 5 filmes?

- Verificação: valores conferem
- Resposta: Os diretores com as maiores notas médias (IMDb) entre aqueles que dirigiram ao menos 5 filmes são: Scott Wozniak (média 9,34 em 5 filmes), Yūichirō Hayashi (9,19 em 8 filmes) e Jun Shishido (9,19 em 8 filmes). Eles lideram a lista, seguidos por Trevor L. Allen (9,15 em 8 filmes) e Alonso O. Lara (9,09 em 17 filmes).
- Premissas: Considerei apenas diretores com 5 ou mais filmes dirigidos (contagem distinta de filmes).; A nota média usada foi a nota IMDb (nota_imdb) presente na tabela fact_movies_performance.; Incluí todos os filmes do catálogo, independentemente do status de lançamento.
- Custo: 3 chamada(s), 11,457 tokens, 42.1 s

```sql
SELECT p.nome_pessoa AS diretor,
       ROUND(AVG(f.nota_imdb),2) AS media_nota_imdb,
       COUNT(DISTINCT d.sk_movie_id) AS qtd_filmes
FROM dim_people p
JOIN bridge_movie_person bmp ON p.sk_person_id = bmp.sk_person_id
JOIN dim_movies d ON bmp.sk_movie_id = d.sk_movie_id
JOIN fact_movies_performance f ON d.sk_movie_id = f.sk_movie_id
WHERE p.tipo_pessoa = 'Diretor'
GROUP BY p.sk_person_id, p.nome_pessoa
HAVING COUNT(DISTINCT d.sk_movie_id) >= 5
ORDER BY media_nota_imdb DESC
LIMIT 10
```

### ELE-03 — OK

**Pergunta:** Qual dupla ator–diretor mais trabalhou junta?

- Verificação: ordem confere
- Resposta: A dupla ator‑diretor que mais trabalhou junta na base é Joe Anoa'i (ator) e Kevin Dunn (diretor), com 37 filmes em comum.
- Custo: 4 chamada(s), 14,315 tokens, 11.2 s

```sql
WITH atores AS (
  SELECT bm.sk_movie_id, p.nome_pessoa AS ator
  FROM bridge_movie_person bm
  JOIN dim_people p ON bm.sk_person_id = p.sk_person_id
  WHERE p.tipo_pessoa = 'Ator'
), diretores AS (
  SELECT bm.sk_movie_id, p.nome_pessoa AS diretor
  FROM bridge_movie_person bm
  JOIN dim_people p ON bm.sk_person_id = p.sk_person_id
  WHERE p.tipo_pessoa = 'Diretor'
)
SELECT a.ator AS ator, d.diretor AS diretor, COUNT(DISTINCT a.sk_movie_id) AS qtd_filmes
FROM atores a
JOIN diretores d ON a.sk_movie_id = d.sk_movie_id
GROUP BY a.ator, d.diretor
ORDER BY qtd_filmes DESC
LIMIT 1
```

### GEN-01 — OK

**Pergunta:** Qual a quantidade de filmes por gênero?

- Verificação: mapeamento confere
- Resposta: A contagem de filmes por gênero mostra que o Drama é o mais representado, com 28.086 títulos, seguido por Documentário (18.082), Comédia (16.048), Terror (8.674) e Thriller (8.540). Os demais gêneros variam de 6.209 (Romance) a 3.336 (Tv Movie). No total, a base contém 19 gêneros diferentes.
- Custo: 3 chamada(s), 10,313 tokens, 3.6 s

```sql
SELECT g.nome_genero AS genero, COUNT(DISTINCT b.sk_movie_id) AS quantidade_filmes
FROM bridge_movie_genre b
JOIN dim_genres g ON b.sk_genre_id = g.sk_genre_id
GROUP BY g.nome_genero
ORDER BY quantidade_filmes DESC
```

### GEN-02 — OK

**Pergunta:** Qual produtora teve o maior lucro total?

- Verificação: ordem confere
- Resposta: A produtora que acumulou o maior lucro total foi a Marvel Studios, com aproximadamente R$ 66,5 bilhões de lucro acumulado nos filmes que têm receita informada.
- Premissas: Considerei apenas filmes com receita_brl informada, conforme a regra de confiabilidade para lucro.; Somamos o lucro_brl de todos os filmes associados a cada produtora.
- Custo: 3 chamada(s), 10,519 tokens, 3.1 s

```sql
SELECT c.nome_produtora AS produtora,
       ROUND(SUM(f.lucro_brl), 2) AS lucro_total_brl
FROM dim_companies c
JOIN bridge_movie_company bc ON c.sk_company_id = bc.sk_company_id
JOIN fact_movies_performance f ON bc.sk_movie_id = f.sk_movie_id
WHERE f.receita_brl IS NOT NULL
GROUP BY c.sk_company_id, c.nome_produtora
ORDER BY lucro_total_brl DESC
LIMIT 1
```

### GEN-03 — OK

**Pergunta:** Qual gênero tem a maior margem de lucro média?

- Verificação: ordem confere
- Resposta: O gênero com a maior margem de lucro média é **War**, com uma margem média de aproximadamente **‑5,35** (ou seja, em média os filmes desse gênero tiveram prejuízo). Como a margem é calculada dividindo o lucro pela receita, valores muito baixos de receita podem gerar margens extremamente negativas, o que distorce a média.
- Premissas: Considerei apenas filmes com receita_brl e orçamento_brl informados e maiores que zero.; A margem média foi calculada como AVG(lucro_brl / receita_brl) por gênero.
- Custo: 3 chamada(s), 10,843 tokens, 3.4 s

```sql
SELECT g.nome_genero AS genero,
       ROUND(AVG(lucro_brl*1.0/receita_brl),4) AS margem_media
FROM dim_movies m
JOIN fact_movies_performance f USING (sk_movie_id)
JOIN bridge_movie_genre bg USING (sk_movie_id)
JOIN dim_genres g USING (sk_genre_id)
WHERE f.receita_brl IS NOT NULL
  AND f.receita_brl > 0
  AND f.orcamento_brl > 0
GROUP BY g.nome_genero
ORDER BY margem_media DESC
LIMIT 1
```

### AVA-01 — OK

**Pergunta:** Quais filmes foram mais avaliados pelos usuários?

- Verificação: valores conferem
- Resposta: Os registros com maior número de avaliações de usuários são todos da série *Die Hart* de 2024. O primeiro aparece com 13 avaliações e nota média 4,99; em seguida, o mesmo título aparece com 12 avaliações (nota 6,49) e depois com 11 avaliações (nota 5,56). Há ainda várias entradas com 10 avaliações, variando entre notas médias de 4,04 a 5,97. Observe que a base contém duplicatas desses filmes, o que faz com que eles dominem o ranking dos mais avaliados.
- Premissas: Considerei todos os filmes que possuem avaliações de usuários (dim_reviews).; Ordenei pelos maiores valores de qtd_avaliacoes_usuarios e limitei a 10 registros, conforme a consulta executada.; Não apliquei filtro mínimo de avaliações, pois a pergunta pede apenas os mais avaliados.
- Custo: 4 chamada(s), 16,173 tokens, 5.6 s

```sql
SELECT dm.titulo || ' (' || dm.ano_lancamento || ')' AS filme,
       dr.qtd_avaliacoes_usuarios AS qtd_avaliacoes,
       ROUND(dr.nota_media_usuarios,2) AS nota_media
FROM dim_movies dm
JOIN dim_reviews dr USING (sk_movie_id)
ORDER BY dr.qtd_avaliacoes_usuarios DESC, dm.titulo
LIMIT 10
```

### AVA-02 — FALHA

**Pergunta:** Em quais filmes a nota média dos usuários mais diverge da nota IMDb?

- Verificação: Os modelos de IA estão indisponíveis no momento (limite de uso ou instabilidade do provedor). Tente novamente em instantes.
