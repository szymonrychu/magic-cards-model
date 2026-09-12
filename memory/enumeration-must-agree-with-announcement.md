---
name: enumeration-must-agree-with-announcement
description: legal_actions and legal_targets must ask the announcement machine's own question - a third reading of the same rule is a lie waiting to be found
metadata:
  type: project
  date: 2026-09-12
---

Three separate paths ask "what may this spell target" and "may it be cast right
now": `machines/casting.Casting` at announcement, `Game._resolution_profile` at
CR 608.2b's recheck, and `Game._announcement_profile`/`legal_actions` for a
caller that has not announced anything yet. Whenever one of them learns a rule
the others do not, the enumeration starts lying - and a lying enumeration is
worse than a missing one, because a seat trusts it.

Measured on 2026-09-12: `Casting.targeting` had read a split card's chosen half
since CR 709.3b was implemented, and `_resolution_profile` had been fixed to
agree. `_announcement_profile` was never taught, so `Action.target_slots` and
`Game.legal_targets` reported the **front** half's phrase on both rows of every
split card. Separately, `legal_actions` asked `why_cannot_cast_now` once per
card, ahead of its own loop over the halves, so it reported both halves of an
`Instant // Sorcery` card as castable at upkeep and neither half of a
`Sorcery // Instant` card as castable at all.

**How to apply:**
- A fix to `Casting` is not finished until `legal_actions` and
  `_resolution_profile` give the same answer. Grep for the other two callers.
- Build a row's candidates from the same call that built its slots
  (`_announcement_profile`), never a second read - that is what makes them
  incapable of disagreeing.
- `legal_actions` enumerating N variants of a cast (`spell_face`,
  `alternative_cost`, keyword) must ask every per-variant question **inside**
  the loop. A check hoisted above it silently answers for the wrong variant.
