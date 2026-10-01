# Registro de decisões técnicas

Cada decisão registra o contexto, a escolha e a evidência que a sustenta.

## D1 — Stack: Pydantic AI + OpenRouter (modelos `:free`) + FastAPI

- **Framework de agentes: Pydantic AI.** Tool calling com validação por tipos, saída estruturada,
  `FallbackModel` nativo (troca de modelo em caso de 429), `UsageLimits` (teto de chamadas por
  pergunta) e `TestModel`/`FunctionModel`, que permitem testar o agente **sem gastar cota**.
  Com o limite de 50 requisições/dia, esse último ponto foi decisivo.
- **Modelo: OpenRouter `:free`**, conforme sugerido pela atividade. A ordem da cadeia de fallback
  será definida por benchmark na Fase 3 (ver D4, a preencher).
- **Entregável: módulo backend FastAPI + CLI**, ambos sobre o mesmo pacote `cinedata_agent`.

## D2 — Banco: preparação de leitura sem alterar dados da camada Gold

**Contexto.** As perguntas de elenco e equipe juntam `bridge_movie_person` (745 mil linhas) com
`dim_people` (425 mil) usando chaves texto de 64 caracteres. Na primeira medição, a pergunta
"dupla ator–diretor que mais trabalhou junta" levou **~60 s**, o que inviabiliza o uso interativo.
O arquivo também é distribuído em modo **WAL**, que complica a abertura somente leitura.

**Decisão.**

1. **PRAGMAs em cada conexão de leitura** (`temp_store=MEMORY`, `cache_size` 256 MiB,
   `mmap_size` 1 GiB). Sozinhos, levam a consulta de ~60 s para ~7–9 s: o gargalo era I/O e a
   ordenação em disco.
2. **Índices de cobertura** para os caminhos pessoa→filme, gênero→filme e produtora→filme, mais
   `ANALYZE` para o otimizador escolher bons planos. Geram ganho adicional de 1,5–3x
   (dupla ator–diretor ~4,5–6,7 s; diretores por nota 0,48 → 0,20 s).
3. **`journal_mode=DELETE`**, para que `mode=ro` funcione sem arquivos `-wal`/`-shm`.

Tudo é **aditivo e idempotente** (`scripts/prepare_db.py`): nenhum dado ou índice original é
alterado. Custo: ~8 s uma única vez e ~220 MB a mais no arquivo.

**Alternativas descartadas.**
- *Tabelas pré-agregadas* (ex.: pares ator–diretor): rápidas, mas criariam uma camada fora da Gold e
  o agente perderia flexibilidade para perguntas não previstas.
- *Só aumentar o timeout*: esconde o problema e prejudica a experiência do usuário.

## D3 — Cota do OpenRouter como recurso planejado

- `scripts/check_quota.py` consulta `GET /key`, que **não consome cota**, antes de cada bateria.
- Testes que chamam a API real recebem o marcador `live` e **não rodam por padrão** (`pytest`
  executa só os testes offline; `pytest -m live` executa os demais).

## D4 — Escolha e ordem dos modelos *(a preencher na Fase 3, com benchmark)*

## D5 — Convenções de negócio derivadas do profiling dos dados

Todas vivem em `src/cinedata_agent/semantic_layer.py` (fonte única para o prompt e para o
[dicionário de dados](dicionario_dados.md)). As principais, com a evidência que as motivou:

| Convenção | Evidência no banco |
|---|---|
| Critério explícito na pergunta prevalece sobre o padrão | O enunciado fixa critérios (ex.: "mínimo de 5 filmes"), que não podem ser sobrescritos. |
| Lucro só com receita informada | `lucro_brl` nunca é NULL: vale 0 sem receita e orçamento, **−orçamento** sem receita (6.296 filmes) e **= receita** sem orçamento (1.743). |
| Margem = lucro / receita, com receita e orçamento > 0 | O topo tem orçamentos de R$ 20–700 (erro na fonte) e a margem mínima é −54.090. O agente avisa sobre esses outliers. |
| Moeda padrão R$, sem conversão manual | A taxa BRL/USD varia de 3,0 a 5,8 entre os filmes (câmbio histórico). |
| Comparar notas exige ≥ 100 votos (IMDb/TMDB) | 33 mil filmes têm 0 votos no TMDB; sem mínimo, o ranking de divergência é ruído. |
| Nota de usuários exige ≥ 3 avaliações | 93% dos filmes avaliados têm uma única avaliação (máximo: 13). |
| Gêneros traduzidos PT → EN | `dim_genres` está em inglês; as perguntas chegam em português. |
| Agrupar por `sk_*` e exibir título + ano | 1.518 grupos de título+ano duplicados; 48 mil nomes aparecem em mais de um papel. |
| `idioma_original` não deve ser usado | A coluna é 100% NULL. |

**Qualidade de dados: avisar em vez de corrigir.** Há popularidade corrompida (4 filmes com o
ano gravado no lugar do índice, ex.: "La Fellinette" = 2020.0) e cadastros duplicados na fonte
(dezenas de "Die Hart 2: Die Harter"). A camada Gold é a fonte de verdade da atividade, então
o agente **não altera nem filtra** esses registros silenciosamente: ele responde com os dados e
avisa o usuário quando o problema afeta a resposta.

## D6 — Avaliação por execution accuracy

`eval/golden.yaml` tem as **14 perguntas do enunciado** e **8 casos de robustez** (tradução de
gênero, entidade em minúsculas, follow-up, pergunta ambígua, fora de escopo, comando destrutivo e
prompt injection), cada um com a SQL de referência escrita à mão.

- Compara-se o **resultado** da SQL do agente com o da referência, e não o texto da SQL (consultas
  diferentes podem estar igualmente certas). Os modos de comparação (`ordered`, `set`, `values`,
  `mapping`, `scalar`, `refusal`) estão documentados em `src/cinedata_agent/golden.py`.
- Empates são tratados explicitamente: um teste garante que nenhum caso `ordered` tem empate na
  posição de corte, e rankings com empate usam o modo `values`.
- `tests/test_golden.py` valida o arquivo e executa cada SQL de referência no banco real (sem LLM,
  custo zero de cota), garantindo que o resultado não expõe chaves `sk_*` nem hashes.
