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

The before/after full-pool numbers (715 cards with rules text): before, 133
silent / 394 handled / 25 notice / 163 static-unaudited. After, 131 silent /
392 handled / 25 notice / 163 static-unaudited / 4 unmatchable-condition / 0
quoted-effect. Net new problem cards found: 2 (Weapons Manufacturing, Ygra);
2 more (Miirym, Blade of the Bloodchief) moved from `silent` to the more
precise `unmatchable_condition`. `docs/engine-coverage.md`'s own zero-silent
narrative needs to say what the number now actually measures - it never did
before this fix.

Related: [[silent-default-dispatch-tables]], [[effect-registry-is-the-dominant-gap]],
[[verify-agent-findings-against-the-engine]].
