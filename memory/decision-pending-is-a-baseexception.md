---
name: decision-pending-is-a-baseexception
description: DecisionPending subclasses BaseException, not Exception, because the 3 bare except Exception and 42 except ValueError handlers measured across src/ would otherwise catch the pause and turn it into "the effect did nothing" - counts are grepped, not assumed
metadata:
  type: project
---

**2026-09-07.** `machines/decisions.DecisionPending` (raised when a question has
no scripted answer, no unconsumed tape entry, no provider, and
`DecisionScript.pause_when_unanswered` is set) derives from `BaseException`,
not `Exception`.

Measured with grep across `src/`, in this session, not assumed: **3** actual
`except Exception:` code sites (`models/game.py:2779`, `models/game.py:3491`,
`machines/cost.py:4290` - a fourth grep hit, `machines/triggers.py:465`, is a
docstring sentence describing one of the two `game.py` handlers, not a fourth
handler) and **42** actual `except ValueError:`/`except ValueError as ...:`
code sites in `src/` (grep matches 44 lines; 2 of those, both in
`machines/decisions.py`, are this module's own docstring prose naming the
pattern, not real handlers), concentrated in `machines/effects.py` (23 of the
42). Most of the `ValueError` sites are unrelated to resolution unwinding -
text-parsing fallbacks, `int()` coercions - but the ones that matter are exactly the three
`decisions.py`'s own docstring names as the reason this had to be a
`BaseException`: `Game.resolve_top`, `Game._resolve_ability`
(`models/game.py`), and `CostPayment.pay` (`machines/cost.py`), each of which
wraps effect resolution in a handler that unwinds the in-progress
resolution - sends the spell to the graveyard, discards the ability, unpays
the cost - before re-raising whatever it caught.

A `DecisionPending` that subclassed `Exception` would be indistinguishable
from an ordinary resolution failure to any of those handlers: it would be
caught, the in-progress spell or ability would be unwound as if it had
crashed, and the pause would silently become "the effect did nothing" - the
same silent-default failure shape `memory/silent-default-dispatch-tables.md`
already names as this codebase's dominant defect class, just reached through
exception handling instead of a lookup table. The whole point of pausing
instead of blocking or defaulting is that resolution is *suspended*, not
*failed* - the caller is expected to resume it later from the committed
snapshot (see [[pause-is-snapshot-plus-tape]]), which cannot happen if the
in-flight state has already been torn down by an unwind handler that thought
it was cleaning up after a crash.

`BaseException` is the standard library's own escape hatch for exactly this
shape - `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit` are its only
other direct subclasses, and none of them is meant to be caught by ordinary
`except Exception`/`except ValueError` code either. `Game.schema_version`'s
`SchemaVersionMismatch` made the same kind of choice for a different reason
(subclassing `RuntimeError` rather than `ValueError`, so pydantic-core does
not rewrap it) - see [[game-schema-version-fail-closed]] - and this is the
same instinct one level up: know exactly which handlers a raised signal must
survive, and choose a base class no accidental `except` clause in this
codebase will match.

Related: [[pause-is-snapshot-plus-tape]], [[silent-default-dispatch-tables]],
[[game-schema-version-fail-closed]].
