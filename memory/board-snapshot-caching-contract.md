---
name: board-snapshot-caching-contract
description: Game.computed_board is cached only inside an explicit Game.board_snapshot() scope (legal_actions opens one); invalidation is per game (a change to a model reachable from that game, or a command on it, in any thread), the signal lands after the value, closed scopes never serve, and an unannounced in-place edit raises BoardSnapshotStale
metadata:
  type: project
---

**2026-09-14.** A profiled Boros Energy vs Dimir Frog game showed
`legal_actions` rebuilding the layered board once per permanent and per
ability (135 boards at 5 permanents, 191 at 12; 775 ms at 25), with 97% of the
time in re-parsing every permanent's oracle text (`_parse_line`).

Two fixes, both behaviour-identical:

- **Sentence parse memo.** `abilities.layer_readable_sentences` and
  `layers._effect_sentences` are `lru_cache(maxsize=16384)` over every argument
  (text, `known_keywords` as a tuple, `static_only`, `card_name`), returning
  tuples; the public functions hand each caller a fresh list. The uncached
  bodies stay as `_layer_readable_sentences_uncached` /
  `_effect_sentences_uncached`, and `tests/test_oracle_sentence_memo.py` checks
  memo against uncached for every printing in the pool.
- **Scoped board reuse** (`src/magic_cards_model/snapshot.py`). Outside a
  scope `computed_board` recomputes on every call, exactly as before. Inside
  `Game.board_snapshot()` (nested scopes share one board) the board is computed
  once and reused. `machines.legal_actions.legal_actions` opens one itself; the
  api wraps its state serialisation and `legal_actions_before` in one too.

**What invalidates it** (drops the board; the next read recomputes) - only for
the game the change belongs to:

1. A public field assignment on a model reachable from that game. Every
   pydantic model in the package is built on `snapshot.EngineModel`
   (`Counters` mixes in `AnnouncesMutation`), and
   `tests/test_models_announce_mutation.py` refuses a model that opts out.
   Which game a model belongs to is the set of model ids reachable from the
   game (private attributes included), walked lazily on the first change that
   has to be placed and kept until a model-valued assignment or a command's end
   moves the game's `structure` counter. Private attributes do not announce.
2. A mutating `Game` command: `Game._id_allocator_scope` enters
   `snapshot.command(game)`. Nothing is cached for that game anywhere while it
   runs, and its end moves the game's epoch for every thread and task - which
   is what covers the zone lists it edits in place, and a mutating thread that
   holds no scope of its own.
3. `Counters.add/remove/set`, `ManaPool`'s in-place edits and
   `CostPayment._register_pool/_unregister_pool` (the `open_payment_pools`
   dict Omnath's effect reads) bracket the edit with `announce_mutation(model)`
   and `mutation_landed(model)`.

A change to another game, or to a model no open scope's game reaches (a model
a read path is filling in), invalidates nothing and takes no lock; the lock on
the assignment path is per game and only when that game has a scope open.

**Race-free epoch.** Each tracked game has its own epoch. A field store moves
it before and after the store; a command at its end. A board is cached only if
nothing but the computing context's own announcements (a computation stamps
permanents) moved the epoch while it was computed, and no command was running
on the game, so a board computed from the old value always carries a dead
epoch once the new value is in place.

**Closed scopes.** A scope is marked closed when it ends, and a closed snapshot
is never read from or cached into - a context copied inside the scope
(`asyncio.create_task`, `copy_context()`) computes afresh afterwards. On exit a
scope removes only its own entry from the context's mapping (no
`ContextVar.reset`), so scopes on two games may end in any order.

**What raises instead**: an in-place list/dict edit outside any command, or a
caller writing into a returned `ComputedBoard`. A JSON fingerprint of the game
and of the board is taken once when a board is cached and compared when this
context next announces a change to that game and at scope exit; a mismatch
raises `BoardSnapshotStale`. The game comparison is skipped when the epoch has
moved or a command is running (that change was announced, possibly by another
thread); the board comparison always runs. Fingerprints never run per read.
`snapshot.uncached_boards()` turns caching off (the equivalence tests compare
against it); `snapshot.board_computations()` is the real counter.

**Traps found while landing it.** Read-only parsing that builds a model and
assigns its fields (`_parse_activated` filling in a fresh `ManaAbility`)
announced like any other assignment and cost 69 boards instead of 1 under the
first, global invalidation; build fresh models with constructor arguments or
`model_copy(update=...)` on read paths. Per-game invalidation then exposed
`CostPayment._register_pool` writing `game.open_payment_pools` in place outside
a command - the old global drop had hidden it by coincidence, because an
unrelated announcement happened to drop the board first. The two-thread tests
in `tests/scenarios/test_board_snapshot.py` pause the writer before every
pydantic field store and every in-place list/dict edit with a profile
function, and let the reader read at each pause, so every interleaving is
exercised without a sleep.
