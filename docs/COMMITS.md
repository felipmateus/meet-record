# Convenção de commits

O histórico é organizado em **ondas**: cada fase do plano de implementação (seção 10 de
`REQUISITOS-E-ARQUITETURA.md`) vira uma sequência curta de commits, um por camada da
arquitetura hexagonal, na ordem de dependência:

1. `docs:` documentos e decisões da fase
2. `feat(domain):` entidades e regras puras
3. `feat(application):` portas, casos de uso, pipeline
4. `feat(adapters):` adaptadores de saída (I/O)
5. `feat(native):` código Swift
6. `feat(cli):` composition root e comandos
7. `test:` fakes, fixtures e testes da onda

Mensagens no imperativo, em português, com escopo entre parênteses. Cada commit deve
deixar a árvore importável; os testes podem só passar ao fim da onda.

## Ondas já registradas

| Onda | Fase | Conteúdo |
|------|------|----------|
| 0 | — | Entrevista, requisitos, arquitetura, convenções |
| 1 | 1 | Esqueleto, domínio, aplicação, repositório em arquivos, config, testes |
| 2 | 2 | teams-tap (Swift), captura e mixagem, CLI start/stop/cancel, testes de adaptadores |
| 3 | 3 | Config de transcrição, transcritor whisper.cpp e download do modelo, CLI transcribe, testes, docs |
