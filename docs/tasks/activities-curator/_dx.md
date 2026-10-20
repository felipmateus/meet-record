# Developer Experience: Activities curator

Public-surface contract for the activities curator. Companion to `_spec.md` (Part II serves this
surface) and `_tests.md` (E2E journeys use these exact invocations). Surfaces: the document file,
the archive, the CLI, config, notifications, the minutes section, and the analysis/minutes
additions. CLI output and notifications are English (AGENTS.md); the document content is Brazilian
Portuguese, written by the model. Three kinds of model-written Portuguese text are echoed verbatim into
English output, and AGENTS.md's allowance list gains them: the curator's one-line summary (notification
bodies, `Last pass:` and per-pass lines), the focus lines `trec activities` prints, and the labels in
`messages.ActivityDoc`. Everything else the CLI prints is English, including weekdays (`Mon 19/10`).

## Golden Path

```bash
$ trec activities curate --since 2026-10-05      # one-time bootstrap from past meetings
Curate 23 meetings in 9 passes using your Claude subscription (~25 min)? [y/N]: y
Pass 1/9: Kickoff SAP (05/10)… ok (9 edits) — 4 ações novas, 2 aguardando, 3 de contexto
…
Pass 9/9: Daily (16/10), Cliente Acme (16/10)… ok (3 edits) — 1 ação nova, 1 possível conclusão, 1 prazo mudou
Document: data/activities/atividades.md

# a Teams meeting happens; the daemon records, transcribes, analyzes, then curates
# ~2–5 min later a notification: "Activities updated — 1 ação nova, 1 possível conclusão"

$ trec activities --open
Document: data/activities/atividades.md   (opened in the default Markdown app)
Updated Mon 19/10 10:12 after Daily
Focus:
  1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.
  2. **Estimar a integração de estoque**: vence seg 19/10; o Rafael quer na Revisão de sprint das 15:00.
  3. Cobrar o **Bruno** pelo acesso ao PRD: trava a validação de ter 20/10.
Open: 7 yours · 3 waiting on others · 2 agenda · 5 context
Last pass: Mon 19/10 10:12 — 1 ação nova, 1 possível conclusão

# in VS Code: tick "- [x]" on what is done, add your own lines; the next pass respects them
```

## Files

```
data/activities/
  atividades.md            # the document (open it in VS Code)
  arquivo/2026-10.md       # everything that left the document, with date and reason (one file per month)
  .curator/                # internal: lock, base.md, versions/ (last 50 passes: _before, _after, _base, _prevbase, _pass.json)
data/log/activities.jsonl  # one line per pass (internal, for diagnosis)
data/recordings/<id>/curation_error.txt   # only when the last pass for this meeting failed
```

### `atividades.md` (as the user sees it, Monday 19/10 after the Daily)

