# Instalação (fase 7 — pendente)

> **Entrega prevista:** `scripts/install.sh`, README de instalação, `trec status` com gasto do mês
> **Módulo:** Instalação · **Gerado:** 2026-10-05

## Objetivo
Instalar do zero em outro Mac ou outro usuário com um único script, atendendo ao RNF10.

## Passos previstos do `install.sh`
1. Verificar macOS ≥ 14.2 e Apple Silicon ou Intel compatível.
2. Homebrew: `ffmpeg`, `whisper-cpp`.
3. Python 3.11: venv e `pip install -e .`.
4. Swift (Command Line Tools): `scripts/build-native.sh`.
5. Modelos: `download-model.sh` (whisper quantizado e Silero VAD).
6. `.env` a partir do exemplo, permissão 600; instruções para a chave.
7. Detecção de pasta sincronizada com iCloud → dados em `~/Library/Application Support/teams-recorder` (já implementada em `config.py`).
8. `trec doctor`; `trec agent install`; orientação sobre as duas permissões do macOS.

## Critério de aceite
Instalação do zero em outro usuário do Mac funciona e `trec doctor` fica verde.
