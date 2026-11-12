---
name: play-magic-card-implementor
description: Use when asked to "Run the play-magic-card-implementor skill for: <card list or 'the latest daily report'>". Long Opus run that implements the missing mechanics for unimplemented cards in the magic-cards-model engine (one PR per mechanic), merges them through the owner gate, releases through the API repo, deploys to play-magic and reports to the superleader.
---

# play-magic card implementor (agent B)

Long run. Implement the mechanics behind the listed cards, merge, release, deploy, report.

## 0. Read first

1. `docs/automation/user-decisions.md` (answered decisions and working defaults override
   this skill).
2. Engine `CLAUDE.md`, `ROADMAP.md`, the tail of `MEMORY.md`, the titles of `memory/*.md`
   (open the relevant ones; `memory/subagents-on-cheaper-model.md` says dispatch subagents
   with `model: "sonnet"`; use opus only for a hard mechanic), and `docs/scenario-tests.md`.
3. Engine rules that bind every change:
   - Target the mechanic, never the card. Nothing name-keyed, no `if card.name == ...`, no
     regex fitted to one sentence. Prove generality with a second, differently worded real
     card.
   - Never state a CR rule from memory: `knowledge_search(type="rules")` (spellslinger MCP)
     or `mise run rules:pull` then `mise run rules:find -- <n>`.
   - No mocks. Add real printings with `uv run python scripts/add_card.py "Name"`. One scenario
     file per mechanic in `tests/scenarios/`.
   - Goldens only via `mise run golden:update` (never hand-edited, commit the reviewed
     diff). Run `mise run dispatch:fingerprint` when the winning parser changes.
   - Parsers go in the family module under `machines/effects/` (CLAUDE.md "Where a parser
     goes"); add `before=`/`after=` edges demanded by `tests/test_dispatch_order.py`.
   - Update `docs/engine-coverage.md` and the set's `docs/card_coverage/<NNN>-<code>/status.md`
     (re-run `uv run python scripts/card_coverage.py --set <code>`).
   - Non-obvious decisions go into `MEMORY.md` with date and why.

## 1. Workspace and hygiene

```
mkdir -p ~/play-magic && cd ~/play-magic
git clone https://github.com/szymonrychu/magic-cards-model      # or git pull --ff-only
git clone https://github.com/szymonrychu/magic-cards-model-api
(cd magic-cards-model && mise trust && mise install && mise run install)
(cd magic-cards-model-api && mise trust && mise install && mise run install)
```

Siblings are required (API path dependency `../magic-cards-model`). One git worktree per
mechanic branch inside the engine repo's parent dir. Never print or commit env values or
`.env`. Before each commit: `gitleaks git --pre-commit --staged --redact --no-banner`.
Before each push: `gitleaks git --redact --no-banner --log-opts="origin/main..HEAD"`.
Never `--no-verify`.

## 2. Main must be green

`gh run list --repo szymonrychu/magic-cards-model --branch main --limit 1` and the same for
`magic-cards-model-api`. If either is red, fixing main (own PR, owner gate) is the first job.

## 3. Input

The card list from the start prompt. If it says "the latest daily report" or is absent,
recompute: newest `docs/card_coverage/*/status.md` rows with bucket `not_working` for sets in
`docs/automation/sync-state.json`, plus `docs/card_coverage/000-metagame/status.md`.
Re-verify each card before working: `uv run python scripts/survey_cards.py "Name" ...`
(a card may be fixed already; drop it).

## 4. Plan

Group the cards by the mechanic that blocks them (the failing clause). One PR per mechanic or
tier, as in the trk campaign PRs #29-#40. Order: cards in the current metagame first, then by
number of cards a mechanic unlocks. Keep the plan in the workspace, not in the repo.

## 5. Per PR

1. Branch `feat/<mechanic>` from fresh `origin/main`. Dispatch implementation subagents
   (sonnet for straightforward mechanics, opus for hard ones) with the rules of step 0
   in the brief. Verify their findings against the engine yourself.
2. Tests first (superpowers:test-driven-development): scenario tests with real printings,
   second differently worded card, interactions around the mechanic.
3. Owner gate on the branch rebased on `origin/main`, engine repo:
   `mise run lint` and `mise run test:full`; then in the API repo (engine checkout = the
   branch): `mise run lint`, `mise run test`, `mise run test:pg`.
4. Ratchet: `mise run regression:guard -- --repo . --base $(git merge-base origin/main HEAD) --ratchet`
   must show no regression. `mise run coverage:baseline` only when cards legitimately improved.
5. gitleaks, push, `gh pr create` with a conventional title (`feat(<area>): <mechanic> (<n>
   cards)`), `gh pr checks <n> --watch` until green.
6. Independent review by a sonnet subagent via superpowers:requesting-code-review. Fix real
   findings (superpowers:receiving-code-review), re-run the gate for the changed parts.
7. `gh pr merge <n> --squash --delete-branch`, then one line to the superleader (step 9).

## 6. Hard cards (working default Q5)

Build the missing subsystem generally; fix the mechanic, never the card. Only if truly
impossible, a strict xfail with a reason (never a bare skip), listed in the final summary.
CLAUDE.md `SWEEP_DRIVER_GAPS` is for sweep cases the harness cannot drive.

## 7. Release and deploy (working default Q7)

The engine has no release; images pick up engine main at the next API main build.

1. API repo: open a PR to main that carries the release, either the new decks from daily-sync
   or a `chore(engine): pick up <PR titles>` change (a PR needs a diff: append one dated line
   to the API `MEMORY.md`; conventional title; `scripts/next_version.py` gives feat=minor, `!`=major, else patch).
2. `gh pr checks <n> --watch`, squash-merge, then wait for the API CI `images` job to push the
   tag: `git fetch --tags && git tag -l 'v*' --sort=-v:refname | head -1` -> `vX.Y.Z`.
3. Deploy: `cd ~/play-magic/magic-cards-model-api && mise run k8s:deploy X.Y.Z` (the single
   argument is the bare version `X.Y.Z`; env alternative `MTG_VERSION`). Watch the phases:
   CNPG ready, migration Job `mtg-migrate-X.Y.Z` complete, Deployment rollout
   (`kubectl -n mtg-engine rollout status deploy`).
4. Smoke check: `curl -sS -o /dev/null -w '%{http_code}\n' https://play-magic.szymonrichert.pl/`
   returns 200; optionally sanity-play a new card through the mtg-sim MCP.
5. If `kubectl` lacks write access to namespace `mtg-engine`, stop after the image tag and
   report the version to the superleader. Never deploy a sha tag.

## 8. Questions (working default Q8)

Ask only what the user must decide. Batch them in one message to the superleader with
`orchestrator_session_send` (find it: `orchestrator_sessions_list`, `superleader: true`, never
a hard-coded slug), each question numbered with your recommended answer. Then keep working on
other cards. When an answer arrives, append it verbatim to `docs/automation/user-decisions.md`
(format in that file) and land it in your next PR, or a tiny docs PR.

## 9. Reporting

Only to the superleader: one line per merge or deploy (`PR #n merged: <mechanic>, <k> cards`),
errors as one line, and a final summary: cards done and tested, xfailed with reason, PRs,
released version, deployed yes/no, open questions. Then `orchestrator_self_close` if it
exists. Without orchestrator tools, print the same text as the final answer.

## 10. Context limits

Near the context limit write `handoff-YYYY-MM-DD.md` in the workspace (`~/play-magic/`), NOT
in the repo and never committed: plan, done, in-flight branches and PRs, next steps, gotchas,
no secrets. Tell the superleader that you handed off and where the file is.
