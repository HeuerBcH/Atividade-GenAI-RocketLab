# CineData Agent — Text-to-SQL sobre a camada Gold

Agente de IA que responde, em português, perguntas de negócio sobre o catálogo de filmes da
CineData Analytics, gerando e executando SQL somente leitura sobre a camada Gold (SQLite).

> 🚧 Em construção. Documentação completa ao final do desenvolvimento.

## Setup

Pré-requisitos: **Python 3.11+** e uma chave gratuita do [Groq](https://console.groq.com/keys)
(ou do [OpenRouter](https://openrouter.ai/keys), com `LLM_PROVIDER=openrouter`).

```bash
# 1. Ambiente virtual e dependências
python -m venv .venv
.venv\Scripts\activate          # Windows  |  source .venv/bin/activate (Linux/macOS)
pip install -r requirements.txt

# 2. Configuração
cp .env.example .env            # preencha GROQ_API_KEY

# 3. Banco de dados: baixe o cinerocket.db (link do Drive da atividade) e salve em
#    data/cinerocket.db. Nenhum preparo é necessário: o arquivo é aberto somente leitura.

# 4. Verificações
python scripts/list_models.py   # modelos disponíveis no provedor (não consome cota)
pytest                          # testes (sem LLM: não consomem cota)
```

> O banco (~580 MB) não é versionado porque excede o limite de arquivo do GitHub.

## Uso (linha de comando)

```bash
python -m cinedata_agent "Quais são os 10 filmes com maior receita em R$?"
python -m cinedata_agent "Qual dupla ator-diretor mais trabalhou junta?" --trace   # passos do ReAct
python -m cinedata_agent "..." --json                                              # resposta completa
```

## Interface de chat (React)

Requer **Node.js 20+**. Com a API rodando (seção abaixo), em outro terminal:

```bash
cd frontend
npm install
npm run dev                                     # abre http://localhost:5173
```

Chat com memória da conversa, perguntas de exemplo por categoria, gráfico automático, tabela com
download em CSV, e a SQL e os passos do agente (ReAct) em seções expansíveis. Se a API não estiver
em `http://localhost:8000`, copie `frontend/.env.example` para `frontend/.env` e ajuste
`VITE_API_BASE` (e `CORS_ORIGINS` no `.env` da API, se o frontend usar outra porta).

## API (FastAPI)

```bash
uvicorn cinedata_agent.api:app --port 8000      # documentação interativa em http://localhost:8000/docs
```

| Rota | O que faz |
|---|---|
| `POST /ask` | `{"question": "...", "session_id": "opcional"}` → resposta, premissas, SQL, linhas e passos do ReAct |
| `DELETE /sessions/{id}` | apaga a memória de uma conversa |
| `GET /health` | provedor, modelos e versão do prompt em uso |
| `GET /schema` | tabelas, colunas e regras de negócio |
| `GET /examples` | perguntas de exemplo |

Com Docker (o banco entra como volume somente leitura):

```bash
docker compose up --build                       # API em http://localhost:8000
```

## Estrutura

```
src/cinedata_agent/      pacote principal
  semantic_layer.py      significado de negócio das tabelas (fonte do prompt e do dicionário)
  golden.py              modelo do conjunto de avaliação
  guardrails.py          validação da SQL gerada pelo LLM
  db.py                  acesso somente leitura ao banco (validação, authorizer, timeout)
  agent.py               agente Pydantic AI (ferramentas, fallback de modelos, validação ReAct)
  grounding.py           verificação anti-alucinação (números e nomes precisam estar nos dados)
  prompts/               system prompt versionado
  evaluation.py          comparação com as SQLs de referência (execution accuracy)
  service.py             memória por sessão, cache de respostas e log de execuções
  api.py                 API FastAPI
eval/golden.yaml         22 perguntas de avaliação com SQL de referência
frontend/                interface de chat (React + Vite + Tailwind + Recharts)
scripts/                 utilitários (preparar banco, cota, benchmark de modelos)
tests/                   testes automatizados
docs/decisoes.md         decisões técnicas e evidências
docs/dicionario_dados.md dicionário de dados (gerado)
data/                    banco SQLite local (ignorado pelo git)
```
