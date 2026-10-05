# teams-recorder

Grava automaticamente o áudio das reuniões do Microsoft Teams no macOS, transcreve localmente com whisper.cpp, extrai ações e decisões com a Claude API e gera um plano diário de atividades em Markdown.

Documentação de requisitos e arquitetura: `docs/REQUISITOS-E-ARQUITETURA.md`.

## Estado atual

- Fase 1 concluída: domínio, portas, casos de uso, repositório em arquivos, CLI (`trec status`, `trec doctor`) e testes.
- Fase 2 concluída: captura do áudio do Teams via Core Audio Process Tap (binário Swift `teams-tap`), captura do microfone e mixagem com ffmpeg, comandos `trec start`, `trec stop` e `trec cancel`.
- Próximas fases: transcrição (3), análise com Claude (4), detector automático e launchd (5), planejador diário (6), instalador (7).

## Gravação manual (fase 2)

```bash
scripts/build-native.sh          # compila native/teams-tap/.build/release/teams-tap
trec start --title "Daily"       # Teams precisa estar aberto; ou use --pid
trec status                      # mostra a gravação em andamento
trec stop                        # mixa e gera data/recordings/<id>/audio.m4a
```

Na primeira execução o macOS pede duas permissões: **Microfone** (para o ffmpeg) e **Gravação de Tela e Áudio do Sistema** (para o teams-tap), em Ajustes do Sistema > Privacidade e Segurança. Sem a segunda, a trilha do Teams sai em silêncio.

## Desenvolvimento

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
trec --help
```
