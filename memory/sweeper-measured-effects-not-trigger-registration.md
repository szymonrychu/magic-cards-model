---
name: sweeper-measured-effects-not-trigger-registration
description: 2026-09-08 - scripts/sweep_pool.py never called condition_matches, so a trigger whose condition could never fire still scored handled
metadata:
  type: project
---

`scripts/sweep_pool.py`'s "zero-silent-cards" number, the one `CLAUDE.md` and
`docs/engine-coverage.md` treat as a goal condition, classified a triggered
ability by whether `ability.event` parsed and whether `trigger_effect_for`
returned non-`None`. It never called `machines/triggers.condition_matches`
(CR 603.2) at all, so a trigger whose event parsed cleanly but whose printed
*condition* could never be satisfied by any real permanent still scored
`handled` - the sweep was a statement about `machines/effects.py`'s dispatch
tables, not about whether the trigger ever registers in a real game.

Weapons Manufacturing's "a nontoken artifact you control enters" is the
concrete case (`docs/2026-09-08-trigger-findings.md`): a substring guard in
`condition_matches` checks `"token" in lowered` without excluding "nontoken",
inverting the restriction, so no real nontoken artifact entering it ever fires
it. It scored `handled` on two counts before this fix - the event parsed, and
a text-fallback parser (`parse_mixed_effect`) produced a real callable by
misreading "deals 2 damage to any target" out of the granted token's own
*quoted* reminder text, not the trigger's own clause.

Both holes are now closed. `classify_clauses` runs a synthetic-permanent
closure (`_condition_can_fire`) against the production `condition_matches`
for the permanent-shaped event kinds (enters, dies, is sacrificed, attacks,
blocks, becomes tapped/untapped), and a condition that can never be satisfied
by any real, honestly-labelled permanent now scores a distinct
`UNMATCHABLE_CONDITION` bucket rather than folding into `SILENT` or hiding
behind `HANDLED`. A second closure (`_effect_matched_inside_quotes`) flags a
clause whose dispatcher answer depends on content inside a quoted span, by
blanking the quote to a neutral non-empty placeholder and checking whether the
dispatcher still answers - not by removing it outright, which would also
misfire on every legitimate "gains '<ability>'" grant (CR 113.10, Urza's
Saga) that genuinely needs its own quoted payload.

Closing the hole for real, not just for Weapons Manufacturing, caught two more
cards the report never named before: Ygra, Eater of All ("a Food is put into a
graveyard from the battlefield") and Blade of the Bloodchief ("a creature
dies") both hit the same underlying gap in `condition_matches`'s `DIES`
branch - a condition naming neither "this"/the source's own name nor
"another"/"other" never matches anything at all, self or other, which is a
different bug from the token/nontoken substring collision but the identical
escaping shape: readable event, unmatched condition. Ygra's was previously
scored fully `handled`, invisible to every prior sweep.

**2026-09-08, update**: while this closure was landing, `main` independently
fixed Weapons Manufacturing's own two holes (`30f2b07`) - the nontoken
substring collision, plus a broader `create a ... token named X with
"<ability>"` parser and an anchored `_DAMAGE_TARGET_RE` that closed the
quoted-text misparse too, not just the condition one. Rebasing this branch
onto that commit failed six tests that had asserted Weapons Manufacturing and
Miirym could never fire/always misparse - correctly, since neither is true
any more. Repointed at the two genuinely still-open cards (Ygra, Blade of the
Bloodchief) and added tests pinning that Weapons Manufacturing/Miirym now
report reachable, with no change to the closure logic itself. A real search
(fixture pool plus over a dozen real Scryfall printings sharing the same
"quoted payload" shape) found no card left in the pool exhibiting the
quoted-text misparse, and inspection of the three other unanchored-prefix
damage regexes in `machines/effects.py` found none of them can actually cross
a quote boundary at all - their `\.?$` suffix refuses the trailing `"` a
quoted grant's closing text always has, unlike the old, tail-permissive
`_DAMAGE_TARGET_RE`. `quoted_effect`'s own detector is pinned with a direct
unit test of its contract instead of a card.

The before/after full-pool numbers, measured on `origin/main` (`7d05007`,
after the nontoken and leaves-the-battlefield fixes, before this closure) vs.
this branch rebased onto it (715 cards with rules text): before, 134 silent /
392 handled / 26 notice / 163 static-unaudited. After, 133 silent / 391
handled / 26 notice / 163 static-unaudited / 2 unmatchable-condition / 0
quoted-effect. Net: Ygra moves `handled` -> `unmatchable_condition` (a new
catch); Blade of the Bloodchief moves `silent` -> `unmatchable_condition` (a
more precise diagnosis of an already-known gap). `docs/engine-coverage.md`'s
own zero-silent narrative needs to say what the number now actually measures
- it never did before this fix, and the count moves every time either the
pool or the engine does, so it is re-measured rather than quoted stale here.

Related: [[silent-default-dispatch-tables]], [[effect-registry-is-the-dominant-gap]],
[[verify-agent-findings-against-the-engine]].
