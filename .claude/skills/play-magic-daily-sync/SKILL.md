---
name: play-magic-daily-sync
description: Use when asked to "Run the play-magic-daily-sync skill." Daily cron run (about 30 minutes, cheap model) that refreshes the Modern metagame snapshot, adds new real tournament decklists, finds new Scryfall sets and previews, lists the cards the magic-cards-model engine does not implement yet, lands one data-only PR and sends one report to the superleader. Never implements cards.
---

# play-magic daily sync (agent A)

Budget about 30 minutes. Silent except for the one final report. You must not implement
cards, edit engine code, touch `mtg-decks`, or ask questions: follow the decision log and
put doubts in the report.

## 0. Decisions first

Read `docs/automation/user-decisions.md` in the engine repo. Decisions in its log override
this skill where they differ.

## 1. Workspace

The API has a path dependency `../magic-cards-model` and `scripts/card_coverage.py` defaults to
`../magic-cards-model-api/decks`, so clone both as siblings:

```
mkdir -p ~/play-magic && cd ~/play-magic
git clone https://github.com/szymonrychu/magic-cards-model      # or git pull --ff-only if present
git clone https://github.com/szymonrychu/magic-cards-model-api
(cd magic-cards-model && mise trust && mise install && mise run install && mise run rules:pull)
(cd magic-cards-model-api && mise trust && mise install && mise run install)
```

Secret hygiene: never print or commit env values, tokens or `.env`. Before each commit, in
every repo committed to (engine and API), run `gitleaks git --pre-commit --staged --redact
--no-banner`; before each push, same repos, run `gitleaks git --redact --no-banner
--log-opts="origin/main..HEAD"`. Never `--no-verify`.

Work on branch `chore/daily-sync-YYYY-MM-DD` in the engine repo, cut from fresh `origin/main`.

## 2. State

`docs/automation/sync-state.json` holds `metagame_as_of`, `sets_seen`
(`{code: {name, released_at, card_count}}` at the last check) and `cards_reported`
(`[{name, set, date}]`). Read it; every report is a delta against it. Update it in this
run's PR.

Seeding: if `sets_seen` is empty, record all current Scryfall sets (types of step 4) without
processing them, and process only sets with a future `released_at` or released within the
last 30 days.

## 3. Metagame and decklists

1. `cd ~/play-magic/magic-cards-model && mise run metagame:fetch` (rewrites
   `docs/card_coverage/metagame.json`; note the new `as_of`).
2. List recent real Modern tournament decks with the repo client (no MCP SDK needed):
   ```
   uv run python -c "
   import json
   from scripts.spellslinger_client import MCPTransport, SpellslingerClient
   c = SpellslingerClient(MCPTransport())
   r = c.statistics_decks(format='modern', date_from='YYYY-MM-DD', limit=50, include_cards='full')
   json.dump(r, open('decks.json', 'w'))"
   ```
   with `date_from` a `YYYY-MM-DD` literal: the previous `metagame_as_of` (or 14 days ago when
   null). Read `decks.json` selectively (jq or python), never print it whole. Real lists only:
   never build a list from `statistics_archetypes` core cards. Check legality of every card
   with the spellslinger `resolve_cards` tool (`format="modern"`, `fields="legality"`).
3. Pick new top lists (best placing per archetype, not already in
   `../magic-cards-model-api/decks/` by pilot and date). Write each to a temp file and run
   `uv run python scripts/survey_cards.py --deck <file> --json`.
4. Fully supported and every card pooled (printings in
   `src/magic_cards_model/data/printings/`): add `decks/<archetype>.txt` in the API repo with
   the exact header
   ```
   # <Archetype> - pilot <Name>, YYYY-MM-DD, source <source>-<id>
   # mainboard 60, sideboard 15
   ```
   then `N Card` lines, a blank line, the sideboard lines (copy an existing file's layout).
   Open one API PR titled `feat(decks): add <archetype> list YYYY-MM-DD`, wait for API CI
   green (`gh pr checks <n> --watch`), squash-merge it.
5. A list with any unsupported or unpooled card is not added; its unsupported cards go into
   the report as new unimplemented cards (bucket and failing clause from the survey).

## 4. New sets and previews

1. `curl -s https://api.scryfall.com/sets` and keep sets whose `set_type` is `expansion`,
   `core`, `masters` or `draft_innovation`. Skip `digital`-only sets and every token,
   memorabilia, promo, funny, commander-only or box type. Keep sets with a future
   `released_at` (previews).
2. A set is new, or grown, when its code is not in `sets_seen` or its `card_count` is larger.
3. For each, in the engine repo: `uv run python scripts/card_coverage.py --set <code>`
   (fetches spoilers too; writes `docs/card_coverage/<NNN>-<code>/status.md`, plan.md and
   support-baseline.json). Collect rows of the "Cards needing work" table with bucket
   `not_working` and Legal (M/P/S) showing Y in the M slot (Modern-legal, or the set will be
   Modern-legal on release).
4. Also take any Not-working card present in the new metagame lists
   (`docs/card_coverage/000-metagame/status.md`).
5. The delta is those cards minus `cards_reported`. Append the delta to `cards_reported` with
   today's date and update `sets_seen` and `metagame_as_of`.
6. Do not hand-edit `plan.md` or `support-baseline.json`; if `card_coverage.py` changed
   `support-baseline.json` for a reason other than a new set, revert that file.

## 5. Landing

If `git status` shows no change in the engine repo, open no PR. Otherwise:

1. Stage only `docs/card_coverage/`, `docs/automation/sync-state.json`.
2. Run the staged gitleaks check, commit `chore(data): daily sync YYYY-MM-DD`, run the
   pre-push gitleaks check, push the branch.
3. `gh pr create --title "chore(data): daily sync YYYY-MM-DD" --body "<one paragraph: as_of, sets, counts>"`.
4. `gh pr checks <n> --watch`. Green: `gh pr merge <n> --squash --delete-branch`. Data-only,
   so no `test:full`. If CI is red because `main` is red, do not merge; report the error.
   If it is red because of your change, fix it once, else report.

## 6. Report

Find the superleader: `orchestrator_sessions_list`, the session with `superleader: true`
(never a hard-coded slug). Send exactly ONE `orchestrator_session_send` per run, containing:

```
play-magic daily sync YYYY-MM-DD: metagame as_of X, N new decks, M new unimplemented cards in sets a, b, PR #n merged
```

Only when M > 0, append the list grouped by set (name, set, bucket, failing clause when
available) and the final line:

```
Start the card implementor (skill play-magic-card-implementor) with this list.
```

Errors are one line each in the same message. Nothing else, no chatter. If the orchestrator
tools are missing or `orchestrator_session_send` fails, print the full report as the final
answer and, if a PR was merged, note the report in its body (`gh pr edit <n> --body ...`) so
the delta is not lost.
