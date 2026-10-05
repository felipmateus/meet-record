# Gravação manual

> **Comandos:** `trec start [--pid N] [--title T]`, `trec stop`, `trec cancel`
> **Módulo:** Gravação · **Gerado:** 2026-10-05

## Visão geral
Permite gravar uma chamada do Teams sob controle do usuário, sem depender do detector automático. É também o caminho de contingência quando a heurística de detecção falha. Grava duas trilhas separadas (o que o Teams toca e o que o microfone capta) e, ao parar, as combina num único arquivo comprimido.

## Pré-condições
- Teams em execução (para localizar o processo), ou um `--pid` explícito.
- Binário nativo `teams-tap` compilado (`scripts/build-native.sh`).
- Nenhuma outra gravação em andamento (só uma por vez).

## Campos e opções

| Opção | Tipo | Obrigatório | Padrão | Regras | Descrição |
|---|---|---|---|---|---|
| `--pid` | inteiro | Não | PID do processo `MSTeams` em execução | Erro se nem o Teams nem o PID existirem | Processo cujo áudio será capturado (ele e seus descendentes) |
| `--title` | texto | Não | vazio | — | Título exibido no status e usado como contexto na análise |

## Interações

### Iniciar (`trec start`)
- **Gatilho:** usuário executa o comando.
- **Comportamento:** cria a pasta da reunião com `meta.json`; inicia a captura do Teams (`tap.wav`) e do microfone (`mic.wav`); grava um ponteiro `data/current_recording.json` com os PIDs dos gravadores; notifica "Gravação iniciada".
- **Validações:** se já houver gravação ativa, falha com "já existe uma gravação em andamento"; se a captura do Teams falhar, nada fica para trás (pasta removida); se o microfone falhar, a captura do Teams é encerrada e a pasta removida.
- **Espera de áudio:** o Teams cria a asserção de chamada antes de inicializar o áudio; o gravador espera até 20 s pelo processo (ou um descendente) virar cliente de áudio antes de desistir.
- **Microfone:** segue a entrada padrão do sistema (`mic_device = "default"`), portanto acompanha troca para headset; sobrevive à reconfiguração que o Teams faz ao abrir o microfone, reiniciando a captura sem perder o arquivo.

### Parar (`trec stop`)
- **Gatilho:** usuário executa o comando, em qualquer terminal (o ponteiro em disco permite parar uma gravação iniciada por outro processo).
- **Comportamento:** encerra os dois gravadores com sinal limpo; registra duração e níveis (dB) de cada trilha no log; mixa em `audio.m4a` (AAC 64 kbps, mono, 48 kHz) aplicando por trilha passa-alta 80 Hz e redução de ruído, e no resultado normalização de loudness (-18 LUFS) e limitador a -1 dBTP; apaga as trilhas brutas; grava `ended_at`; limpa o ponteiro; notifica "Gravação encerrada" com a duração; sugere o comando de transcrição.
- **Regras:** trilha ausente ou menor que 1 KB é descartada e a mixagem segue com a outra; se uma trilha tiver menos da metade da duração da outra, cópias brutas são preservadas em `<reunião>/debug/` para diagnóstico.
- **Falha:** se nenhuma trilha for utilizável, erro "nenhuma trilha de áudio utilizável"; a pasta permanece em estado "gravando" para inspeção.

### Cancelar (`trec cancel`)
- **Gatilho:** usuário executa o comando.
- **Comportamento:** encerra os gravadores (melhor esforço), apaga a pasta da reunião e o ponteiro; notifica "Gravação cancelada". Nenhum arquivo é mantido.

## Integrações
| Integração | Uso | Observações |
|---|---|---|
| `teams-tap --pid` (Core Audio Process Tap) | Áudio emitido pelo Teams | Captura o processo e descendentes clientes de áudio; WAV float 32 bits 48 kHz estéreo |
| `teams-tap --mic` (AVAudioEngine) | Microfone | WAV float 32 bits 48 kHz mono; backend alternativo `ffmpeg` disponível por configuração |
| ffmpeg | Mixagem e codificação | Ver apêndice de integrações para a cadeia de filtros |

## Relações
- **Para:** [Transcrição](./02-transcricao.md) (estado passa a `recorded`).
- **Com:** [Automação](./04-automacao.md) — o daemon adota uma gravação manual em andamento em vez de iniciar outra.

## Regras de negócio
- Uma única gravação ativa por vez, independentemente de ser manual ou automática.
- Trilhas brutas são efêmeras; só o M4A fica (exceto na preservação por anomalia).
