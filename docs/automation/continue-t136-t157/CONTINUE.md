# Continue T-136 (trk 29 cards) and T-157 (chorus counters) locally

Wrapped up on 2026-11-12 ~21:30Z by user decision m849 (stop, hand off to a local terminal).
All code lives on the PR branches below; nothing is unpushed. This branch carries only these
notes. The other files in this folder are the run's working documents: `plan.md` (card survey
and batch plan), `implementer-brief.md` (rules every batch followed), `resume-override.md`
(gate overrides used on the 4-CPU / 8 GiB pod), `review-48-b3.md` and `review-50-88-t157.md`
(independent review findings still open). Paths in them under `/workdir/...` were pod paths;
locally read them as `~/play-magic/...`.

## State per PR (szymonrychu/magic-cards-model unless noted)

| PR | Batch / cards | Head | CI | Review | Still to do |
|---|---|---|---|---|---|
| #45 | B4 layer static grants (4) | merged | - | - | done (schema 178) |
| #44 | B7 search variants: Andromedan Automatons, Captain Jean-Luc Picard | dbd4e50d9 | green | fixed | behaviour sweep + ratchet, merge |
| #46 | B6 turn-scoped delayed triggers: The Inner Light, Will Riker, The Wrath of Khan I | a483a9e86 | green | fixed | behaviour sweep + ratchet, merge (schema 179) |
| #47 | B8 mana choice + counter kind: Dal R'El, Dathon | 747b0cd39 | green | fixed | see B8 note below; sweep + ratchet |
| #48 | B3 library onto battlefield: Hit It!, Deep Space 9, Temporal Conqueror, First Contact | 4d593b644 | green | fix first | `review-48-b3.md`: regenerate trk status.md, two missing tests; schema collides with #46/#49 |
| #49 | B1 conditional instead + player choices (6) + rules:pull sh fix | b436eb21a | green | not reviewed | review; rebase (branch still on schema 178, take next free); sweep + ratchet |
| #51 | B5 hand exile + linked returns: All Good Things..., Salt Vampire, The Measure of a Man, Wrath II (branch `feat/hand-exile-and-linked-returns-r2`) | e94e31b47 | 1 red check | not reviewed | read the red log, fix; review; sweep + ratchet |
| #52 | B2 copy variants (5) (branch `feat/copy-variants-rebased`) | a4203ff61 | green | not reviewed | review; sweep + ratchet |
| #50 | T-157 engine: open named counter kinds, Malcolm (+ Blademane Baku proof) | d99a78758 | running | fix first | `review-50-88-t157.md`: missing golden `tests/golden/malcolm-alluring-scoundrel/triggered-0.json`, reader over-matches "Each player discards...", 3 untested variants, Malcolm last-known-counters xfail (small fix in `conditions/objects._there_are_counters_on`) |
| API #88 | T-157 API: PATCH accepts named counters | 0b87ad78a | running | mergeable | validate all counter names before applying any (atomic); merge AFTER #50 |

B8 note: a `(?!if)` guard added in `machines/effects/dispatch.py` makes Balin's, Chandra's and
Reckless Handling's "If ..., deals 2 damage to each opponent" clauses fall to unhandled (before,
they dealt damage with the condition dropped). Fix by reading the conditional clause properly,
with tests on those real cards, and check the ratchet. The last agent was adding a narrowness
test for that guard.

Decision 464 (All Good Things IV) is answered and recorded by #51 in
`docs/automation/user-decisions.md`.

## Setup (once)

```sh
mkdir -p ~/play-magic && cd ~/play-magic
git clone https://github.com/szymonrychu/magic-cards-model
git clone https://github.com/szymonrychu/magic-cards-model-api
for r in magic-cards-model magic-cards-model-api; do
  (cd $r && mise trust && mise install && mise run install)
done
cd magic-cards-model && mise run rules:pull   # on main it needs bash: MISE_UNIX_DEFAULT_INLINE_SHELL_ARGS="bash -c" (fixed in #49)
```

The API repo uses `../magic-cards-model` as a path dependency, so the engine checkout is what the
API tests run against.

## Per PR, in this merge order

Suggested order (smallest conflict surface first): #44, #46, #47, #52, #49, #48, #51, #50, then API #88.
Each later PR conflicts on `Game.CURRENT_SCHEMA_VERSION`, `MEMORY.md`, `docs/engine-coverage.md`,
`docs/card_coverage/297-trk/status.md` and `tests/dispatch_fingerprint_baseline.json`.

```sh
cd ~/play-magic/magic-cards-model
gh pr checkout <n>
git fetch origin && git rebase origin/main          # schema: take the next free number on conflict
mise run dispatch:fingerprint                        # if dispatch changed; commit the baseline
uv run python scripts/card_coverage.py --set trk     # commit status.md
mise run lint
uv run pytest tests/scenarios/<the PR's scenario files>
mise run test:behaviour                              # full behavioural sweep (CI does NOT run it)
mise run golden:update                               # only for intended behaviour changes; review the diff
mise run regression:guard -- --repo . --base $(git merge-base origin/main HEAD) --ratchet
(cd ../magic-cards-model-api && mise run lint && mise run test && mise run test:pg)
gitleaks git --redact --no-banner --log-opts="origin/main..HEAD"
git push --force-with-lease
gh pr checks <n> --watch
gh pr merge <n> --squash --delete-branch
```

Unreviewed PRs (#49, #51, #52) need an independent review first (engine rules: no name-keyed
behaviour, a second real card per mechanic, CR numbers looked up with `mise run rules:find -- <n>`,
no mocks, goldens only via `golden:update`, every new triggered/activated ability has a golden).

## After the last merge

1. `mise run coverage:baseline` on main, commit `docs/card_coverage/support-baseline.json` in a
   small PR (batch PRs deliberately did not touch it).
2. Release: API repo PR `chore(engine): trk 29 cards and named counters` that appends one line to
   `docs/engine-releases.md` (date, engine main sha, cards/mechanics); version via
   `scripts/next_version.py` (patch). Merge, wait for the `images` job, then
   `git fetch --tags && git tag -l 'v*' --sort=-v:refname | head -1`.
3. Deploy: `cd ~/play-magic/magic-cards-model-api && mise run k8s:deploy X.Y.Z` (bare version), watch
   `kubectl -n mtg-engine rollout status deploy`. Currently deployed: 0.7.1.
4. Smoke: `curl -sS -o /dev/null -w '%{http_code}\n' https://play-magic.szymonrichert.pl/` (302 from
   oauth2-proxy is the normal answer).
5. Close T-136 and T-157 on the task board.

## Gotchas from this run

- A full `test:behaviour` sweep takes about an hour on 4 CPUs; never run several suites in parallel
  on a small machine (the agent pods were OOMKilled at 8 GiB).
- Open PR #40 (`feat/trk-b6-v2`, from T-110) is not part of this work and touches trk files.
- CI test shard 11 `test_the_full_pool_classifies_within_budget` is a CPU-timing test that can flake;
  rerun the failed job before changing code.
