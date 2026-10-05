# Dicionário de estados e enumerações

## Estado da reunião (`MeetingStatus`) — derivado dos arquivos da pasta
| Valor | Condição (precedência de cima para baixo) | Próxima etapa |
|---|---|---|
| `failed` | existe `error.txt` | corrigir e repetir a etapa (o pipeline limpa o erro ao retomar) |
| `analyzed` | existe `analysis.json` | nenhuma (entra no plano do dia) |
| `transcribed` | existe `transcript.json` | `analyze` |
| `recorded` | existe `audio.m4a` | `transcribe` |
| `recording` | só `meta.json` (e trilhas brutas) | `stop` |

Observação: `audio.m4a` pode ter sido apagado pela retenção sem alterar `transcribed`/`analyzed`.

## Arquivos de uma reunião
| Arquivo | Quando existe | Conteúdo |
|---|---|---|
| `meta.json` | sempre | id, início, fim, PID alvo, título |
| `tap.wav`, `mic.wav` | só durante a gravação | trilhas brutas (apagadas após a mixagem) |
| `audio.m4a` | após `stop` | mix mono AAC 48 kHz |
| `transcript.json`, `transcript.txt` | após `transcribe` | segmentos / texto com tempos |
| `analysis.json` | após `analyze` | registro estruturado |
| `error.txt` | após falha | `etapa: mensagem` |
| `.lock` | durante uma etapa | PID do processo que processa |
| `debug/*.wav` | anomalia nas trilhas | cópias brutas preservadas |

## Estado do detector (`CallState`)
| Valor | Significado |
|---|---|
| `in_call` | processo observado com asserção de chamada |
| `idle` | sem asserção |
| `unknown` | leitura do `pmset` falhou (neutro na histerese) |

## Status de ação (`ActionStatus`)
| Valor | Significado |
|---|---|
| `open` | pendente |
| `done` | concluída (marcada pelo plano diário) |
| `overdue` | prazo vencido na data do plano |

## Provedor de LLM (`llm.provider`)
| Valor | Transporte | Cobrança |
|---|---|---|
| `api` | Claude API, SDK oficial | crédito pré-pago |
| `claude-code` | `claude -p` headless | assinatura do Claude Code |

## Backend do microfone (`audio.mic_backend`)
| Valor | Implementação | Observação |
|---|---|---|
| `coreaudio` (padrão) | `teams-tap --mic` (AVAudioEngine) | tolera reconfiguração do dispositivo; segue a entrada padrão |
| `ffmpeg` | avfoundation | parava de gravar quando o Teams abria o microfone |

## Asserções de energia reconhecidas como chamada
`PreventUserIdleDisplaySleep`, `PreventUserIdleSystemSleep`, `NoIdleSleepAssertion`, `NoDisplaySleepAssertion`. `UserIsActive` e outras não contam.

## Códigos de saída da CLI
| Código | Significado |
|---|---|
| 0 | sucesso |
| 1 | erro de execução ou pelo menos uma reunião falhou |
| 2 | comando de fase ainda não disponível |

## Notificações do macOS
"Gravação iniciada", "Gravação encerrada" (com minutos), "Gravação cancelada", "Falha na transcrição", "Falha na análise", "Plano do dia pronto" (fase 6).