```markdown
# Atividades

<!-- curador:início (reescrito a cada passada; escreva fora desta caixa) -->
> **Atualizado seg 19/10 10:12** · após Daily
>
> **Foco**
> 1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.
> 2. **Estimar a integração de estoque**: vence seg 19/10; o Rafael quer na Revisão de sprint das 15:00.
> 3. Cobrar o **Bruno** pelo acesso ao PRD: trava a validação de ter 20/10.
> 4. **Subir o timesheet de outubro**: você disse que já subiu; marque [x] se for o caso.
<!-- curador:fim 20261019-101200 -->

## Minhas ações

- [ ] **Enviar cronograma revisado do go-live** — p/ Carla · sex 16/10 · alta · [Revisão SAP 14/10][2026-10-14_10-00-03] [Daily 16/10][2026-10-16_09-30-11]
  - prazo mudou de qua 14/10 para sex 16/10 (Daily 16/10, 00:05:02)
- [ ] **Estimar a integração de estoque** — p/ Rafael · seg 19/10 · [Planejamento 15/10][2026-10-15_14-00-07]
  - falta só o módulo de reservas (Daily 19/10, 00:04:12)
- [ ] **Validar a carga de materiais no QAS** — p/ time de dados · ter 20/10 · [Daily 16/10][2026-10-16_09-30-11]
- [ ] **Subir o timesheet de outubro** · [1:1 Marina 13/10][2026-10-13_16-00-04]
  - 💬 Na Daily 19/10 (00:02:55) você disse: "o timesheet eu já subi". Marque [x] se concluiu.
- [ ] Ligar para o suporte da VPN
- [ ] **Revisar o PR do mapeamento de centros** — p/ Diego · ⚠️ a confirmar: não ficou claro se o pedido era para você · [Daily 16/10][2026-10-16_09-30-11]
- [ ] **Atualizar a documentação da interface de pedidos** · 💤 sem menção desde ter 22/09 — ainda vale? · [Revisão SAP 22/09][2026-09-22_10-00-09]
- [x] **Enviar a ata da reunião com a Acme** ✔ sex 16/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]

## Aguardando outros

- [ ] **Bruno**: liberar o seu acesso ao SAP PRD · pedido qua 14/10 · bloqueia a validação de ter 20/10 · [Revisão SAP 14/10][2026-10-14_10-00-03]
- [ ] **Carla**: aprovar o escopo da fase 2 · qui 22/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]
- [ ] **Diego**: corrigir a conversão de unidade no relatório de estoque · [Daily 16/10][2026-10-16_09-30-11]
  - 💬 Na Daily 16/10 (00:06:40) o Diego disse: "o fix já tá em homologação". Marque [x] se resolvido.

## Agenda e prazos

- seg 19/10 15:00 — Revisão de sprint · [Daily 16/10][2026-10-16_09-30-11]
- sex 30/10 — Go-live do piloto em Jundiaí · [Revisão SAP 14/10][2026-10-14_10-00-03]

## Contexto recente

- Decisão: a carga inicial usa a planilha de sexta, não o extrato do SAP · [Daily 16/10][2026-10-16_09-30-11]
- Pergunta: quem assina o aceite do piloto do lado da Acme? · [Cliente Acme 15/10][2026-10-15_16-30-02]
- Risco: sem acesso ao PRD até qua 21/10, o go-live de sex 30/10 atrasa · [Revisão SAP 14/10][2026-10-14_10-00-03]
- Sem dono: avisar o suporte sobre a janela de manutenção de sábado · [Daily 16/10][2026-10-16_09-30-11]

<!-- links:início (gerado automaticamente) -->
[2026-09-22_10-00-09]: ../recordings/2026-09-22_10-00-09/minutes.md
[2026-10-13_16-00-04]: ../recordings/2026-10-13_16-00-04/minutes.md
[2026-10-14_10-00-03]: ../recordings/2026-10-14_10-00-03/minutes.md
[2026-10-15_14-00-07]: ../recordings/2026-10-15_14-00-07/minutes.md
[2026-10-15_16-30-02]: ../recordings/2026-10-15_16-30-02/minutes.md
[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md
<!-- links:fim -->
```

What the user may do in the file: tick `[x]`, untick, delete lines, reword, change a date, add own
lines and sub-lines, add own `##` sections, write `#história` on an item. The next pass treats all of
it as the user's decision. Lines typed inside the box are moved by the pass into the right section (the
box itself is rewritten); a line the pass did not move, or that was typed while the pass was running, is
put at the top of `## Minhas ações` by the app, unchanged, and the next pass handles it as a normal
user line. Leave the two box marker lines alone: the number in the closing one is the stamp of the pass that wrote the file, which lets the app tell after a crash whether a pass reached the file. Lines the user wrote are never marked 💤 or given links on their main line: a meeting that
mentions one adds a sub-line (`- citado na [Daily 19/10][2026-10-19_09-30-11]`).

### `arquivo/2026-10.md` (one entry)

```markdown
### 16/10/2026 — data passou (qui 15/10)
- qui 15/10 16:30 — Reunião com a Acme · [Revisão SAP 14/10][2026-10-14_10-00-03]
[2026-10-14_10-00-03]: ../../recordings/2026-10-14_10-00-03/minutes.md
```

Reasons the user will see: `concluído`, `data passou (<data>)`, `respondida na <reunião dd/mm>: …`,
`resolvido na <reunião dd/mm>: …`, `sem menção há 7 dias`, `duplicado de: <título>`,
`removido por você`.

