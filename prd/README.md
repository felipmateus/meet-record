# teams-recorder — Documento de Requisitos de Produto (PRD)

> Gerado a partir do código em 2026-10-05 (commit da fase 5 + tratamento de ruído). Linguagem de produto; detalhes técnicos só onde afetam o comportamento. Itens marcados `[TBC]` não puderam ser confirmados pelo código.

## 1. Visão geral do sistema

O teams-recorder é um utilitário pessoal para macOS que grava automaticamente as reuniões do Microsoft Teams de um único usuário, transcreve o áudio localmente em português, extrai da transcrição um registro estruturado (resumo, decisões, ações, prazos, perguntas em aberto) usando um modelo de linguagem, e, na fase seguinte, consolida as reuniões do dia em um plano de atividades.

Ele roda em segundo plano, sem interface gráfica: um daemon observa o Teams e dispara a gravação quando uma chamada começa; ao fim, processa tudo sozinho e avisa por notificações do macOS. Uma linha de comando (`trec`) permite operar e inspecionar manualmente cada etapa. Áudio e transcrição nunca saem do Mac; só o texto da transcrição é enviado ao modelo de linguagem, por API ou pelo Claude Code instalado.

**Usuário**: uma pessoa, dona do Mac e da conta do Teams, que participa de várias reuniões por dia e quer um registro confiável de compromissos sem tomar notas. **Contexto**: ambiente corporativo; a gravação nativa do Teams pode estar desabilitada; consentimento e política interna são responsabilidade do usuário (ver §6).

## 2. Módulos

| Módulo | Fluxos | Função central | Status |
|---|---|---|---|
| Gravação | start, stop, cancel | Capturar o áudio do Teams e do microfone em trilhas separadas e mixar num M4A | Entregue (fase 2) |
| Transcrição | transcribe | Converter o áudio em texto com marcação de tempo, localmente | Entregue (fase 3) |
| Análise | analyze | Extrair resumo, decisões, ações, prazos e perguntas da transcrição | Entregue (fase 4) |
| Automação | daemon, agent | Detectar chamadas do Teams e encadear gravação → transcrição → análise sem intervenção | Entregue (fase 5) |
| Operação | status, doctor, purge, version | Inspecionar o estado, verificar dependências, aplicar retenção | Entregue (fases 1 a 5) |
| Planejamento | plan, scheduler | Consolidar as análises do dia num plano em Markdown e manter ações abertas | Pendente (fase 6) |
| Instalação | install.sh | Instalar do zero em outro Mac/usuário | Pendente (fase 7) |

## 3. Inventário de fluxos

| # | Fluxo | Comando | Módulo | Doc |
|---|---|---|---|---|
| 1 | Gravação manual | `trec start` / `trec stop` / `trec cancel` | Gravação | [→](./pages/01-gravacao-manual.md) |
| 2 | Transcrição | `trec transcribe [id]` | Transcrição | [→](./pages/02-transcricao.md) |
| 3 | Análise | `trec analyze [id]` | Análise | [→](./pages/03-analise.md) |
| 4 | Gravação automática | `trec daemon`, `trec agent …` | Automação | [→](./pages/04-automacao.md) |
| 5 | Operação e diagnóstico | `trec status` / `doctor` / `purge` / `version` | Operação | [→](./pages/05-operacao.md) |
| 6 | Plano diário | `trec plan` (futuro) | Planejamento | [→](./pages/06-plano-diario.md) |
| 7 | Instalação | `scripts/install.sh` (futuro) | Instalação | [→](./pages/07-instalacao.md) |

Apêndices: [dicionário de estados e enumerações](./appendix/dicionario-enums.md) · [integrações externas](./appendix/integracoes.md) · [layout de dados e esquemas](./appendix/layout-de-dados.md) · [relações entre fluxos](./appendix/relacionamentos.md).

## 4. Notas globais

### Modelo de estado: "o estado é o arquivo"
Não há banco de dados. Cada reunião é uma pasta em `data/recordings/<id>/`, e o estado da reunião é derivado de quais arquivos existem nela (ver dicionário). Qualquer etapa pode ser repetida a partir dos arquivos existentes; falhas ficam registradas em `error.txt` na própria pasta e não afetam outras reuniões.

### Identidade da reunião
O id é o instante de início no formato `AAAA-MM-DD_HH-MM-SS`. Não há título automático; o campo `title` só é preenchido quando informado manualmente em `trec start --title`. `[TBC]` integração com o calendário para nomear reuniões foi descartada na entrevista de requisitos (decisão 9), mas o campo existe no modelo.

### Configuração
`config.toml` na raiz do projeto, sem segredos; `.env` com a chave da API (ignorado pelo git, permissão 600 recomendada). Variáveis de ambiente sobrescrevem pontos específicos: `TEAMS_RECORDER_DIR` (pasta do projeto), `TREC_LLM_PROVIDER` (api | claude-code), `TREC_TEAMS_PROCESS` (nome do processo observado; uso em testes).

### Permissões do macOS
Duas permissões são necessárias e pedidas na primeira gravação: **Microfone** e **Gravação de Tela e Áudio do Sistema**. Sem a segunda, a trilha do Teams sai em silêncio e a mixagem segue só com o microfone.

### Padrões de interação
- Comandos de processamento (`transcribe`, `analyze`) sem argumento atuam sobre **todas** as reuniões pendentes daquela etapa e seguem adiante mesmo quando uma falha; saem com código 1 se houve alguma falha.
- Toda saída de erro começa com `erro:`; comandos de fases futuras existem na ajuda e informam em que fase chegam (código de saída 2).
- Notificações do macOS: "Gravação iniciada", "Gravação encerrada", "Falha na transcrição/análise", "Plano do dia pronto" (fase 6).

### Custo e privacidade
- Transcrição 100 % local (whisper.cpp). Modelo `large-v3-turbo-q5_0`, 574 MB.
- Análise: Claude Opus 5.5 via API (pré-pago, ~US$ 0,10 por hora de reunião) ou Claude Code headless (assinatura). Cada chamada registra tokens e custo em `data/log/llm_usage.jsonl`.
- Transcrições com menos de 20 palavras não são enviadas ao modelo.
- Áudio é apagado após 30 dias (configurável) quando já transcrito; transcrição e análise permanecem.

## 5. Roteiro

| Fase | Entrega | Situação |
|---|---|---|
| 1–5 | Gravação, transcrição, análise, automação, operação | Entregues e validadas com chamadas reais do Teams em 2026-10-05 |
| 6 | Planejador diário (`trec plan`), agendamento às 18h, atualização de ações abertas | Caso de uso e prompt prontos; falta adaptador, comando e agendamento |
| 7 | `install.sh`, `trec status` com gasto do mês, README de instalação | Pendente |

## 6. Fora de escopo e responsabilidades do usuário
- Identificação de quem fala (diarização): não implementada; o modelo infere pelo contexto.
- Aviso aos participantes e conformidade com política da empresa e LGPD: responsabilidade do usuário. O projeto oferece um filtro de termos sensíveis apenas como melhoria futura (risco R5 do documento de arquitetura).
- Integração com Microsoft To Do, Obsidian ou calendário: adiada para depois da fase 7.
