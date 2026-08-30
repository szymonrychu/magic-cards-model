---
name: silent-default-dispatch-tables
description: Every defect class found by the playtest loop so far is a dispatch table that silently defaults instead of refusing - look for the else branch
metadata:
  type: project
---

The dominant defect shape in this codebase is **a lookup that silently falls
back instead of refusing**. Four independent playtest defects turned out to be
the same pattern:

- `machines/effects.py` keys effects by CARD NAME; a card with no entry resolves
  and does nothing. (Guide of Souls, 2 of 8 fetchlands, 63/85 instants.)
- `Game.trigger_targets` was a dict keyed by card name defaulting to `[]`, so a
  targeted trigger went on the stack with no targets and did nothing - and
  reused a stale entry for a second copy of the same card.
- `machines/triggers.py`'s `condition_matches` returns False for any condition
  shape it cannot read, so 11 triggers never fired at all.
- The API's `decide` endpoint knew 2 of the engine's 9 `DecisionKind`s; the
  other 7 parked for the full timeout and took the default, so the player
  silently lost the choice. This one was *introduced* while fixing the third.

In every case the code was correct for the entries it had and wrong by
omission, and in every case the failure was invisible: no log line, no warning,
a game state that looked plausible.

**How to apply:**
- When you add a producer, enumerate the consumer's full domain. A table that
  can be *asked* nine kinds of question must answer nine or refuse loudly.
- Prefer parsing behaviour out of oracle text over a name-keyed table; where a
  table is unavoidable, make the miss branch shout.
- A silent default and an explicit refusal are not equivalent: **a wrong game
  state that looks right is worse than an unimplemented one.** Fail closed.
- Distinguish "could not answer" from "chose not to answer" in logs. Conflating
  them is what hid the `decide` gap.
- The `resolved`/`changed` fields added to the game log exist to expose exactly
  this: an effect that resolves and changes nothing is the signature.

Related: [[effect-registry-is-the-dominant-gap]], [[autonomous-playtest-loop]],
[[verify-agent-findings-against-the-engine]].