### `minutes.md` (new section, after the actions)

```markdown
### 🔄 Andamento informado
- Você: concluído — timesheet de outubro · "o timesheet eu já subi" [00:02:55]
- Diego: concluído — conversão de unidade no relatório de estoque · "o fix já tá em homologação" [00:06:40]
- Você: prazo alterado — cronograma do go-live (nova data sex 16/10) · "o cronograma eu fecho hoje à tarde" [00:05:02]
- Rafael: reatribuído — relatório de testes (para Ana) · "passa o relatório para a Ana" [00:12:04] ⚠️ não confirmado: a frase não aparece nesse trecho
```

## CLI

### `trec activities [--open]`

```
$ trec activities
Document: data/activities/atividades.md
Updated Mon 19/10 10:12 after Daily
Focus:
  1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.
  …
Open: 7 yours · 3 waiting on others · 2 agenda · 5 context
Last pass: Mon 19/10 10:12 — 1 ação nova, 1 possível conclusão
Not curated:
  2026-10-19_14-00-03 (Revisão de sprint): Claude Code timed out after 900 s → trec activities curate 2026-10-19_14-00-03
  2026-10-16_17-30-00 (Alinhamento Acme): not attempted yet → trec activities curate 2026-10-16_17-30-00
$ echo $?
0
```

- `--open` additionally opens the file with the default application (`open` on macOS, `os.startfile` on Windows).
- No document: `No activities document yet. Build it from past meetings: trec activities curate --since YYYY-MM-DD` and exit 0.
- The `Updated` line comes from the last pass record (time and meeting titles, English weekday), the focus lines from the box between its markers, and the counts from the document: open checkbox lines under each of the four `messages.ActivityDoc` headings, plain lines for agenda and context (a section whose heading the user renamed or removed is omitted).
- `Not curated` lists every meeting analyzed in the last 10 working days with no successful pass: one that failed (its `curation_error.txt` text) and one never attempted (`not attempted yet`, e.g. its pass was lost to a restart). The daemon retries those of the last 2 working days (today counts as day 0: on a Monday the window starts Thursday) by itself; the list is the manual route.

### `trec activities curate <id>... | --since YYYY-MM-DD [--yes]`

```
$ trec activities curate 2026-10-19_14-00-03
waiting for the curator…            # only when a pass is running
Curating Revisão de sprint (19/10)… ok (2 edits) — 1 ação nova, prazo do cronograma mudou para sex 16/10
$ echo $?
0

$ trec activities curate 2026-10-19_16-00-00
Meeting 2026-10-19_16-00-00 is transcribed, not analyzed: run trec analyze 2026-10-19_16-00-00 first.
$ echo $?
1

$ trec activities curate --since 2026-10-05
Curate 23 meetings in 9 passes using your Claude subscription (~25 min)? [y/N]: n
Nothing curated.
```

- Confirmation wording follows `llm.provider`: `using your Claude subscription` with `claude-code`, `using the Anthropic API (spends API credit)` with `api`. The estimate is passes × `Activities.EST_SECONDS_PER_PASS` (160 s).

- Passes run in the foreground, under the curator lock, chronologically, up to 4 same-day meetings per pass.
- Reruns are safe (no duplicates).
- A failed pass of several meetings is re-run one meeting at a time; each meeting that fails alone prints `failed: <reason>` and gets `curation_error.txt`; the command continues with the next pass and exits 1 at the end.
- `[activities] enabled = false` does not disable this command: it is an explicit request.
- `--yes` skips the confirmation (for scripts).

### `trec analyze [id]` (curation step)

`trec analyze` does not go through `Pipeline`; after its loop it curates the meetings it analyzed successfully, `[activities] enabled` permitting, in batches of four oldest first, reusing the `curate` output line. Analyzing an already analyzed meeting again curates it again (safe: its items are recognised).

