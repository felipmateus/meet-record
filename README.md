# teams-recorder

Grava automaticamente o áudio das reuniões do Microsoft Teams no macOS, transcreve localmente com whisper.cpp, extrai ações e decisões com a Claude API e gera um plano diário de atividades em Markdown.

Documentação de requisitos e arquitetura: `docs/REQUISITOS-E-ARQUITETURA.md`.

## Estado atual

- Fase 1 concluída: domínio, portas, casos de uso, repositório em arquivos, CLI (`trec status`, `trec doctor`) e testes.
- Fase 2 concluída: captura do áudio do Teams via Core Audio Process Tap (binário Swift `teams-tap`), captura do microfone e mixagem com ffmpeg, comandos `trec start`, `trec stop` e `trec cancel`.
- Fase 3 concluída: transcrição local em português com whisper.cpp (`trec transcribe`), modelo `large-v3-turbo-q5_0`.
- Fase 4 concluída: análise da transcrição com a Claude API (`trec analyze`): resumo, decisões, ações, prazos e perguntas em aberto em `analysis.json`.
- Próximas fases: detector automático e launchd (5), planejador diário (6), instalador (7).

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
