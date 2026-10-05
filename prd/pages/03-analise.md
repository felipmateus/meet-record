# Análise da reunião

> **Comando:** `trec analyze [id]`
> **Módulo:** Análise · **Gerado:** 2026-10-05

## Visão geral
Transforma a transcrição em um registro estruturado do que importa para o usuário: resumo, decisões, ações dele, ações de terceiros a acompanhar, prazos, perguntas em aberto e próximas reuniões. É o insumo do plano diário.

## Campos e opções
| Argumento / config | Tipo | Padrão | Descrição |
|---|---|---|---|
| `id` | texto | todas em estado `transcribed` | Reunião específica |
| `llm.provider` | `api` \| `claude-code` | `api` | Transporte: Claude API (chave no `.env`) ou Claude Code headless (assinatura). Sobrescrevível por `TREC_LLM_PROVIDER` |
| `llm.model` / `llm.cli_model` | texto | `claude-opus-5-5` / `opus` | Modelo por provedor |
| `llm.effort` | low…max | `high` | Profundidade de raciocínio |
| `llm.max_tokens` | inteiro | 16000 | Teto de saída (API) |

## Saída estruturada (esquema)
| Campo | Tipo | Regra de extração |
|---|---|---|
| `summary` | texto | 3 a 6 frases, objetivo |
| `decisions[]` | texto | só o efetivamente decidido |
| `my_actions[]` | descrição, responsável (`usuário`), prazo ISO ou nulo | compromissos do usuário; verbo no infinitivo |
| `others_actions[]` | descrição, responsável, prazo | tarefas de terceiros que afetam o usuário; `indefinido` quando não identificável |
| `deadlines[]` | o quê, quando (ISO ou nulo), quem | expressões relativas convertidas pela data da reunião informada no prompt |
| `open_questions[]` | texto | dúvidas não respondidas |
| `next_meetings[]` | texto | encontros combinados |

Cada ação recebe um id curto único e `status = open`. O prompt instrui explicitamente a não inventar tarefas, prazos ou decisões.

## Interações
- **Pré-validação:** provedor `api` exige a chave; `claude-code` exige o executável `claude` no PATH. Mensagens apontam a alternativa.
- **Curto-circuito:** transcrição vazia ou com menos de 20 palavras recebe análise local ("Transcrição muito curta …") sem chamada ao modelo.
- **Chamada (API):** prompt de sistema fixo e cacheado; mensagem do usuário com data, dia da semana, hora, título, duração e a transcrição com tempos; saída forçada por JSON Schema (objetos fechados, todos os campos obrigatórios); fallback de servidor para recusas pontuais do classificador de segurança; validação Pydantic do lado do cliente.
- **Chamada (Claude Code):** mesmo prompt e esquema via `claude -p --output-format json --json-schema`, modo restrito e sem ferramentas.
- **Erros explícitos:** recusa final, resposta truncada, saída fora do esquema, autenticação, limite de requisições, conexão. Viram `error.txt` na reunião.
- **Registro de uso:** tokens de entrada/saída/cache e custo (ou equivalente) em `data/log/llm_usage.jsonl`.
- **Saída no terminal:** provedor em uso, contagens, resumo e a lista de ações do usuário com prazos.

## Integrações
| Integração | Uso |
|---|---|
| Claude API (SDK `anthropic` 1.x) | `beta.messages.create` com `output_config.format`, `cache_control`, `fallbacks="default"` |
| Claude Code CLI | `claude -p` headless |

## Relações
- **De:** [Transcrição](./02-transcricao.md). **Para:** [Plano diário](./06-plano-diario.md) (estado `analyzed`).

## Regras de negócio
- Só o texto da transcrição e o prompt saem do Mac.
- Com Claude Code, não há fallback de recusa e a análise depende de sessão logada no Mac (relevante para o daemon).
