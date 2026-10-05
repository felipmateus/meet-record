# Plano diário (fase 6 — pendente)

> **Comando previsto:** `trec plan [--date AAAA-MM-DD]` · agendamento diário às 18h (dias úteis) via LaunchAgent
> **Módulo:** Planejamento · **Gerado:** 2026-10-05 · **Status:** caso de uso, modelo de dados, prompt e testes existem; faltam adaptador, comando e agendamento

## Visão geral
Uma vez por dia, consolida as análises das reuniões do dia, o plano do dia anterior e a lista acumulada de ações abertas num plano de atividades em Markdown, e atualiza a lista de ações (novas, concluídas, vencidas).

## Entradas
| Entrada | Origem | Regra |
|---|---|---|
| Análises do dia | reuniões com `started_at` no dia e estado `analyzed` | só reuniões analisadas contam |
| Plano anterior | último `data/planos/<data>.json` anterior ao dia | pode não existir |
| Ações abertas | `data/planos/acoes_abertas.json` | lista acumulada entre dias |

## Saída
| Artefato | Conteúdo |
|---|---|
| `data/planos/AAAA-MM-DD.md` | Título com a data; seções **Prioridades** (3 a 5), **Ações novas**, **Vencidas**, **Conflitos e alertas** (quando houver) |
| `data/planos/AAAA-MM-DD.json` | prioridades, ações novas, ids concluídos, ids vencidos, markdown |
| `acoes_abertas.json` atualizado | remove concluídas, marca vencidas (`status = overdue`), acrescenta novas sem duplicar ids |

## Regras do planejamento (prompt já escrito em `prompts/plan_system.md`)
- Prioriza por prazo e impacto: vencido/vencendo primeiro, depois o que destrava terceiros, depois o resto.
- Não inventa ações: toda ação nova vem de uma análise do dia; concluída/vencida corresponde a um id da lista aberta.
- Marca concluída só com indicação clara em alguma análise; vencida quando o prazo passou na data do plano.
- Português do Brasil, direto.

## Interações previstas
- `trec plan` sem data: hoje. Com `--date`: refaz o plano daquele dia (substitui arquivos do dia).
- Notificação "Plano do dia pronto: N reunião(ões), M ação(ões) nova(s)".
- Agendador: segundo LaunchAgent (`local.teams-recorder.planner`) com `StartCalendarInterval` às 18:00 em dias úteis executando `trec plan`; também executa `trec purge`.
- Dia sem reuniões analisadas: gera plano só com ações abertas e vencidas (`[TBC]` confirmar na implementação).

## Integrações
Mesmo provedor da análise (API ou Claude Code), com saída estruturada por esquema.

## Relações
- **De:** [Análise](./03-analise.md). **Para:** o usuário lê o Markdown; integrações (To Do, Obsidian) ficam para depois da fase 7.
