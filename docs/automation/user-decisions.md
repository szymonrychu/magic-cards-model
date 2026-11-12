# User decisions for the play-magic automation

Shared memory of the user's decisions. Both automation skills
(`.claude/skills/play-magic-daily-sync`, `.claude/skills/play-magic-card-implementor`)
read this file first, on every run. Decisions here override the skills.

Rules:

- Whenever the user answers a question (via the superleader, a task decision, or a
  session message), the agent that learned it appends an entry and lands it in its next
  PR (or in a tiny docs PR).
- Entries are append-only and never edited. Newest at the bottom of the log.
- Until a question below is answered, follow its working default.

Entry format:

```
### YYYY-MM-DD - <short topic>
Question: <verbatim>
Answer: <verbatim>
Source: <T-134 decision id | session slug | PR>
```

## Working defaults (pending answers)

The 8 open questions on T-134 (https://lab.szymonrichert.pl/tasks/T-134). The leader moves
each into the log below once answered. A = play-magic-daily-sync, B = play-magic-card-implementor.

1. Q1 decklists: A refreshes `docs/card_coverage/metagame.json` daily (`mise run metagame:fetch`)
   as a data-only engine PR, self-merged on green CI. New real top Modern tournament lists
   (`statistics_decks`, legality checked via `resolve_cards`) whose cards are all supported and
   pooled are added by A to the API repo `decks/` (API PR). Lists needing new cards are handed
   to B. `mtg-decks` is untouched.
2. Q2 formats: Modern only (new-set cards count when Modern-legal or when they will be on release).
3. Q3 scope: all Not-working cards of each new Modern-legal set, plus any Not-working card in
   current metagame lists.
4. Q4 previews: report as soon as a card is previewed on Scryfall. A re-reports a set while new
   previews keep arriving (only the delta).
5. Q5 hard cards: build missing subsystems generally (fix the mechanic, never the card). Only if
   truly impossible: strict xfail with a reason, listed in the summary.
6. Q6 merge: self-merge (squash) once the owner gate (engine `lint` + `test:full` on the rebased
   branch, API `lint` + `test` + `test:pg` against it) and GitHub CI are green and an
   independent reviewer subagent found no real issue.
7. Q7 deploy: B releases through an API PR to main (new decks, or a `chore(engine): ...` commit;
   conventional title so `scripts/next_version.py` bumps) and runs `mise run k8s:deploy X.Y.Z`
   in the API repo, then smoke-checks https://play-magic.szymonrichert.pl/ . If B lacks
   `mtg-engine` access, it stops after the image release and reports the version to the
   superleader.
8. Q8 questions: B sends the question to the superleader session, keeps working on other cards,
   and records the answer here.

## Log (append below)
