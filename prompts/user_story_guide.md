# User story guide

This file is sent to the model every time it drafts user stories (`[stories] guide` in `config.toml`). It is the single source of how stories are written: edit it to match your team's conventions and the next draft follows the new rules. Keep it short and concrete, since all of it is read on every call.

## What becomes a story

- A story is product work: a change in how the product behaves for its users (a feature) or a fix for something that should work and does not (a bug).
- The meeting analysis already classifies actions; only features, bugs and actions extracted before classification existed reach this step. Technical and operation work become task cards and management and communication stay in the daily plan without you.
- For an unclassified action, write a story only for a feature or a bug. Leave out estimates, investigations, mocks, deploys, access requests, process changes, reports and metrics, and any communication (e-mails, meetings, follow-ups, reviews), with a short reason.
- When several actions lead to the same outcome, write one story. When one action hides two outcomes that can be delivered separately, write two.

## Bugs

Actions classified as `bug` describe something that should work and does not. Write them as stories too, with:

- Title starting with "Corrigir", naming the symptom: "Corrigir data de vencimento exibida no card".
- Story sentence: "Como <persona>, quero que <comportamento esperado>, para <benefício>."
- `details` with **Problema** (what happens today), **Esperado** (what should happen) and **Como reproduzir** (steps, when the meeting gave them; otherwise an open question asking for them).
- Acceptance criteria describing the corrected behavior, plus one criterion that the reported case no longer happens.

## Title

- Up to 10 words, starting with a verb in the infinitive and naming the outcome, e.g. "Exportar relatório de horas por projeto".
- No ticket prefixes or internal codes, unless the meeting used the code as the name of the system.

## Story sentence

- Use exactly this form: "Como <persona>, quero <capacidade>, para <benefício>."
- The persona is the real role that benefits, taken from the meeting (e.g. "analista financeiro", "gestor do contrato", "time de operações"). Never the bare word "usuário", and never the person who recorded the meeting unless they are the one who benefits.
- The benefit says why it matters, as stated in the meeting. If nobody said why, write the most direct benefit and add an open question asking to confirm it.

## Acceptance criteria

- 2 to 6 criteria, each in the form "Dado <contexto>, quando <ação>, então <resultado observável>."
- Each one must be checkable by someone who was not in the meeting: name the screen, file, field, value or message. Never "funcionar corretamente" or "ser rápido".
- A due date is planning, not a criterion. Put a deadline in the criteria only when it is a product rule (e.g. "o relatório fica disponível até o dia 5 de cada mês").

## Other sections (`details`)

Add these, in this order, only when there is content for them:

- **Contexto:** one or two sentences linking the story to the decision or problem raised in the meeting.
- **Fora de escopo:** what the meeting explicitly left out.
- **Dependências:** other people's actions, teams or systems the story waits for, with the owner when known.

## Open questions

- List what must be answered before work can start: missing values, undecided rules, unclear owner or persona. One question per item, phrased so it can be sent as is to whoever can answer it.

## Size

- A story must fit in one sprint (two weeks) for one person. When the outcome is bigger, split it into user-visible steps that can each be delivered and tested on their own.
