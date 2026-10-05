# teams-recorder

Grava automaticamente o áudio das reuniões do Microsoft Teams no macOS, transcreve localmente com whisper.cpp, extrai ações e decisões com a Claude API e gera um plano diário de atividades em Markdown.

Documentação de requisitos e arquitetura: `docs/REQUISITOS-E-ARQUITETURA.md`.

## Estado atual

- Fase 1 concluída: domínio, portas, casos de uso, repositório em arquivos, CLI (`trec status`, `trec doctor`) e testes.
- Fase 2 concluída: captura do áudio do Teams via Core Audio Process Tap (binário Swift `teams-tap`), captura do microfone e mixagem com ffmpeg, comandos `trec start`, `trec stop` e `trec cancel`.
- Fase 3 concluída: transcrição local em português com whisper.cpp (`trec transcribe`), modelo `large-v3-turbo-q5_0`.
- Fase 4 concluída: análise da transcrição com a Claude API (`trec analyze`): resumo, decisões, ações, prazos e perguntas em aberto em `analysis.json`.
- Fase 5 concluída: detector de chamada, daemon e LaunchAgent (`trec agent install`). Gravação, transcrição e análise acontecem sozinhas.
- Próximas fases: planejador diário (6), instalador (7).

## Gravação manual (fase 2)

```bash
scripts/build-native.sh          # compila native/teams-tap/.build/release/teams-tap
trec start --title "Daily"       # Teams precisa estar aberto; ou use --pid
trec status                      # mostra a gravação em andamento
trec stop                        # mixa e gera data/recordings/<id>/audio.m4a
```

## Transcrição (fase 3)

```bash
brew install whisper-cpp
scripts/download-model.sh            # ggml-large-v3-turbo-q5_0.bin (574 MB) em data/models/
trec transcribe                      # todas as reuniões gravadas e ainda não transcritas
trec transcribe 2026-10-06_14-00-00  # uma reunião específica
```

Gera `transcript.txt` (com marcação de tempo) e `transcript.json` na pasta da reunião. Tudo roda localmente; o áudio não sai do Mac. Em um MacBook Air M1, 15 s de fala levam cerca de 30 s incluindo a carga do modelo; reuniões longas ficam próximas de 1:4 (uma hora em 15 min).

## Análise com Claude (fase 4)

```bash
cp .env.example .env && chmod 600 .env   # cole a chave da API (console.anthropic.com)
trec analyze                             # todas as reuniões transcritas e ainda não analisadas
trec analyze 2026-10-06_14-00-00         # uma reunião específica
```

Só o texto da transcrição e o prompt saem do Mac. Modelo `claude-opus-5-5` com saída estruturada validada por esquema, prompt de sistema em `prompts/analyze_system.md` com cache, e fallback de servidor para recusas pontuais do classificador de segurança. Cada chamada registra tokens em `data/log/llm_usage.jsonl`. Custo típico: cerca de US$ 0,10 por hora de reunião.

### Provedor: API ou Claude Code

Em `config.toml`, `llm.provider` escolhe o transporte:

| `provider` | Usa | Cobrança | Observações |
|---|---|---|---|
| `api` (padrão) | Claude API com `ANTHROPIC_API_KEY` | Crédito pré-pago por uso | Fallback de recusa e cache controlados pelo projeto |
| `claude-code` | Claude Code instalado, em modo headless (`claude -p`) | Assinatura do Claude Code | Exige sessão logada no Mac; sem fallback de recusa; modelo por apelido em `llm.cli_model` |

A variável de ambiente `TREC_LLM_PROVIDER` sobrescreve o arquivo, útil para testar: `TREC_LLM_PROVIDER=claude-code trec analyze`.

## Automático (fase 5)

```bash
trec agent install                                   # sobe no login, reinicia se cair
trec agent install --env TREC_LLM_PROVIDER=claude-code   # idem, analisando pela assinatura
trec agent status | restart | uninstall
trec daemon --once                                   # diagnóstico: o detector vê o Teams em chamada?
```

O daemon consulta `pmset -g assertions` a cada 3 s. O Teams, em chamada, impede o Mac de dormir, e essa asserção é o sinal: a gravação começa após 2 leituras positivas seguidas (~6 s) e termina após 5 negativas (~15 s), evitando falsos positivos em oscilações. Ao fim da chamada o pipeline roda em segundo plano (mixagem, transcrição, análise) enquanto o detector segue atento à próxima. Se o daemon cair no meio de uma gravação, ele finaliza a gravação órfã ao subir e retoma reuniões pendentes. Log em `data/log/teams-recorder.log`; `trec start/stop` manual continua funcionando e o daemon adota uma gravação manual em andamento.

Na primeira execução o macOS pede duas permissões: **Microfone** (para o ffmpeg) e **Gravação de Tela e Áudio do Sistema** (para o teams-tap), em Ajustes do Sistema > Privacidade e Segurança. Sem a segunda, a trilha do Teams sai em silêncio.

## Desenvolvimento

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                             # suíte rápida (sem cobertura)
pytest --cov=teams_recorder --cov-report=term-missing   # com cobertura (alvo: 70%)
TREC_REAL_WHISPER=1 pytest -m slow                 # inclui transcrição real com o modelo
trec --help
```
