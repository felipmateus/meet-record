# teams-recorder — Requisitos e Arquitetura

Data: 2026-10-04 · Autor: Felipe Mateus de Carvalho (entrevista conduzida com Claude)

## 1. Objetivo

Gravar automaticamente o áudio de todas as reuniões do Microsoft Teams no MacBook, transcrever localmente, extrair ações e decisões com uma LLM e gerar um plano diário de atividades. Tudo roda em segundo plano, sem intervenção, com custo próximo de zero.

## 2. Decisões da entrevista

| # | Tema | Decisão | Observação |
|---|------|---------|------------|
| 1 | Pasta do projeto | `~/Documents/teams-recorder` | Ver risco R1 (iCloud) |
| 2 | Linguagens | Python 3.11 + Swift mínimo | Swift só no binário de captura |
| 3 | Captura do Teams | Core Audio Process Tap | Sem BlackHole, sem alterar roteamento |
| 4 | LLM | Claude API (Opus 5.5) | Sem fallback local nesta fase |
| 5 | Organização do código | Arquitetura hexagonal | Domínio isolado, portas e adaptadores |
| 6 | Estado e comunicação | Só arquivos | Status derivado da existência dos arquivos |
| 7 | Configuração e segredos | Arquivo `.env` | Ver risco R1 e R2 |
| 8 | Testes | pytest com fixtures, alvo 70% | Adaptadores falsos para LLM e áudio |
| 9 | Detecção de chamada | Heurística do sistema (pmset + microfone) | Sem acesso ao calendário |
| 10 | Retenção de áudio | Apagar após 30 dias | Transcrição e análise permanecem |
| 11 | Saída do plano | Markdown local | Integrações ficam para fase 2 |
| 12 | Idioma | Só português (pt-BR) | Whisper fixado em `pt` |

## 3. Requisitos funcionais

| ID | Requisito |
|----|-----------|
| RF01 | Detectar início e fim de chamada do Teams sem ação do usuário, em até 10 s do evento real. |
| RF02 | Capturar o áudio emitido pelo processo do Teams (participantes) e o microfone (usuário) em trilhas separadas. |
| RF03 | Mixar as duas trilhas num único arquivo M4A (AAC, 64 kbps, mono) ao fim da chamada. |
| RF04 | Permitir cancelar a gravação em andamento por comando CLI; o áudio parcial é descartado. |
| RF05 | Transcrever o áudio em português com marcação de tempo por segmento, gerando `transcript.txt` e `transcript.json`. |
| RF06 | Enviar a transcrição à Claude API e receber uma análise estruturada: resumo, decisões, ações do usuário, ações de terceiros a acompanhar, prazos, perguntas abertas, próximos encontros. |
| RF07 | Gerar, uma vez por dia em horário configurável, um plano em Markdown consolidando as análises do dia, o plano anterior e as ações ainda abertas. |
| RF08 | Manter uma lista acumulada de ações abertas em `planos/acoes_abertas.json`, atualizada a cada plano. |
| RF09 | Notificar via Central de Notificações do macOS no início e no fim da gravação e quando o plano diário estiver pronto. |
| RF10 | Reprocessar qualquer etapa por comando CLI a partir dos arquivos existentes (`trec transcribe`, `trec analyze`, `trec plan`). |
| RF11 | Apagar `audio.m4a` de reuniões com mais de 30 dias que já tenham transcrição. |
| RF12 | Exibir status por CLI: daemon ativo, última reunião, etapas pendentes, validade da chave de API. |
| RF13 | Registrar cada etapa em log com data, reunião e resultado. |

## 4. Requisitos não funcionais

| ID | Requisito |
|----|-----------|
| RNF01 | Áudio e transcrição nunca saem do Mac; só a transcrição em texto é enviada à Claude API. |
| RNF02 | Nenhuma alteração no dispositivo de saída de áudio nem no controle de volume do usuário. |
| RNF03 | O daemon consome menos de 1% de CPU em espera e menos de 100 MB de RAM. |
| RNF04 | Transcrição de 1 h de reunião em até 15 min em Apple Silicon (modelo large-v3-turbo). |
| RNF05 | Falha em uma etapa não impede as demais reuniões nem apaga arquivos já gerados. |
| RNF06 | Domínio sem dependência de bibliotecas externas; adaptadores substituíveis por testes. |
| RNF07 | Cobertura de testes de 70% nos módulos de domínio e aplicação. |
| RNF08 | Compatível com macOS 14.2+ (API de process tap); testado em macOS 26. |
| RNF09 | Custo da API inferior a US$ 10/mês para 40 reuniões de 1 h. |
| RNF10 | Instalação completa por um único script (`scripts/install.sh`). |

