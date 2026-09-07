---
name: flow-based-auto-tap-source-grouping
description: replacing auto-tap's exponential combinations() search with a max-flow network only works if a permanent's several abilities are grouped into one provider node first - two independent nodes for Eldrazi Temple's {C} and {C}{C} abilities let their capacities sum (1+2=3 from one land, one {T})
metadata:
  type: project
---

**2026-09-07.** T8b (`machines/cost.py`, `models/mana.py`) replaced
`_solve_auto_tap`'s `combinations(candidates, size)` search (5-28,678 combos on
a real 17-source board, up to 8.2s for `{5}{B}{B}`) with a max-flow extension
of `ManaPool`'s own bipartite network: `models/mana._assign_sources` adds one
layer, `demand -> bucket -> permanent -> sink`, with the permanent -> sink cut
(`capacity[permanent]`) doing the work `_assign`'s bucket -> sink cut already
did. Kept the old search as `_solve_auto_tap_brute_force`, a test-only oracle
`tests/scenarios/test_auto_tap_flow_property.py` checks against on random
boards (0 disagreements across 450 generated trials).

**The trap that would have shipped a silent over-count**: `_auto_tap_candidates`
returns one tuple per *(source, ability)* pair, so Eldrazi Temple - a free
`{T}: Add {C}.` and a restricted `{T}: Add {C}{C}.` - is two entries. Feeding
both straight into the flow network as two independent provider nodes lets
their capacities add: a `{2}{C}` cost (converted 3) would read as payable off
Eldrazi Temple alone (1 + 2 = 3), which is two taps from one land and a direct
violation of CR 118.3 ("a permanent that's already tapped can't be tapped to
pay a cost"). Fix: `_group_by_source` folds a permanent's several abilities
back into one node - the alternatives it offers - *before* anything asks
whether it needs branching. A permanent with only one alternative (however
much mana, however many colours - a boosted Tron piece) is always flow-safe;
one with several alternatives is flow-safe exactly when every alternative is
a single mana of a single colour (an ordinary dual, Cavern of Souls's free
{C} beside its restricted any-colour choice - genuine CR 106.6 choices
included, since each alternative can carry its own restriction slot); a
permanent whose choice includes an alternative of more than one mana -
Shang-Chi's `{T}: Add two mana of any one color.`, the only card in the pool
shaped that way - is branched over explicitly instead of handed to the
network, the same way the old brute force always did, but only over *it*.
`test_eldrazi_temple_never_sums_its_two_abilities` (`test_auto_tap_flow.py`)
is the regression test for the bug this would otherwise have shipped.

The `{5}{B}{B}` benchmark board still runs at ~80ms after the fix, unchanged
from `{R}`'s own baseline - the combinatorial exponential is gone, but a
separate, pre-existing cost dominates: `_auto_tap_candidates` calls
`can_tap_for_mana`/`_activation_refused`/`_mana_narrowings`, each of which
consults `Game.computed_board()`/`characteristics_of` per source, uncached
across repeated calls or even across sources within one call (~9 recomputes
per source on this board). Out of scope for this task - it already dominated
the trivial `{R}` case before any of this work - and not fixed here.
