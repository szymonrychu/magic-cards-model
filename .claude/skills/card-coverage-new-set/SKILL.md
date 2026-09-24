---
name: card-coverage-new-set
description: Use when a new Magic set is released, or previewed ahead of its street date (spoiler season). Fetches the set from Scryfall - including not-yet-released spoiler cards - classifies every Standard/Pioneer/Modern-legal card with the engine's own support oracle, writes docs/card_coverage/<NNN>-<code>/status.md, and updates plan.md with the set's row and its missing-mechanics note.
---

# Card coverage: new set

## When this fires

- A set's spoiler season has started (Wizards previews are up on Scryfall) but
  the set has not released yet.
- A set just released.
- The human names a set and asks for its coverage status to exist or be
  refreshed right now.

## What it produces

One `docs/card_coverage/<NNN>-<code>/status.md` (created or refreshed) and an
updated `docs/card_coverage/plan.md` row + missing-mechanics note for that
set. `scripts/card_coverage.py` (repo root) does the classification; this
skill is the procedure around it.

## Procedure

### 1. Get the set code

Scryfall's 3+ letter lowercase code, not the display name. If unsure:

```sh
curl -s -H "User-Agent: magic-cards-model/0.1" \
  "https://api.scryfall.com/sets" | python3 -c \
  'import json,sys; [print(s["code"], s["name"], s["released_at"]) for s in json.load(sys.stdin)["data"][:15]]'
```

or search by name at `https://api.scryfall.com/sets/<code>` once you have a
guess. Spoiler-season sets are already listed there with a future
`released_at`.

### 2. Fast, real-time single-set refresh

The Scryfall **search** endpoint (`cards/search?q=e:<code>`) reflects a card
the moment Wizards/Scryfall adds it - same day, not next bulk-data snapshot.
This is what makes the campaign usable *during* preview season, when new
cards land every few hours:

```sh
mise exec -- uv run python scripts/card_coverage.py --set <code> --workers 8
```

This writes/refreshes only `docs/card_coverage/<NNN>-<code>/status.md`
(assigning it a fresh number if it doesn't have one yet - the number is
stable from here on) without touching any other set's file. Use this as
often as you like while a set is actively spoiling - it's cheap (a handful of
HTTP calls plus a sub-second classification pass).

### 3. Sync plan.md (and every other set) against the same data

`--set` mode deliberately never touches `plan.md` - it's a narrow, fast path.
To fold this set's numbers into the campaign-wide plan (its row, its
contribution to the missing-mechanics roll-up, the overall coverage table),
run the full generator too:

```sh
mise exec -- uv run python scripts/card_coverage.py --refresh-bulk --workers 8
```

`--refresh-bulk` forces a fresh `oracle-cards`/`default-cards` download so
this set's newest spoilers (which may be more current than the last cached
bulk snapshot) are reflected everywhere, not just in its own file. This is a
full regeneration - every other set's `status.md` is rewritten too - but it
is deterministic and preserves every `## Notes` section and every round's
`state` column verbatim (see `scripts/card_coverage.py`'s own docstring), so
nothing a human wrote is lost, and nothing you haven't touched actually
changes content-wise. On real data this takes well under a minute (~10-30s
depending on network).

Skip this step only if you are going to run it again very soon anyway (e.g.
several `--set` refreshes back to back during one preview-season session) -
do it at least once before you finish, so `plan.md` is never left stale.

### 4. Mark provisional legality when the set hasn't released yet

**Before a set releases, its Pioneer/Modern legality is not final** - only
Standard legality for a new premier set is something Wizards commits to at
preview time. Scryfall's own `legalities` field on a spoiled card usually
already reflects "will be Standard legal, not yet Pioneer/Modern legal", but
say so explicitly for a human reading the report:

1. Check the set's release date (the status.md header's "Release date"
   line, or `https://api.scryfall.com/sets/<code>`'s `released_at`).
2. If that date is in the future relative to today, and the set is a premier
   Standard-legal set (not a Commander-only/supplemental product), open
   `docs/card_coverage/<NNN>-<code>/status.md` and, **if its `## Notes`
   section does not already say "Provisional"**, add one line there:

   ```
   Provisional: <Set Name> has not released yet (release date <date>).
   Standard legality is assumed; Pioneer/Modern legality is not final until
   release - re-run this skill after release to confirm.
   ```

   This survives every later regeneration (Notes are preserved verbatim), so
   it only needs adding once, and it gets removed by hand once the set has
   actually released and been re-verified.
3. If `plan.md`'s row for this set doesn't already flag it, append
   `(provisional)` after the set name in its Campaign-order row, or add a
   one-line note under `plan.md`'s own `## Notes` naming the set. Same
   idempotency rule: don't duplicate the marker on a re-run.

### 5. Report

Say, in a few lines: the set code and name, its expansion number, cards in
scope and the tested/works/partial/not-working split, whether it's
provisional, and the two or three biggest entries in its "Missing
mechanics" section (these are the campaign's next likely work items, but
**this skill does not do that work** - `card-coverage-campaign` does).

## What this skill does not do

- It does not implement anything. A silent/notice card found here is a
  finding, not a task - `card-coverage-campaign` turns findings into TDD
  work.
- It does not move a round's `state` column (todo/in-progress/done) -
  `card-coverage-refresh` does that, from actual engine progress.
- It does not commit. Leave the regenerated docs for the human or the next
  skill to review and commit alongside real work, unless explicitly asked to
  commit a docs-only refresh on its own.