## 5. Arquitetura hexagonal

```
                     ┌──────────────────────────────────────────────┐
  inbound            │                 APLICAÇÃO                    │        outbound
                     │  casos de uso + portas (Protocol)            │
 ┌───────────┐       │                                              │       ┌────────────────────┐
 │ daemon    │──────▶│  StartRecording   StopRecording              │──────▶│ CoreAudioTapCapture│ (Swift)
 │ (launchd) │       │  TranscribeMeeting AnalyzeMeeting            │──────▶│ FfmpegMicCapture   │
 └───────────┘       │  BuildDailyPlan   PurgeOldAudio              │──────▶│ FfmpegMixer        │
 ┌───────────┐       │                                              │──────▶│ WhisperCppTranscr. │
 │ CLI trec  │──────▶│           ┌──────────────────┐               │──────▶│ ClaudeAnalyzer     │
 └───────────┘       │           │     DOMÍNIO      │               │──────▶│ ClaudePlanner      │
 ┌───────────┐       │           │ Meeting, Action, │               │──────▶│ FsMeetingRepository│
 │ scheduler │──────▶│           │ Analysis, Plan   │               │──────▶│ MacOSNotifier      │
 │ (launchd) │       │           └──────────────────┘               │──────▶│ PmsetCallDetector  │
 └───────────┘       └──────────────────────────────────────────────┘       └────────────────────┘
```

### 5.1 Domínio (`domain/`)
Puro Python, sem I/O.

- `Meeting`: id (timestamp), início, fim, caminho da pasta, status derivado.
- `Transcript`: lista de `Segment(start, end, text)`.
- `Analysis`: `summary`, `decisions[]`, `my_actions[]`, `others_actions[]`, `deadlines[]`, `open_questions[]`, `next_meetings[]`.
- `Action`: descrição, responsável, prazo opcional, origem (meeting id), status.
- `DailyPlan`: data, prioridades, ações novas, concluídas, vencidas, texto Markdown.
- `MeetingStatus`: enum derivado de quais arquivos existem (`RECORDING`, `RECORDED`, `TRANSCRIBED`, `ANALYZED`, `FAILED`).

### 5.2 Portas (`application/ports.py`)

| Porta | Métodos | Implementação |
|-------|---------|---------------|
| `CallDetector` | `poll() -> CallState` | `PmsetCallDetector` |
| `ProcessAudioCapture` | `start(pid, out) -> Handle`, `stop(Handle)` | `CoreAudioTapCapture` (subprocesso Swift) |
| `MicCapture` | `start(device, out) -> Handle`, `stop(Handle)` | `FfmpegMicCapture` |
| `AudioMixer` | `mix(tracks, out)` | `FfmpegMixer` |
| `Transcriber` | `transcribe(audio, lang) -> Transcript` | `WhisperCppTranscriber` |
| `MeetingAnalyzer` | `analyze(transcript, ctx) -> Analysis` | `ClaudeAnalyzer` |
| `Planner` | `plan(analyses, prev, open) -> DailyPlan` | `ClaudePlanner` |
| `MeetingRepository` | `create`, `save_*`, `load_*`, `list(status)` | `FsMeetingRepository` |
| `Notifier` | `notify(title, body)` | `MacOSNotifier` |
| `Clock` | `now()` | `SystemClock` / `FakeClock` |

Cada porta tem um adaptador falso em `tests/fakes/` para testes sem hardware e sem rede.

### 5.3 Casos de uso (`application/use_cases/`)

- `StartRecording`: cria pasta, grava `meta.json`, inicia tap e microfone, notifica.
- `StopRecording`: para capturas, mixa, grava `audio.m4a`, remove trilhas brutas, notifica, enfileira transcrição.
- `TranscribeMeeting`: lê `audio.m4a`, gera `transcript.txt` e `transcript.json`.
- `AnalyzeMeeting`: lê transcrição, chama analisador, grava `analysis.json`.
- `BuildDailyPlan`: lê análises do dia, plano anterior e ações abertas; grava `planos/AAAA-MM-DD.md` e atualiza `acoes_abertas.json`.
- `PurgeOldAudio`: apaga `audio.m4a` com mais de 30 dias e transcrição presente.
- `Pipeline`: encadeia Stop → Transcribe → Analyze com tratamento de erro por etapa.

