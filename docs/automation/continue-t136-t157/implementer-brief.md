# Implementer brief: play-magic trk batch (T-136)

You implement ONE batch of the plan `~/play-magic/plan.md`
(sections 1 and 2 for your batch) in the MTG rules engine magic-cards-model. You do not merge.

## Workspace (your own; never touch another batch's dir)

Home is NOT persistent (pod restarts wiped earlier attempts). Work only on the workspace
volume path below, commit WIP locally as you go, and push the branch (after the gitleaks
pre-push scan) as soon as the first tests pass, then after every meaningful step. If the dir
already exists with your branch, resume from it instead of re-cloning.

```
W=~/play-magic/<batch-id>   # e.g. .../ws/b1
mkdir -p $W && cd $W
git clone -q https://github.com/szymonrychu/magic-cards-model
git clone -q https://github.com/szymonrychu/magic-cards-model-api
for r in magic-cards-model magic-cards-model-api; do (cd $r && mise trust -q && mise install -q && mise run install); done
cd magic-cards-model && MISE_UNIX_DEFAULT_INLINE_SHELL_ARGS="bash -c" mise run rules:pull
git config --show-origin core.hooksPath   # must show ~/.config/git/hooks (global); never change it
```
(`rules:pull` fails under plain sh because of `${URL// /%20}`; the env var is the workaround.)
Branch: `git switch -c feat/<mechanic> origin/main` in the engine clone. The API clone stays on main
(its path dependency `../magic-cards-model` is your engine clone, so it tests your branch).
Logs of long runs: `~/play-magic/logs/<batch-id>-*.log`
(pipe through `tail -n 40` in your context, keep the full log there).

## Read first

engine `CLAUDE.md` (all of it: rules lookup, "Where a parser goes", target the mechanic,
no mocks, goldens), `docs/scenario-tests.md`, `docs/automation/user-decisions.md`, MEMORY.md
T-110 sections, `memory/verify-agent-findings-against-the-engine.md`.

## Binding rules

- Target the mechanic, never the card. Nothing name-keyed, no `if card.name == ...`, no regex
  fitted to one sentence. Prove generality with a second, differently worded REAL card
  (the plan names candidates; where none exists, vary the board inside the set, as T-110 did,
  and say so in MEMORY.md).
- Never state a CR rule from memory: `mise run rules:find -- <n>` (local `.rules/`) or the
  spellslinger MCP `knowledge_search(type="rules")` if available. Every CR number you write
  is looked up in this session.
- No mocks. Add real printings with `uv run python scripts/add_card.py "Name"`. One scenario
  file per mechanic in `tests/scenarios/`, corner cases as the bulk. Tests first (TDD: watch
  them fail, then implement).
- Goldens only via `mise run golden:update` (never hand-edited); review the diff. Run
  `mise run dispatch:fingerprint` when the winning parser changes.
- Parsers in the family module (CLAUDE.md table); add `before=`/`after=` edges demanded by
  `tests/test_dispatch_order.py`.
- A schema bump (`Game.schema_version`) is expected for new persisted union kinds; other
  batches may bump too, so the later merge takes the next number on rebase.
- Update `docs/engine-coverage.md` and re-run
  `uv run python scripts/card_coverage.py --set trk` for `docs/card_coverage/297-trk/status.md`.
- Non-obvious decisions into engine `MEMORY.md` under a heading `## T-136 <batch-id>: <mechanic>`,
  dated 2026-11-12, with the why. Hard cards: build the subsystem generally; only if truly
  impossible, a strict xfail with a reason (never a bare skip), and report it.
- Never print or commit env values or `.env`. No em dashes or smart quotes anywhere.

## Memory: heavy runs take the pod lock (the pods were OOMKilled at 8 GiB)

Several batches share one pod. Every heavy run (any `pytest` over more than a few files,
`mise run test*`, `golden:update`, `coverage:baseline`, `card_coverage.py`, `regression:guard`,
API `test`/`test:pg`) MUST run under the pod-wide lock and with at most 4 workers:

```
L=~/play-magic/heavy-$(hostname).lock
flock $L mise run test:full -- -n 4    # or: flock $L uv run pytest ... -n 4
```
(`card_coverage.py`/`coverage:baseline`: `--workers 4`.) Single scenario files may run without
the lock. Push the branch as soon as it has commits (after the gitleaks pre-push scan) and
after every commit thereafter.

## Owner gate (all must pass, on the branch rebased on fresh origin/main)

Engine: `mise run lint`, `mise run test:full`.
API repo (engine clone = your branch): `mise run lint`, `mise run test`, `mise run test:pg`
(if test:pg cannot run here for lack of Docker/Postgres, say so precisely; CI covers it).
Ratchet: `mise run regression:guard -- --repo . --base $(git merge-base origin/main HEAD) --ratchet`
shows no regression. `mise run coverage:baseline` only when cards legitimately improved
(it should: commit the regenerated baseline).

## Land the PR (do not merge)

1. Before each commit: `gitleaks git --pre-commit --staged --redact --no-banner`.
   Conventional commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
   Never `--no-verify`.
2. Before push: `gitleaks git --redact --no-banner --log-opts="origin/main..HEAD"`. Any finding:
   stop and report, do not push.
3. `git push -u origin feat/<mechanic>`, `gh pr create` title `feat(<area>): <mechanic> (<n> cards)`,
   body: cards, mechanics, proof printings, CR rules used, test summary, gate results, and last
   line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
4. `gh pr checks <n> --watch` until green; on red read the log tail, fix, re-gate the changed
   parts, push again.

## Report (final reply, at most 200 words)

PR number and URL, CI state, cards now working (survey_cards.py output summary line per card),
cards xfailed with reason, schema version bumped to, any question that needs the user (with your
recommended answer), anything surprising.
