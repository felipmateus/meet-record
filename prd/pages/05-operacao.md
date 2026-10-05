# Operação e diagnóstico

> **Comandos:** `trec status`, `trec doctor`, `trec purge`, `trec version`
> **Módulo:** Operação · **Gerado:** 2026-10-05

## `trec status`
Lista a pasta de dados, se a chave da API está configurada, as reuniões com estado derivado e a próxima etapa pendente, a gravação em andamento (se houver) e o número de ações abertas.

| Coluna | Formato |
|---|---|
| id | `AAAA-MM-DD_HH-MM-SS` |
| título | quando informado |
| estado | `recording` · `recorded` · `transcribed` · `analyzed` · `failed` |
| próximo | `stop` · `transcribe` · `analyze` · vazio |

`[TBC]` Soma do gasto estimado do mês a partir de `llm_usage.jsonl` está prevista para a fase 7.

## `trec doctor`
Verifica, com `ok`/`FALTA`/`info`: ffmpeg, whisper-cli, swift, osascript, teams-tap compilado, Claude Code CLI (e o provedor atual), modelo whisper, modelo VAD, chave da API (exigida só com provedor `api`), permissão do `.env` (aviso se diferente de 600) e a pasta de dados. Código 0 só se tudo que o provedor atual exige está presente.

## `trec purge`
Apaga `audio.m4a` de reuniões com mais de `planner.retention_days` (30) dias que já tenham `transcript.json`. Lista os ids afetados. Transcrição e análise permanecem.

## `trec version`
Imprime a versão do pacote.

## Relações
Consulta e manutenção sobre o estado produzido por [Gravação](./01-gravacao-manual.md), [Transcrição](./02-transcricao.md), [Análise](./03-analise.md) e [Automação](./04-automacao.md).
