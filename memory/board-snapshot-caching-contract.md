---
name: board-snapshot-caching-contract
description: Game.computed_board is cached only inside an explicit Game.board_snapshot() scope (legal_actions opens one); any engine-model field assignment, mutating Game command, or Counters/ManaPool edit drops the cached board, and an unannounced in-place edit raises BoardSnapshotStale
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
  scope `computed_board` recomputes on every call, exactly as before - the
  "continually" reasoning in its docstring still holds. Inside
  `Game.board_snapshot()` (nested scopes share one board) the board is computed
  once and reused. `machines.legal_actions.legal_actions` opens one itself; the
  api is expected to wrap its state serialisation and `legal_actions_before` in
  one too.

**What invalidates it** (drops the board; the next read recomputes):

1. Any public field assignment on any engine model. Every pydantic model in the
   package is built on `snapshot.EngineModel` (`Counters` mixes in
   `AnnouncesMutation`), and `tests/test_models_announce_mutation.py` refuses a
   model that opts out. Private attributes (`_board_source`,
   `_asking_the_board`) do not announce.
2. Any mutating `Game` command: `Game._id_allocator_scope` suspends the
   snapshot for its whole extent, so a command's own reads are never cached
   whatever order it edits lists and assigns fields in.
3. `Counters.add/remove/set` and `ManaPool`'s in-place edits announce
   explicitly.

**What raises instead**: an in-place list/dict edit outside any command, or a
caller writing into a returned `ComputedBoard`. Neither can be seen as it
happens, so a JSON fingerprint of the game and of the board is taken when the
board is cached and compared at the next announced change and at scope exit;
a mismatch raises `BoardSnapshotStale`. `snapshot.uncached_boards()` turns
caching off (the equivalence tests compare against it);
`snapshot.board_computations()` is the real counter the count test reads.

**The trap found while landing it**: read-only parsing that builds a model
and then assigns its fields (`_parse_activated` filling in a fresh
`ManaAbility`) announces a mutation like any other assignment, and silently
cost the whole benefit - 69 boards instead of 1. Build fresh models with
constructor arguments or `model_copy(update=...)` on read paths.
`tests/scenarios/test_board_snapshot.py::test_legal_actions_computes_the_board_a_constant_number_of_times`
is what catches a regression.
