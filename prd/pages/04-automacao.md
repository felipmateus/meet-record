# Gravação automática (daemon e LaunchAgent)

> **Comandos:** `trec daemon [--once]`, `trec agent install [--env K=V]… | uninstall | restart | status`
> **Módulo:** Automação · **Gerado:** 2026-10-05

## Visão geral
É o coração do produto: um processo em segundo plano que percebe quando uma chamada do Teams começa e termina, grava, e ao final encadeia transcrição e análise, sem que o usuário toque no teclado. O LaunchAgent garante que ele suba no login e volte se cair.

## Detecção
- **Sinal:** a cada 3 s lê `pmset -g assertions`. O Teams, em chamada, cria asserções que impedem o Mac de dormir (`PreventUserIdleDisplaySleep`, `PreventUserIdleSystemSleep`, `NoIdleSleepAssertion`, `NoDisplaySleepAssertion`). Linhas do processo `MSTeams` com essas asserções significam "em chamada"; o PID do Teams vem da própria linha.
- **Histerese:** começa a gravar após 2 leituras positivas seguidas (~6 s); para após 5 negativas seguidas (~15 s). Leituras com falha são neutras.
- **Configuração:** `[detector] poll_seconds`, `start_after_positive_polls`, `stop_after_negative_polls`; `[audio] teams_process_name`.

## Interações

### Início de chamada
- Inicia a gravação como em [Gravação manual](./01-gravacao-manual.md) usando o PID detectado. Se já houver gravação manual ativa, o daemon a adota em vez de iniciar outra. Falhas são registradas e tentadas de novo no próximo ciclo.

### Durante a chamada
- Verifica a cada ciclo se os dois gravadores continuam vivos e registra um aviso único por gravador que morrer.

### Fim de chamada
- Encerra a gravação e dispara em segundo plano a sequência transcrição → análise, para o detector continuar atento à próxima chamada. Cada etapa falha isoladamente (`error.txt`).

### Partida e queda
- Ao subir: se encontrar uma gravação órfã (ponteiro + trilhas brutas), finaliza-a; se o ponteiro estiver sem trilhas, descarta-o. Em seguida retoma reuniões paradas em `recorded` ou `transcribed`.
- Ao receber SIGTERM/SIGINT: encerra a chamada ativa (gravação → pipeline) antes de sair.

### LaunchAgent
| Comando | Comportamento |
|---|---|
| `agent install` | Escreve `~/Library/LaunchAgents/local.teams-recorder.daemon.plist` (RunAtLoad, KeepAlive, PATH com Homebrew e `~/.local/bin`, logs em `data/log/daemon.*.log`) e carrega no domínio do usuário. `--env CHAVE=VALOR` adiciona variáveis ao daemon (ex.: `TREC_LLM_PROVIDER=claude-code`). Se já carregado, descarrega antes e espera a remoção concluir; repete o carregamento até 10 vezes por causa de um erro transitório do launchd. |
| `agent uninstall` | Descarrega e remove o plist. |
| `agent restart` | Reinicia o daemon (após mudar `config.toml` ou atualizar o código). |
| `agent status` | Mostra plist, se está carregado, PID e estado; código 1 se não carregado. |
| `daemon --once` | Diagnóstico: uma leitura do detector e o PID encontrado. |

## Integrações
| Integração | Uso |
|---|---|
| `pmset -g assertions` | Sinal de chamada |
| `pgrep -x MSTeams` | Reserva para localizar o PID |
| launchd (`launchctl bootstrap/bootout/kickstart/print`) | Ciclo de vida do daemon |
| `osascript display notification` | Notificações |

## Relações
- Encadeia [Gravação](./01-gravacao-manual.md) → [Transcrição](./02-transcricao.md) → [Análise](./03-analise.md).
- [Operação](./05-operacao.md) mostra o estado resultante.

## Regras de negócio
- Validado em 2026-10-05 com três chamadas reais; a terceira produziu as duas trilhas íntegras.
- `[TBC]` Comportamento em reuniões longas (> 1 h) e com troca de headset no meio ainda não observado em produção.
- Log principal: `data/log/teams-recorder.log` (rotação diária, 30 dias).
