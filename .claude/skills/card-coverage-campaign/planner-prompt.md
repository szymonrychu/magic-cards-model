# Planner prompt template (round planner, model: opus)

Fill every `<...>` placeholder before dispatching this as an `Agent` prompt
with `subagent_type: "fork"` unset (fresh agent - the planner does not need
the orchestrator's conversation), `model: "opus"`. This template, and the
COMMON ACCEPTANCE text inside it, is copied verbatim from the proven
`silent-plan.md` campaign format - do not paraphrase the acceptance clauses,
copy them exactly as printed here.

---

You are planning round `<ROUND_ID>` of the magic-cards-model card-coverage
campaign: `<ROUND_LABEL>` (e.g. "expansion 187-ecl, Lorwyn Eclipsed" or
"Round 0, metagame decks").

Engine repo: `/Users/szymonri/Documents/magic-trainer/code/magic-cards-model`
(work read-only here; you are not implementing, only planning - do not
create a worktree or edit engine files).

## Inputs

- This round's coverage report(s): `<STATUS_MD_PATHS>` (one or more
  `docs/card_coverage/<NNN>-<code>/status.md` files, or for Round 0 the deck
  files listed in `docs/card_coverage/plan.md`'s Round 0 row). Each lists
  every non-full card with its status (silent/notice/unaudited/error), worst
  clause, reason, and legal formats, plus a "Missing mechanics" section
  already clustering failing clauses by shared wording - start from that
  clustering, it is usually most of the work.
- `docs/card_coverage/plan.md`'s own `## Notes` and `## Missing mechanics`
  roll-up, for cross-set context (a mechanic failing here may already be
  scoped in a round that hasn't landed yet - don't duplicate it).
- Owner rule, binding: every card legal in Modern, Pioneer or Standard must
  be fully supported - never silent, never notice-only, never left
  unaudited without a scenario proving the static ability actually works.

## 1. Re-classify on current main

The status.md files may be stale by the time you read them (another round
may have landed since). Re-check every listed card against **current**
engine main before planning around it:

```sh
mise exec -- uv run python scripts/sweep_pool.py --card "<name>"
```

or, for many cards at once, a short throwaway script calling
`magic_cards_model.support.card_support` directly (see
`src/magic_cards_model/support.py`'s own docstring). **Do not read the whole
bulk Scryfall dataset or the whole engine source tree to do this** - targeted
lookups only; conserve tokens.

Drop any card that is now fully handled (already fixed by a round that
landed since the status.md was generated). Report the drop count at the end.

## 2. Cluster by TEMPLATE, never by card

Group the remaining failing clauses by the **printed wording shape** (the
"Missing mechanics" section already gives you a starting clustering - verify
it, don't blindly trust it, since the clustering is a text heuristic, not a
rules judgement). One task = one template or a small set of closely related
templates, owning a **disjoint set of files** so tasks can run in parallel
worktrees without touching each other's code.

**At most 8 tasks.** If the round has more distinct templates than that,
broaden task scope (more templates per task) rather than exceeding 8 - but
**every remaining card of the round must be named in exactly one task's
`requirement`**. No card silently dropped for scope reasons.

## 3. Write the plan

Write `<PLAN_OUTPUT_PATH>` (a scratch file, NOT under `docs/`): a fenced
` ```json ` block, a JSON array of task objects, this exact schema:

```json
{
  "id": "T1",
  "title": "<short description of the template(s)>",
  "repo": "magic-cards-model",
  "requirement": "Cards: <name>; <name>. Behaviour: <precisely what each proof/listed card must do, with CR numbers you have looked up this session - never from memory>. Proof printings (candidates, verify): <second, different-wording printing per mechanic, legal in Modern/Pioneer/Standard, NOT a listed card and NOT in magic-cards-model-api/decks/*.txt or mtg-decks decks>. Test files: <paths>. COMMON ACCEPTANCE: (a) `mise exec -- uv run python scripts/sweep_pool.py --card \"<name>\"` for every listed card (and its `A // B` full-name form where the sweep lists one) shows every clause `handled` - no `silent`, no `notice`; every `static_unaudited` clause on a listed card is proven working by a scenario test. (b) Target the template, never the card: no card-name rows in EFFECTS/TRIGGER_EFFECTS/ACTIVATED_EFFECTS, no `if card.name`/name-set gate, no regex fitted to one printed sentence. (c) Every reader added or widened is proven by a scenario on a second printing legal in Modern, Pioneer or Standard that is not a listed card and not in magic-cards-model-api/decks/*.txt, added with `uv run python scripts/add_card.py \"<name>\"`, legality and oracle text verified with resolve_cards before use. The named proof cards are candidates: if one is not legal or does not carry the template, substitute another legal printing found with card_search and record the substitution as a dated MEMORY.md line. (d) Scenario tests in tests/scenarios/, one mechanic per file, corner cases as the bulk, real printings only, no mocks; the conftest round-trip/replay check passes. (e) Every CR number written (code, docstring, test, docs) is verified with `mise run rules:find <n>` (`mise run rules:pull` first in a fresh worktree). (f) Game.schema_version is bumped only if a new persisted field is added, to the next free version at merge time, with tests/test_game_schema_version.py updated. (g) `mise run dispatch:fingerprint` regenerated and tests/dispatch_fingerprint_baseline.json committed. (h) docs/engine-coverage.md gains a section/rows for each mechanic closed, and MEMORY.md one dated line per non-obvious decision or dead-end. (i) `sweep_pool.py --effects`: no card outside this task becomes silent or notice (compare before/after); no listed card ends on a fail-closed notice. (j) Any subsystem a listed card needs is built in this task, not deferred.",
  "files": ["<paths this task owns exclusively>"],
  "notes": "Round <ROUND_ID>. Dependencies: <none, or another task id in this round that must merge first>. Owns: <the specific reader functions/regexes this task owns, by name>. Do not edit reader functions owned by another task in the same round; if a shared helper must change, keep the change additive and note it in MEMORY.md.",
  "verify": "mise exec -- uv run pytest <this task's test files> tests/test_dispatch_fingerprint.py -q && mise run lint",
  "model": "opus | omit for sonnet - opus only for hard rules reasoning (layers, replacement effects, copy, control change); omit (defaults to sonnet) otherwise",
  "reviewModel": "opus | sonnet, matching model",
  "review": true
}
```

Set `"model": "opus"` **only** for genuinely hard rules reasoning (layers,
replacement effects, copying, control-change effects); omit it (sonnet)
otherwise - cost discipline, per the owner's standing subagent-model rule.

## 4. Write the scoped plan text

Write `<PLANTEXT_OUTPUT_PATH>`: a short (a few sentences)
`"SCOPE OF THIS RUN: round <ROUND_ID>, tasks <list of ids>. Already done:
<earlier rounds/sets, one line>. Deferred: <later rounds, one line>."` -
this is what `workbench:plan-execute` shows each task's implementer as
overall context; keep it short.

## 5. Return

Return **only**:

1. One line: `TASKS=<PLAN_OUTPUT_PATH> PLANTEXT=<PLANTEXT_OUTPUT_PATH>`
2. A count of cards dropped as already handled (with names, if 10 or fewer;
   otherwise just the count).

No other prose. Conserve tokens throughout: do not read large files whole
(the bulk Scryfall snapshot, the whole `effects.py`), do not explore beyond
what clustering the round's own cards requires.
