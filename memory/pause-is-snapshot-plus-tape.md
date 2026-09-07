---
name: pause-is-snapshot-plus-tape
description: Why a paused game is (last committed Game, the command, the answers so far) rather than a pending field on Game - a half-applied game mid-resolution is not a legal state to persist, and a deterministic id allocator makes replaying it re-derive the identical pause
metadata:
  type: project
---

**2026-09-07.** `machines/decisions.py`'s `DecisionPending`/`PendingDecision`
replace a live `DecisionProvider` that blocked the resolving thread. The
obvious alternative - a `pending: PendingDecision | None` field on `Game` - was
not built. Two reasons, both in the module's own docstring:

Every site that can raise mid-resolution would have to maintain that field by
hand, and there are many of them - `Game.resolve_top`, `Game._resolve_ability`,
`machines/cost.py`'s `CostPayment.pay`, each of which already wraps effect
resolution in a bare `except Exception` or `except ValueError` that unwinds the
in-progress resolution (sends the spell to the graveyard, discards the ability,
unpays the cost) on any ordinary failure. A `pending` field would need every
one of those unwind paths taught not to discard it, and the game snapshotted at
the exact half-applied moment - a spell partway through resolving, state-based
actions not yet run, the ability popped off the stack but not restored - is not
a legal state this engine's own invariants describe. It is not `Game`'s job to
represent "in the middle of executing a spell."

Instead a paused game is the triple `(last committed Game, the command that was
running, the answers recorded so far)`. Resuming is replay, not a checkpoint:
there is no mid-effect state to save, so a caller re-runs the exact same
command from the last committed snapshot, with the answers already given fed
back through `DecisionScript.recorded`/`.consumed` (read positionally, oldest
first - see `DecisionScript.take_from_tape`). The mutated `Game` from the
paused attempt is discarded, never stored, which is what makes double-applying
an answer structurally impossible: there is nothing left to apply it to twice.

What makes this actually reproduce the identical pending decision rather than
a plausibly-similar one: `ids.py`'s allocator is deterministic per `game_uid`
(`uuid5` of `game_uid` and `Game.objects_created`), installed for the span of
every id-minting `Game` method through `_id_allocator_scope`. Replaying the
same command from the same committed snapshot mints the same ids in the same
order, so the replay's `PendingDecision` is the same question with the same
`seq` - `DecisionScript.begin_replay` is what resets `asked`/`consumed` so that
numbering restarts at 0 exactly like the first attempt's did, rather than
carrying forward a stale count. Because the intermediate state is never
written down, only ever re-derived, an illegal half-applied game can never end
up persisted anywhere a caller could read it back.

`DecisionPending` derives from `BaseException`, not `Exception` - see
[[decision-pending-is-a-baseexception]] for why, since it is the same
unwind-safety concern from the other direction: the pause has to pass through
those same `except Exception`/`except ValueError` unwind handlers undisturbed,
not be caught and treated as an ordinary failure by them.

Related: [[decision-pending-is-a-baseexception]],
[[harness-deadlock-defaulted-every-decision]],
[[scenario-round-trip-replay-invariant]].