### 5.4 Adaptadores de entrada (`adapters/inbound/`)

- `daemon.py`: laço de detecção a cada 3 s; inicia gravação após 2 leituras positivas consecutivas e encerra após 5 negativas (15 s), evitando falsos positivos em oscilações.
- `cli.py` (Typer): `trec start|stop|cancel|transcribe|analyze|plan|purge|status|doctor`.
- Scheduler: entrada do launchd que chama `trec plan` no horário configurado.

### 5.5 Adaptadores de saída (`adapters/outbound/`)

**`CoreAudioTapCapture`** executa o binário `native/teams-tap` (Swift) por subprocesso:
`teams-tap --pid <pid> --out tap.wav`; captura via `AudioHardwareCreateProcessTap` + dispositivo agregado, 48 kHz, encerra limpo em SIGTERM.

**`FfmpegMicCapture`**: `ffmpeg -f avfoundation -i ":<idx>" mic.wav`, dispositivo configurável.

**`FfmpegMixer`**: `amix` das duas trilhas, normalização leve, saída AAC 64 kbps mono.

**`WhisperCppTranscriber`**: `whisper-cli -m ggml-large-v3-turbo.bin -l pt -oj -otxt`; parse do JSON para `Transcript`.

**`ClaudeAnalyzer` / `ClaudePlanner`** (SDK `anthropic` 1.x):
- modelo `claude-opus-5-5`; thinking adaptativo (padrão do modelo); `output_config.effort` configurável, padrão `high` para análise;
- saída estruturada com `client.messages.parse(..., output_format=<Pydantic>)`; o esquema Pydantic vive no adaptador e é convertido para o domínio;
- streaming para transcrições longas, `max_tokens` 16000;
- `cache_control` no prompt de sistema (fixo, em `prompts/*.md`);
- fallback de servidor habilitado (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) para recusas pontuais de classificador;
- tratamento de `stop_reason == "refusal"` e cadeia de exceções `RateLimitError → APIStatusError → APIConnectionError` com retentativa própria além da do SDK.

**`FsMeetingRepository`**: layout abaixo; escrita atômica (arquivo temporário + rename); `.lock` enquanto uma etapa roda.

**`MacOSNotifier`**: `osascript -e 'display notification ...'`.

**`PmsetCallDetector`**: parse de `pmset -g assertions` buscando asserções do processo do Teams; sinal secundário opcional de uso do microfone, a validar na implementação.

### 5.6 Composition root (`container.py`)
Único lugar que instancia adaptadores concretos a partir de `config.py`. Testes trocam por fakes aqui.

## 6. Layout de arquivos de dados (estado = arquivos)

```
~/Documents/teams-recorder/data/
├── recordings/
│   └── 2026-10-06_14-00-12/
│       ├── meta.json          # início, fim, pid, versão do pipeline
│       ├── tap.wav            # temporário, apagado após mix
│       ├── mic.wav            # temporário, apagado após mix
│       ├── audio.m4a          # apagado após 30 dias
│       ├── transcript.txt
│       ├── transcript.json
│       ├── analysis.json
│       ├── .lock              # presente só durante processamento
│       └── error.txt          # presente só se alguma etapa falhou
├── planos/
│   ├── 2026-10-06.md
│   └── acoes_abertas.json
└── log/
    └── teams-recorder.log     # rotação diária, 30 dias
```

Status de uma reunião é derivado: `audio.m4a` sem `transcript.json` → pendente de transcrição, e assim por diante. `trec status` e o `Pipeline` usam essa regra para retomar o que faltou.

## 7. Layout do código