```
$ trec analyze 2026-10-19_14-00-03
Analyzing 2026-10-19_14-00-03… ok (…)
…
Curating Revisão de sprint (19/10)… ok (2 edits) — 1 ação nova, prazo do cronograma mudou para sex 16/10
$ echo $?
0

$ trec analyze 2026-10-19_14-00-03        # analysis ok, curation failed
…
Curating Revisão de sprint (19/10)… failed: Claude Code timed out after 900 s
$ echo $?
0
```

- A curation failure prints `failed: <reason>`, writes `curation_error.txt`, sends the failure notification and leaves the exit code at 0 when every analysis succeeded (the meeting stays `analyzed`; the daemon retries it, or run `trec activities curate <id>`). An analysis failure exits 1 as today, and failed meetings are not curated.
- With `[activities] enabled = false` the step is skipped without output.

### `trec activities undo [--yes]`

```
$ trec activities undo
Last pass: Mon 19/10 10:12 after Daily (1 ação nova, 1 possível conclusão)
--- now
+++ before the pass
@@ … @@
-- [ ] **Validar a carga de materiais no QAS** — p/ time de dados · ter 20/10 · [Daily 16/10][2026-10-16_09-30-11]
…
This also discards 2 lines you edited after the pass.
Restore the document to before this pass? [y/N]: y
Restored. Run trec activities curate 2026-10-19_09-30-11 to curate that meeting again.

$ trec activities undo          # while a pass is running
The curator is working; try again in a few minutes.
$ echo $?
1

$ trec activities undo          # nothing left
No pass to undo.
$ echo $?
1
```

- When the archive changed after that pass (its size is no longer the one recorded after the pass): `The archive changed after this pass; its entries were left in place.`
- Undo goes back to the version before that pass and the next pass sees again every edit you made before and during it: a deletion the undone pass had archived is seen as your deletion again, not lost.
- The preview identifies the pass it shows; the confirmation undoes only that pass. If another pass committed meanwhile: `A new pass ran while you were deciding; run trec activities undo again.` and exit 1, document untouched.

### `trec stories`

```
$ trec stories
Drafting 2 tagged items… ok (1 story, 1 already exists)
  Estimativa da integração de estoque
  Skipped: Revisar o PR do mapeamento de centros — already exists ("Mapeamento de centros")
Drafts: data/plans/2026-10-19.stories.md
$ echo $?
0

$ trec stories
Nothing tagged #história in data/activities/atividades.md.
```

```
$ trec stories                      # the curator holds the lock when the drafts are ready
Drafting 1 tagged item… ok (1 story)
  Estimativa da integração de estoque
The curator is working; the drafts are saved. Run trec stories again later to replace the tags.
Drafts: data/plans/2026-10-19.stories.md
$ echo $?
0
```

- `trec stories` never waits for the curator lock. When it is busy, the drafts are saved and the tag replacements wait: the next `trec stories` replaces them first (a line edited meanwhile keeps its tag). A line that already has a story or a skip in the recent drafts (today included) is never sent to the writer again, so running `trec stories` several times while a pass runs drafts each item once.
- A block the writer skips keeps its tag and the CLI prints `Skipped: <first line> — <reason>`. A block of another nature than feature, bug, technical or operation is skipped that way.
- `--date` is removed: drafts always go to today's drafts file, merged with drafts already there (including drafts the old planner wrote that day).
- With `[stories] publish = true` the drafts are published right after drafting, as before.
- `trec publish [--date] [--only 1,3]` is unchanged for the user and publishes block stories and old drafts alike. It reads only the day's `*.stories.json` (no plan file is needed, so it works on every day after the planner is gone) and re-renders the drafts document from what that file stores.

### Removed

```
$ trec plan
Usage: trec [OPTIONS] COMMAND [ARGS]...
Error: No such command 'plan'.
```

### `trec agent install` / `uninstall` / `status`

```
$ trec agent install
LaunchAgent installed: ~/Library/LaunchAgents/local.teams-recorder.daemon.plist
Removed the old daily planner job (local.teams-recorder.planner).     # only when it existed
…
$ trec agent status
plist: … (exists)
loaded: yes (pid 812, running)
```

The planner line disappears from `agent status`. `trec agent restart` and `trec agent uninstall` remove the old planner job the same way (until it is removed, the installed job runs `trec plan --purge` at 18:00 and fails with exit 2; restart is the step the project already requires after a code change). The installer scripts (`scripts/install.sh`, `install.ps1`) no longer mention the 6 pm planner and remove the job.

