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

# 3. Banco de dados: baixe o cinerocket.db (link do Drive da atividade) em data/cinerocket.db
python scripts/prepare_db.py    # valida as tabelas e cria índices (~10 s, uma única vez)

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

## Estrutura

```
src/cinedata_agent/      pacote principal
  semantic_layer.py      significado de negócio das tabelas (fonte do prompt e do dicionário)
  golden.py              modelo do conjunto de avaliação
  db_setup.py            preparação do banco (índices, estatísticas)
  guardrails.py          validação da SQL gerada pelo LLM
  db.py                  execução somente leitura (authorizer, timeout, teto de linhas)
  agent.py               agente Pydantic AI (ferramentas, fallback de modelos, validação ReAct)
  grounding.py           verificação anti-alucinação (números e nomes precisam estar nos dados)
  prompts/               system prompt versionado
  evaluation.py          comparação com as SQLs de referência (execution accuracy)
eval/golden.yaml         22 perguntas de avaliação com SQL de referência
scripts/                 utilitários (preparar banco, cota, benchmark de modelos)
tests/                   testes automatizados
docs/decisoes.md         decisões técnicas e evidências
docs/dicionario_dados.md dicionário de dados (gerado)
data/                    banco SQLite local (ignorado pelo git)
```
