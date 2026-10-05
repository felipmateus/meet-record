# Layout de dados e esquemas

```
<data_dir>/                           # <projeto>/data, ou ~/Library/Application Support/teams-recorder se o projeto estiver no iCloud
├── current_recording.json            # ponteiro da gravação ativa (no máximo uma)
├── recordings/<AAAA-MM-DD_HH-MM-SS>/ # uma pasta por reunião (ver dicionário)
├── planos/
│   ├── AAAA-MM-DD.md / .json         # plano diário (fase 6)
│   └── acoes_abertas.json            # ações acumuladas
├── models/                           # ggml-*.bin (whisper, VAD)
└── log/
    ├── teams-recorder.log            # daemon (rotação diária, 30 dias)
    ├── daemon.out.log / daemon.err.log
    ├── capture.log                   # stderr dos gravadores
    └── llm_usage.jsonl               # uma linha por chamada à LLM
```

## `meta.json`
```json
{"id": "2026-10-05_12-29-37", "started_at": "2026-10-05T12:29:37", "ended_at": "2026-10-05T12:30:50", "pid": 32663, "title": null}
```

## `current_recording.json`
```json
{"meeting_id": "…", "process_handle": {"pid": 123, "out": "…/tap.wav"}, "mic_handle": {"pid": 124, "out": "…/mic.wav"}}
```

## `transcript.json`
```json
{"language": "pt", "segments": [{"start": 0.0, "end": 3.2, "text": "Bom dia, pessoal."}]}
```
`transcript.txt`: `[hh:mm:ss] texto` por segmento.

## `analysis.json`
```json
{
  "meeting_id": "…", "summary": "…",
  "decisions": ["…"],
  "my_actions": [{"id": "f5350aee", "description": "Enviar o relatório de integração", "owner": "usuário", "source_meeting": "…", "due": "2026-10-07", "status": "open"}],
  "others_actions": [{"id": "…", "description": "…", "owner": "Mariana", "source_meeting": "…", "due": null, "status": "open"}],
  "deadlines": [{"what": "…", "when": "2026-10-07", "who": "usuário"}],
  "open_questions": ["…"], "next_meetings": ["…"]
}
```

## `planos/AAAA-MM-DD.json` (fase 6)
```json
{"day": "2026-10-06", "markdown": "# …", "priorities": ["…"], "new_actions": [Action…], "completed_action_ids": ["…"], "overdue_action_ids": ["…"]}
```

## `llm_usage.jsonl` (uma linha por chamada)
```json
{"ts": "…", "meeting": "…", "provider": "claude-code", "model": "claude-opus-5", "input": 2, "output": 406, "cache_read": 1991, "cache_write": 692, "cost_usd_equiv": 0.054, "stop": "success", "session_id": "…"}
```
No provedor `api`: `request_id` em vez de `session_id`, sem `provider`/`cost_usd_equiv`.

## Escrita
Todos os JSON são gravados de forma atômica (arquivo temporário + rename). Arquivos `*.tmp` são ignorados nas listagens.