```
teams-recorder/
├── pyproject.toml              # pacote teams_recorder, CLI trec, deps: anthropic, pydantic, typer, python-dotenv
├── .env.example                # ANTHROPIC_API_KEY=
├── .gitignore                  # .env, data/, native/.build
├── config.toml                 # dispositivo de mic, horário do plano, modelo whisper, retenção, effort
├── README.md
├── docs/
│   └── REQUISITOS-E-ARQUITETURA.md
├── prompts/
│   ├── analyze_system.md
│   └── plan_system.md
├── native/teams-tap/           # Swift Package
│   ├── Package.swift
│   └── Sources/teams-tap/main.swift
├── src/teams_recorder/
│   ├── domain/
│   │   ├── models.py
│   │   ├── status.py
│   │   └── errors.py
│   ├── application/
│   │   ├── ports.py
│   │   ├── pipeline.py
│   │   └── use_cases/
│   │       ├── start_recording.py
│   │       ├── stop_recording.py
│   │       ├── transcribe_meeting.py
│   │       ├── analyze_meeting.py
│   │       ├── build_daily_plan.py
│   │       └── purge_old_audio.py
│   ├── adapters/
│   │   ├── inbound/
│   │   │   ├── cli.py
│   │   │   └── daemon.py
│   │   └── outbound/
│   │       ├── detector_pmset.py
│   │       ├── capture_coreaudio.py
│   │       ├── capture_mic_ffmpeg.py
│   │       ├── mixer_ffmpeg.py
│   │       ├── transcriber_whispercpp.py
│   │       ├── llm_claude.py
│   │       ├── repository_fs.py
│   │       ├── notifier_macos.py
│   │       └── clock.py
│   ├── config.py
│   └── container.py
├── tests/
│   ├── fakes/                  # um fake por porta
│   ├── fixtures/               # áudio curto pt-BR, transcrição exemplo, analysis exemplo
│   ├── unit/                   # domínio e casos de uso
│   └── integration/            # whisper real (marcado slow), repositório em tmp_path
├── launchd/
│   ├── com.felipe.teams-recorder.plist   # daemon no login, KeepAlive
│   └── com.felipe.teams-planner.plist    # StartCalendarInterval 18:00, seg–sex
└── scripts/
    ├── install.sh              # brew whisper-cpp, modelo, pip -e ., swift build, launchctl load
    └── status.sh
```

## 8. Stack e versões no Mac de destino

| Componente | Versão | Origem |
|------------|--------|--------|
| macOS | 26.6.2 | — |
| Python | 3.11.5 | pyenv |
| Swift | 6.1 | Command Line Tools |
| ffmpeg | 9.0.1 | Homebrew |
| whisper.cpp | 1.9.4 | Homebrew (a instalar) |
| anthropic SDK | 1.x | pip (a instalar) |
| pydantic | 2.x | pip |
| typer | 0.x | pip |
| pytest | 8.x | pip |

## 9. Riscos e mitigações

| ID | Risco | Mitigação |
|----|-------|-----------|
| R1 | `~/Documents` pode sincronizar com o iCloud, levando `.env` (chave da API) e `data/` (áudios e transcrições) para a nuvem. | `install.sh` verifica se Documentos está no iCloud e, se estiver, cria `data/` em `~/Library/Application Support/teams-recorder` e avisa. Alternativa: `chflags nosync` nas pastas ou mover o projeto. |
| R2 | Chave da API em texto puro no `.env`. | `chmod 600 .env`, `.gitignore`, e `trec doctor` alerta. Migração para Keychain fica documentada como melhoria. |
| R3 | Heurística `pmset` pode quebrar em atualização do Teams. | Detector isolado atrás de porta; `trec start/stop` manual sempre disponível; teste de fumaça em `trec doctor`. |
| R4 | API de process tap pode mudar entre versões do macOS. | Binário Swift isolado; adaptador alternativo com BlackHole pode ser adicionado sem tocar o domínio. |
| R5 | Transcrições com conteúdo de clientes enviadas à API. | Filtro opcional de termos sensíveis antes do envio (`config.toml: redact = [...]`); política da Radix a confirmar. |
| R6 | Falso positivo do detector (Teams impede sono sem estar em chamada). | Exigir 2 leituras consecutivas e, quando disponível, sinal do microfone. |
| R7 | Custo da API acima do previsto. | Log de `usage` por chamada; `trec status` mostra gasto estimado do mês. |

## 10. Plano de implementação