### `trec doctor` (new line)

```
Activities document: data/activities/atividades.md (ok, last pass Mon 19/10 10:12)
```

or `not created yet (trec activities curate --since YYYY-MM-DD)`; or `2 meetings not curated (trec activities)` (failed or never attempted, last 10 working days).

### `trec status` (replaced line)

`Open actions: N` becomes `Activities: 7 yours · 3 waiting on others (last pass Mon 19/10 10:12)`.

## Config

```toml
[audio]
# Delete audio.m4a of meetings older than this many days that are already transcribed. Was
# [planner] retention_days (still read when this key is absent). The daemon runs it once a day.
retention_days = 30

[activities]
# After each analyzed meeting, an agent updates data/activities/atividades.md: adds what is new,
# suggests (💬) what was said as done, keeps everything you wrote. false = no automatic curation
# (neither the daemon nor `trec analyze`); the `trec activities` commands still work.
enabled = true
model = "claude-opus-5-5"   # with provider = "api"
cli_model = "opus"          # with provider = "claude-code"
effort = "medium"
# Send a notification when a pass changed something of yours.
notify = true
# Versions kept for `trec activities undo`.
keep_versions = 50

[stories]
# Stories are drafted only for items tagged #história, with `trec stories`.
guide = "prompts/user_story_guide.md"
destinations = ["backlog-md"]
publish = false
dedup_days = 30
```

- `[planner]` is removed (`hour`); `retention_days` moves to `[audio]`. The daemon schedules the purge in the background on the first tick of each day (never inline in the detector tick).
- `[stories] enabled` is removed (no automatic drafting). An old config that still has it loads, and the key is ignored.

## Notifications

| When | Title | Body |
| ---- | ----- | ---- |
| A pass changed something of the user's | `Activities updated` | the curator's one-line summary, e.g. `1 ação nova, 1 possível conclusão, prazo do cronograma mudou para sex 16/10` |
| A pass suspected an editor overwrite | `Activities updated` | summary including `itens devolvidos: o editor parece ter sobrescrito o arquivo` |
| A pass failed | `Activity curation failed` | `<meeting title> (<id>): <error>. It will be retried; or run trec activities curate <id>.` |

## Errors

| Condition | Surface | Message | Action |
| --------- | ------- | ------- | ------ |
| Meeting not analyzed | `curate <id>` | `Meeting <id> is <state>, not analyzed: run trec analyze <id> first.` | exit 1 |
| Unknown meeting id | `curate <id>` | existing `Meeting not found: <id>` | exit 1 |
| Model refused / truncated / schema / timeout / auth | pass | `curation_error.txt` = `Activity curation failed: <transport error>`; notification | retried by later passes (max 2 attempts) |
| Edits not applicable after the retry | pass | `Activity curation failed: <n> edits did not match the document (<first target, 60 chars>…)` | same |
| An edit would remove or change a checkbox without `archive` (after the repair round) | pass | `Activity curation failed: an edit would change a checkbox without archiving: <target, 60 chars>` | same |
| Curator busy | `undo` | `The curator is working; try again in a few minutes.` | exit 1 |
| Nothing to undo | `undo` | `No pass to undo.` | exit 1 |
| Another pass committed after the preview | `undo` | `A new pass ran while you were deciding; run trec activities undo again.` | exit 1 |
| Curator busy when the drafts are ready | `stories` | `The curator is working; the drafts are saved. Run trec stories again later to replace the tags.` | exit 0; tags replaced by the next run |
| Curation failed after a successful analysis | `analyze` | `Curating <title> (<dd/mm>)… failed: <reason>` | exit 0; retried by the daemon, or `curate <id>` |
| No document | `stories` | `No activities document yet: data/activities/atividades.md` | exit 1 |
| Story writer failure | `stories` | existing `Drafting failed: <error>`; tags untouched | exit 1 |
| LLM prerequisites missing | `curate`, `stories` | existing prerequisite message (key or `claude`) | exit 1 |
