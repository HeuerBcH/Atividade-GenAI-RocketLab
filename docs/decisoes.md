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

## D2 — Banco: preparação com índices *(substituída pela D11)*

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

## D4 — Escolha e ordem dos modelos

**Contexto.** O modelo `z-ai/glm-5.2:free`, citado no guia do bootcamp, não existe mais no
OpenRouter (verificado em 2026-10-01 via `GET /models`, que não consome cota). Dos 17 modelos
`:free`, 16 suportam tool calling.

**Benchmark preliminar** (`scripts/benchmark_models.py`, 3 casos: BIL-01, ELE-03, EXT-02, sem
raciocínio, 2026-10-01 ~19h30):

| Modelo | Resultado |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Acertou BIL-01 e, em nova execução, ELE-03 (o caso mais difícil). ~15 s por pergunta. |
| `nvidia/nemotron-3.5-lightning:free` | Acertou BIL-01; tende a responder **antes** de observar o resultado (ver D8). ~5–14 s. |
| `google/gemma-4-31b-it:free` | 429 no pool compartilhado do provedor em todas as chamadas (congestionamento, não qualidade). |
| `qwen/qwen3.8-27b:free` | Idem. |

**Decisão.** Cadeia `nemotron-3-ultra → nemotron-3.5-lightning → gemma-4-31b → qwen3.8-27b`, com
`temperature=0` e raciocínio `none`. O 429 dos modelos gratuitos é frequente, então o fallback
entre modelos é requisito, não luxo. A amostra é pequena: a avaliação completa (Fase 6) confirma
ou corrige a ordem.

## D8 — Garantia estrutural do ciclo ReAct (anti-alucinação)

**Problema observado em produção.** O `nemotron-3.5-lightning` pediu a consulta e, na mesma
resposta, enviou a resposta final, **inventando** filmes e números (Avatar, Titanic,
"popularidade 10.000+") que não estavam no resultado. Ele também ignorou
`parallel_tool_calls=False`.

**Decisão.** Um *output validator* rejeita (com `ModelRetry`) qualquer resposta final emitida
na mesma rodada de uma chamada de ferramenta. O modelo é forçado a observar o resultado antes de
responder, independentemente de obedecer às configurações. Também:
- A resposta exige um mínimo de caracteres (resposta vazia gera nova tentativa).
- Os dados exibidos ao usuário vêm **direto do banco**, nunca do texto do modelo.
- Teste de regressão: `test_answer_sent_with_a_tool_call_is_rejected`.

## D5 — Convenções de negócio derivadas do profiling dos dados

Todas vivem em `src/cinedata_agent/semantic_layer.py` (fonte única para o prompt e para o
[dicionário de dados](dicionario_dados.md)). As principais, com a evidência que as motivou:

| Convenção | Evidência no banco |
|---|---|
| Critério explícito na pergunta prevalece sobre o padrão | O enunciado fixa critérios (ex.: "mínimo de 5 filmes"), que não podem ser sobrescritos. |
| Lucro com receita **e** orçamento informados (só receita quando a pergunta disser "receita informada") | `lucro_brl` nunca é NULL: vale 0 sem receita e orçamento, **−orçamento** sem receita (6.296 filmes) e **= receita** sem orçamento (1.743). Somar esses casos mudaria o 3º lugar em "produtora com maior lucro total". |
| Margem = lucro / receita, com receita e orçamento > 0 | Critério do enunciado; no banco, os 1.630 filmes com receita e orçamento informados têm ambos > 0. |
| Moeda padrão R$, sem conversão manual | A taxa BRL/USD varia de 3,0 a 5,8 entre os filmes (câmbio histórico). |
| Divergência entre notas: só exige as duas notas não nulas | Sem mínimo de votos (ver abaixo). |
| Gêneros traduzidos PT → EN | `dim_genres` está em inglês; as perguntas chegam em português. |
| Agrupar por `sk_*` e exibir título + ano | 1.518 grupos de título+ano duplicados; 48 mil nomes aparecem em mais de um papel. |
| `idioma_original` não deve ser usado | A coluna é 100% NULL. |

**A camada Gold é usada como está.** Ela já chega tratada da etapa de Engenharia de Dados, então
o agente não exclui, corrige nem deduplica registros, não os classifica como erro e não aplica
filtros que a pergunta não peça. Versões anteriores exigiam um mínimo de votos (≥ 100 no
IMDb/TMDB, ≥ 3 avaliações de usuários) e avisavam sobre registros atípicos (popularidade igual ao
ano, cadastros repetidos, orçamentos extremos). Isso foi removido por ser um tratamento fora da
Gold: o enunciado não pede esses critérios. Quando um ranking fica dominado por empates ou por
amostras pequenas, o usuário pode pedir o critério explicitamente ("com pelo menos 100 votos"),
que prevalece sobre o padrão.

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

