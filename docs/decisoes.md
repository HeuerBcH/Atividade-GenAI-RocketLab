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
