# Relações entre fluxos e estados

```
                 trec start / detector (IN_CALL ≥ 2)
   [—] ──────────────────────────────────────────▶ recording
                                                      │ trec stop / detector (IDLE ≥ 5) / SIGTERM do daemon
                                                      ▼
                                                   recorded ──▶ (purge após 30 d apaga só o áudio)
                                                      │ trec transcribe / pipeline
                                                      ▼
                                                  transcribed
                                                      │ trec analyze / pipeline
                                                      ▼
                                                   analyzed ──▶ trec plan (fase 6) ──▶ planos/<dia>.md + acoes_abertas.json
   qualquer etapa com erro ──▶ failed (error.txt) ──▶ repetir a etapa limpa o erro e segue
   trec cancel em recording ──▶ pasta removida
```

## Quem dispara o quê
| Origem | Alvo | Dados passados |
|---|---|---|
| Detector → daemon | `StartRecording` | PID do Teams |
| Daemon (fim de chamada) → pipeline | `StopRecording` → `TranscribeMeeting` → `AnalyzeMeeting` | `ActiveRecording` / id da reunião |
| Daemon (partida) → pipeline | `resume_pending` | reuniões em `recorded`/`transcribed` |
| `trec stop` (outro processo) | `StopRecording` | ponteiro `current_recording.json` |
| Agendador (fase 6) | `BuildDailyPlan`, `PurgeOldAudio` | data do dia |

## Acoplamentos de dados
- `acoes_abertas.json` é lido e reescrito só pelo plano diário.
- `llm_usage.jsonl` é só acrescido pelas análises (e pelo plano, na fase 6); `trec status` passará a lê-lo na fase 7.
- `config.toml` é lido a cada comando; o daemon precisa de `trec agent restart` para recarregar.