## D7 — Segurança da execução de SQL em três camadas

A SQL é gerada por um LLM, portanto é **entrada não confiável**. Em `guardrails.py` e `db.py`:

1. **Guardrail sintático:** um único comando, iniciado por `SELECT`/`WITH`. A separação de
   comandos usa um scanner que respeita strings e comentários (`WHERE titulo = 'A;B'` é válido).
   As mensagens de erro orientam o LLM a se corrigir.
2. **Authorizer do SQLite (allowlist):** só `SELECT`, leitura de colunas, funções e CTE
   recursiva. Todo o resto é negado **pelo motor**, inclusive `WITH x AS (...) DELETE ...`, que
   começa com `WITH` e passaria por qualquer filtro textual, além de `load_extension`.
3. **Conexão `mode=ro`:** mesmo sem as camadas anteriores, o arquivo não pode ser alterado
   (há um teste que desliga o authorizer e comprova isso).

Além disso, há um **timeout aplicado pelo motor** (`progress_handler`, 30 s por padrão), que
interrompe consultas descontroladas, e um **teto de linhas por `fetchmany`** (1.000 por padrão),
com indicação de truncamento.

**Alternativas descartadas.**
- *Lista de palavras proibidas por regex* (abordagem comum): rejeita consultas legítimas (um
  título como "Drop Dead Fred") e não é uma garantia real.
- *Anexar `LIMIT` ao texto da SQL*: pode quebrar consultas que terminam em comentário e muda o
  texto que o usuário vê. O `fetchmany` limita sem reescrever a consulta.

## D9 — Provedor: Groq como padrão, OpenRouter mantido como alternativa

O enunciado deixa o modelo **à escolha** e só *sugere* o OpenRouter. Optamos pelo **Groq** (plano
gratuito) como provedor padrão. A troca é feita por configuração (`LLM_PROVIDER=groq|openrouter`),
sem mudança de código: as duas cadeias de fallback, os parâmetros de geração (`temperature`,
nível de raciocínio via `groq_reasoning_effort` / `openrouter_reasoning`) e todas as garantias
(guardrails, validação de respostas) são as mesmas para os dois.

- O Groq não informa a cota por API: os limites por modelo ficam em
  <https://console.groq.com/settings/limits>. `scripts/list_models.py` lista os modelos ativos
  sem consumir cota.
- O nível de raciocínio só é enviado quando pedido (`REASONING_EFFORT` diferente de `none`),
  porque modelos sem raciocínio rejeitam o parâmetro.

## D10 — Tolerância zero a alucinação: verificação de fundamentação

Além do D8 (responder só depois de observar), **toda resposta é verificada contra os dados
antes de chegar ao usuário** (`grounding.py`, aplicada no *output validator* do agente):

- **Números:** cada número citado no texto (e nas premissas) precisa corresponder a um valor
  observado nos resultados das ferramentas, na pergunta ou num fato documentado da camada
  semântica. Formatos brasileiros ("R$ 12,4 bilhões", "2.994,4", "52%") e arredondamentos
  legítimos são aceitos. Marcadores de lista ("1.", "2º") não contam como dado.
- **Nomes próprios:** cada nome de 2+ palavras capitalizadas (filme, pessoa, produtora) precisa
  aparecer nos dados observados. Títulos traduzidos ("Avatar: O Caminho da Água") são rejeitados,
  porque não existem no banco.
- **Valores derivados** (somas, diferenças, percentuais) só são aceitos se vierem da SQL.

Resposta reprovada vira `ModelRetry` com a lista exata do que não foi encontrado. Se o modelo
insistir, o usuário recebe um erro claro: **nunca uma resposta com dado inventado**. A tabela
exibida vem sempre do banco, nunca do texto do modelo.

**Limitação conhecida:** nomes de uma única palavra ("Avatar") não são verificáveis com segurança
por texto livre e não são checados; o número associado a eles, sim.

## D11 — Banco original intacto, aberto com `immutable=1`

Substitui a D2. Comparando com a abordagem de um colega de turma, medimos a consulta mais pesada
(dupla ator–diretor) no **arquivo original, sem índices**, aberto com `mode=ro&immutable=1` e com
os PRAGMAs de leitura: **7,3 s**, contra ~5–7 s na cópia indexada. Quase todo o ganho vinha dos
PRAGMAs, que não alteram o arquivo.

**Decisão.** Usar o `cinerocket.db` exatamente como distribuído:

- O enunciado pede para "baixar o arquivo, colocá-lo na pasta e conectar": nenhum passo extra.
  O `prepare_db.py` era um passo que o avaliador poderia pular, deixando o projeto num estado
  diferente do testado.
