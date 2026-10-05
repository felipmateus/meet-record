# Transcrição

> **Comando:** `trec transcribe [id]`
> **Módulo:** Transcrição · **Gerado:** 2026-10-05

## Visão geral
Converte o áudio de uma reunião em texto em português com marcação de tempo, inteiramente no Mac. É a etapa que torna a reunião pesquisável e que alimenta a análise.

## Campos e opções
| Argumento | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `id` | texto | Não | todas as reuniões em estado `recorded` | Reunião específica a transcrever |

## Interações
- **Gatilho:** comando manual ou pipeline automático após `stop`.
- **Pré-processamento:** o M4A é convertido para WAV 16 kHz mono (formato aceito pelo whisper) em pasta temporária.
- **Detecção de voz (opcional, desligada por padrão):** com `transcription.vad = true` e o modelo Silero presente, o whisper só transcreve trechos com fala. Em teste com frases curtas, piorou o texto; por isso fica desligada até ser medida em reuniões longas.
- **Transcrição:** modelo `large-v3-turbo-q5_0`, idioma fixo `pt`, threads = metade dos núcleos por padrão.
- **Saída:** `transcript.json` (segmentos com início, fim e texto) e `transcript.txt` (uma linha por segmento, `[hh:mm:ss] texto`). Segmentos em branco são descartados.
- **Bloqueio:** um `.lock` na pasta impede duas transcrições simultâneas da mesma reunião.
- **Sem argumento:** processa todas as pendentes, informa "ok (N segmentos, M min)" por reunião; falhas viram `error.txt` e o comando termina com código 1 se houve alguma. Ao final sugere `trec analyze`.
- **Erros claros:** modelo ausente (com o comando para baixar), áudio ausente, whisper-cli ausente (com o comando do Homebrew), tempo esgotado (3 h).

## Integrações
| Integração | Uso | Observações |
|---|---|---|
| ffmpeg | Conversão para 16 kHz mono | — |
| whisper-cli (whisper.cpp 1.9.x) | Reconhecimento de fala | `-oj` JSON; `--vad -vm` opcional |
| Modelos ggml | Pesos do whisper e do VAD | `scripts/download-model.sh [nome]` |

## Relações
- **De:** [Gravação manual](./01-gravacao-manual.md) ou [Automação](./04-automacao.md).
- **Para:** [Análise](./03-analise.md) (estado passa a `transcribed`).

## Regras de negócio
- Desempenho observado em MacBook Air M1: 15 s de fala em ~30 s incluindo carga do modelo; reuniões longas próximas de 1:4.
- A transcrição permanece mesmo após o áudio ser apagado pela retenção.
- Alucinações do whisper em silêncio ("Tchau, tchau", "Legenda por …") são tratadas pelo corte de transcrições curtas na análise e pela redução de ruído na mixagem. `[TBC]` Efeito do VAD em reuniões longas ainda não medido.