| Fase | Entrega | Critério de aceite | Status |
|------|---------|--------------------|--------|
| 1 | Esqueleto do pacote, domínio, portas, fakes, CLI vazio, testes de domínio | `pytest` verde; `trec --help` funciona | Concluída em 2026-10-04 (casos de uso e repositório em arquivos entraram nesta fase) |
| 2 | `teams-tap` em Swift + `CoreAudioTapCapture` + `FfmpegMicCapture` + `FfmpegMixer`; `trec start/stop` manual | Chamada de teste gera `audio.m4a` audível com os dois lados | Concluída em 2026-10-04. Pendente do usuário: conceder "Gravação de Áudio do Sistema" ao `teams-tap` |
| 3 | `WhisperCppTranscriber`; `trec transcribe` | Transcrição em português do áudio da fase 2 com erros aceitáveis | Concluída em 2026-10-04. Fala sintetizada (voz Luciana) transcrita sem erros com `large-v3-turbo-q5_0` |
| 4 | `ClaudeAnalyzer`; `trec analyze`; prompts | `analysis.json` válido com ações reais da reunião de teste | Concluída em 2026-10-05 |
| 5 | `PmsetCallDetector` + daemon + launchd + notificações | Reunião real gravada sem toque no teclado | Concluída em 2026-10-05 com chamada simulada (processo que segura asserção de energia e é cliente de áudio) sob o launchd. Validação com Teams real pendente da próxima reunião |
| 6 | `ClaudePlanner`; `trec plan`; scheduler; `PurgeOldAudio` | Plano Markdown gerado às 18h com ações acumuladas | |
| 7 | `install.sh`, `trec doctor/status`, README | Instalação do zero em outro usuário do Mac funciona | |

### Notas da fase 2

- `CaptureHandle` virou dataclass concreta (PID + arquivo) em vez de Protocol: precisa ser gravada em `data/current_recording.json` para que `trec stop`, em outro processo, encerre os gravadores iniciados por `trec start`.
- O `teams-tap` embute um `Info.plist` (via linker) com `NSAudioCaptureUsageDescription`, para que o TCC identifique o utilitário ao pedir permissão.
- Teste de ponta a ponta (tom de teste + microfone) gerou `audio.m4a` mono AAC 48 kHz. A trilha do Teams sai em silêncio enquanto a permissão de áudio do sistema não for concedida; a mixagem tolera trilhas vazias.
- O ambiente mostra lentidão na primeira abertura de arquivos novos (antivírus corporativo); testes com subprocessos esperam sinal de prontidão em vez de assumir tempo de inicialização.

### Notas da fase 3

- Modelo padrão trocado de `large-v3-turbo` (1,6 GB) para `large-v3-turbo-q5_0` (574 MB, quantizado): o disco do Mac de destino estava com 3,8 GB livres. A qualidade em português se mostrou equivalente no teste; o nome do modelo é configurável em `config.toml`.
- O whisper-cli lê WAV/FLAC/MP3/OGG; o adaptador converte o M4A para WAV 16 kHz mono com ffmpeg em pasta temporária antes de transcrever.
- Saída via `-oj`: segmentos com `offsets` em milissegundos. Segmentos em branco são descartados.
- `trec transcribe` sem argumento processa todas as reuniões em estado RECORDED; falhas viram `error.txt` e não interrompem as demais (RNF05).

### Notas da fase 4

- Saída estruturada por JSON Schema derivado de um modelo Pydantic do adaptador (`AnalysisOut`), com `additionalProperties=false` e todos os campos obrigatórios; o Pydantic valida de novo do lado do cliente antes de converter para o domínio. Datas vêm em ISO e expressões relativas ("quarta-feira") são resolvidas pelo modelo a partir da data da reunião informada na mensagem.
- Prompt de sistema fixo e marcado com `cache_control`; metadados da reunião e transcrição vão na mensagem do usuário, preservando o prefixo cacheado entre reuniões.
- Fallback de servidor (`fallbacks: "default"`) ligado por padrão; a recusa final ainda é tratada como `AnalysisError` e vira `error.txt`.
- Respostas truncadas (`max_tokens`) e fora do esquema são erros explícitos, nunca análises parciais.
- Uso de tokens por chamada em `data/log/llm_usage.jsonl` (risco R7); `trec status` passará a somar o gasto estimado na fase 7.
- Teste real contra a API é opt-in (`TREC_REAL_CLAUDE=1`), pois gasta créditos; a suíte padrão usa um cliente simulado.
- Segundo adaptador para a mesma porta `MeetingAnalyzer`: `ClaudeCliAnalyzer` chama o Claude Code em modo headless (`claude -p --output-format json --json-schema …`) e usa a assinatura do usuário em vez de crédito de API. Compartilha prompt, esquema e conversão para o domínio com o adaptador de API; a seleção é por `llm.provider` em `config.toml` ou `TREC_LLM_PROVIDER`. Trade-offs: sem fallback de recusa, cache gerenciado pelo Claude Code, depende de sessão logada (relevante para o daemon via launchd, fase 5). Decisão motivada pela conta de API sem crédito no momento da validação; o adaptador de API segue como padrão.