- O arquivo não muda (SHA-256 `410f5beef6ab9fb3...` antes e depois da suíte de testes) e evita
  ~220 MB a mais.
- `immutable=1` dispensa travas e arquivos auxiliares. Como ele ignora o `-wal`, a conexão recusa
  abrir se houver um `-wal` com transações pendentes (mensagem clara em vez de dado perdido).
- A validação (arquivo existe, é SQLite, tem as 10 tabelas) roda **automaticamente** ao iniciar.

## D12 — `gpt-oss-120b` no Groq: respostas em texto e margem de chamadas

Observado com a resposta HTTP bruta (2026-10-01):

- Com saída só estruturada, o Pydantic AI exige uma ferramenta em toda rodada; o `gpt-oss` quer
  responder em texto e o Groq devolve `400 tool_use_failed`. **Decisão:** aceitar a resposta final
  também como texto (`output_type=[AgentOutput, str]`). O texto passa pela mesma verificação de
  fundamentação (D10), e um JSON escrito como texto é convertido no formato estruturado.
- Às vezes o modelo escreve a resposta no canal de raciocínio e encerra com `content=''`. Ele se
  recupera na rodada seguinte, mas isso consome chamadas. **Decisão:** teto de 10 chamadas por
  pergunta (era 5).
- Limites do plano gratuito por modelo: 1.000 requisições/dia, **8 mil tokens/minuto** e **200 mil
  tokens/dia**. Uma pergunta usa ~3,7 mil tokens por chamada; num 429 o SDK espera o tempo pedido
  pelo Groq e tenta de novo (até 3 vezes).

## D13 — Agente híbrido: SQL + busca semântica nas sinopses

**Contexto.** Perguntas sobre o *tema* de um filme ("filmes sobre viagem no tempo", "receita de
filmes de assalto a banco") não têm coluna para filtrar: o assunto só existe no texto da
`sinopse` (82 mil filmes com sinopse, em inglês, ~230 caracteres em média). Um `LIKE '%time%'`
erra nos dois sentidos: acha "time" em qualquer frase e não acha "travels to the future".

**Decisão.** Uma 3ª ferramenta, `buscar_por_sinopse(descricao, quantidade)`, faz busca por
significado (embeddings) e devolve os `id_filme` mais parecidos, que o agente usa na SQL
(`WHERE id_filme IN (...)`). O agente continua com 3 ferramentas, dentro do limite de ≤ 5.

- **Modelo `BAAI/bge-small-en-v1.5` via fastembed (ONNX, roda na CPU).** Sem torch: as
  dependências novas somam ~55 MB (onnxruntime 46 MB), contra mais de 2 GB do
  sentence-transformers. O modelo é em inglês, como as sinopses; o próprio LLM traduz o tema ao
  chamar a ferramenta ("viagem no tempo" → `"time travel"`).
- **Índice fora do banco**, gerado uma vez por `scripts/build_synopsis_index.py` e salvo em
  `data/synopsis_index.npz` (vetores normalizados em float16, ~65 MB). O `cinerocket.db` não é
  alterado (D11). Sem o índice, a API sobe normalmente e a ferramenta só avisa que ele falta.
- **Busca exata (força bruta):** produto escalar contra os 82 mil vetores, em ~8 ms (os vetores ficam em float32 na memória, ~126 MB; convertê-los a cada busca custava ~50 ms). Um índice
  aproximado (FAISS, HNSW) só compensaria com milhões de itens e traria mais uma dependência.
- **Resultado enxuto para o LLM:** 10 filmes por padrão, com título, ano, similaridade e um
  trecho de 100 caracteres (~400 tokens). O resultado volta em todas as chamadas seguintes da
  pergunta, então sinopses inteiras custariam cota a cada chamada.
- Os `id_filme` vêm do índice, não do LLM, e mesmo assim vão para a SQL como parâmetros.
  Títulos e similaridades devolvidos entram na verificação anti-alucinação (D10).

**Desempenho medido** (2026-10-02, CPU de 20 núcleos): gerar o índice em lotes aleatórios fazia
43 sinopses/s (~32 min). O gargalo era o *padding*: cada lote é completado até o texto mais
longo. Ordenar as sinopses por tamanho antes de montar os lotes levou a 153 sinopses/s (~9 min),
3,5x mais rápido. Paralelismo por processos e mais threads não ajudaram.

**Alternativas descartadas.**
- *FTS5/BM25:* sem dependências, mas é busca por palavras, não semântica.
- *Modelo multilíngue:* aceitaria a pergunta em português, mas é ~4x maior e mais lento; a
  tradução feita pelo LLM resolve o idioma de graça.
- *`all-MiniLM-L6-v2`:* ~2x mais rápido para indexar, porém com qualidade de recuperação menor.
