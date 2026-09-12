---
name: tap-plan-reported-not-discarded
description: the auto-tap solve was run twice per action and thrown away both times - plan_mana_payment returns it and could_pay_mana_cost became `is not None`; the ability index a plan entry reports is read back off the hoisted candidate scan, because re-deriving it through tap_for_mana's own search cost 12% of a legal_actions enumeration
metadata:
  type: project
---

**2026-09-10.** M3 (`machines/cost.py`, `machines/legal_actions.py`,
`models/action.py`). `_solve_auto_tap` had always returned a full plan -
which permanent to tap, what colour to make it add, CR 106.6's restriction on
that mana - and `could_pay_mana_cost` reduced it to `plan is not None` and
discarded it, only for `auto_tap` to solve the identical question again when
the action was taken. `plan_mana_payment` now returns the plan and
`could_pay_mana_cost` is literally `plan_mana_payment(...) is not None`, so
there is one implementation of "can this be paid" rather than a predicate and
an executor that could drift. `machines/legal_actions` reports it on
`Action.pays_with`, gated on the action owing mana at all *and* the whole cost
being affordable.

It is deliberately **informational only**. No entry point takes one back in,
and nothing asks a seat to name mana sources - `auto_tap` still offers every
untapped source and stops as soon as the pool can pay (CR 118.3c). A
`<card_id>:<ability_index>` request syntax was considered and explicitly
retracted: it is a "how do I pay" affordance for a case the agent should never
be in. What the plan answers is a "what" question worth inference - *which* of
my sources this spell eats.

Two things worth remembering about the ability index each entry carries.

First, `tap_for_mana`'s "which of this permanent's abilities is this tap
activating" search was inlined in `_tap_for_mana_impl` and is now
`_activated_mana_ability`, module-level and pure, taking a `_SpendContext` as
happily as a live `CostPayment`. That is what lets a report and a tap share
one answer.

Second - and this is the non-obvious part - `mana_ability_index` does **not**
take that path in the enumeration. Asking `_activated_mana_ability` per plan
entry costs a `computed_board` survey each time, and measured **137ms -> 154ms
per `legal_actions` call** on a twelve-permanent board (~12%), on the one code
path whose module docstring demands it stay cheap. Every plan entry was built
out of exactly one row of the `candidate_scan` `legal_actions` already hoists,
so the index is now carried on `_ScannedCandidate` and read back off that scan
by (source id, restriction, offered options) - free, and arguably the more
faithful answer, since it names the ability the *solver* chose rather than
re-deriving one. `_filter_candidate_scan` drops the index again on the way
into `_Candidate`, so nothing in the flow solver ever sees it. The
`_activated_mana_ability` path remains as the fallback for a caller with no
scan, and a scenario asserts the two agree.

`ManaPlanEntry` carries a `name` beside its `card_id`, breaking `Action`'s
otherwise absolute "ids only, never a name" rule on purpose: this rides on an
enumeration a seat reads in one pass, and re-resolving a dozen uuids against
the board to discover one of them is a Cavern of Souls is exactly the round
trip the enumeration exists to avoid. The id is still the identity. Its
`restriction` field is dropped from the serialized entry when absent
(`model_serializer(mode="wrap")`) rather than emitted as null, because a plan
rides on every affordable action and the null would be pure weight on every
unrestricted land in the game.
