---
name: could-pay-mana-cost-predicate
description: the pure "could this cost be paid" predicate could not build a CostPayment at all (for_total registers a pool into game.open_payment_pools) - _SpendContext duck-types CostPayment's three read-only fields instead, and Card had to become frozen=True to make the new ability-parse caches sound
metadata:
  type: project
---

**2026-09-07.** T8a (`machines/cost.py`) split `auto_tap` into `_solve_auto_tap`
(pure search) plus a thin executing `auto_tap`, and exposed the search as
`could_pay_mana_cost` for legal-action enumeration. The search's own helpers
(`_auto_tap_candidates`, `_mana_context`, `_mana_narrowings`,
`_activation_refused`, `_among_colors`) all took a `payment: CostPayment` but
only ever read `.game`/`.payer`/`.spend` off it - `CostPayment.for_total` is
the only constructor that registers a working pool into
`game.open_payment_pools[payer]` (via `_seed_payer_pool`/`_register_pool`), so
a predicate calling it would leak a dead pool even if nothing ever read it
back out. Fix: `_SpendContext`, a frozen dataclass carrying just those three
fields, passed wherever the search used to take a `CostPayment` - `auto_tap`
still passes `self` (structurally identical), `could_pay_mana_cost` passes a
throwaway context and reads the payer's floating pool directly instead of
going through `for_total` at all.

Same task memoised `parse_abilities`/`activated_abilities_of` on `Card.id` and
`supertypes_of` on the type line string (162,815 re-parses of the same 18
sources' text for one `{3}{W}{W}` affordability question). Both are sound only
because `Card` never mutates after construction - which was a docstring
claim, not a pydantic guarantee, until this task added `frozen=True` to
`Card.model_config`. That broke one pre-existing test
(`test_targeting.py::test_mutating_a_card_in_one_game_is_not_observed_through_another_games_profile`)
that mutated a `Card.name` in place to prove a cache-identity fix; rewritten to
assert the two `Card` objects are simply never the same reference, since the
mutation path it relied on no longer exists.

Checked whether `Game.colors_could_produce`'s recursion guard
(`skip_could_produce_abilities`) is call-scoped or an instance attribute,
since an instance attribute would make the new predicate impure - it is a
plain keyword argument threaded through the one recursive call
(`_could_produce_survey`), never stored on `self`. No fix needed there.
