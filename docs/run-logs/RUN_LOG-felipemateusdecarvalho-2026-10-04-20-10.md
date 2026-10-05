# RUN_LOG — felipemateusdecarvalho — 2026-10-04 20:10

Atividade: entrevista de requisitos técnicos e definição de arquitetura do projeto teams-recorder. Resultado consolidado em `docs/REQUISITOS-E-ARQUITETURA.md`.

## Rodada 1 — Fundamentos

| Pergunta | Resposta do usuário |
|----------|---------------------|
| Em qual pasta o projeto deve ficar no seu Mac? | ~/Documents/teams-recorder |
| Quais linguagens o projeto deve usar? | Python + Swift mínimo |
| Como capturar o áudio dos participantes do Teams? | Core Audio Process Tap |
| Qual LLM fará a análise e o planejamento? | Claude API |

## Rodada 2 — Arquitetura do código

| Pergunta | Resposta do usuário |
|----------|---------------------|
| Como organizar o código Python? | Arquitetura hexagonal |
| Como as etapas devem se comunicar e guardar estado? | Só arquivos |
| Onde guardar configuração e segredos? | Arquivo .env |
| Qual nível de testes automatizados? | pytest com fixtures (alvo 70%) |

## Rodada 3 — Requisitos funcionais

| Pergunta | Resposta do usuário |
|----------|---------------------|
| Como detectar que uma reunião do Teams começou e terminou? | Heurística do sistema (pmset + microfone) |
| O que fazer com o áudio depois de transcrito? | Apagar áudio após 30 dias |
| Onde o plano de atividades deve ser entregue? | Markdown local |
| Em que idioma são as reuniões? | Só português |

## Observações registradas
- Usuário optou por `.env` em vez de Keychain e por `~/Documents` como pasta; riscos R1 (iCloud) e R2 (chave em texto puro) documentados com mitigações.
- Sessão movida para `~/Documents/teams-recorder` (pasta criada vazia nesta data).
