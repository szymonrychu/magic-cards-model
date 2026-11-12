# Review of PR #48 (magic-cards-model, batch B3)

Scope: Hit It!, Deep Space 9, Temporal Conqueror, First Contact (+ proofs Shigeki, Patient Naturalist). Reviewed read-only from a scratch copy of the clone at 4d593b644.

Verdict: FIX FIRST (one real-blocker: stale status.md; everything else is minor). No rules or design defect found.

## Verified OK
- All CR numbers cited (601.2i, 707.10, 117.1a, 101.3, 608.2c, 608.2d, 701.17a/b/c, 111.10a, 406.1, 503.1a, 609.3, 110.4a, 110.2a, 701.20a/b, 603.6a) checked with `rules:find`: each says what is claimed.
- ruff check and format: clean. The 4 new scenario files: 28 passed. test_game_schema_version, test_dispatch_fingerprint, test_split_gates: pass. The behavioural sweep (-k on the 6 cards) was not awaited to completion; CI must show it green.
- No name-keyed behaviour: `_nth_spell_this_game` is any-ordinal / any-subject; fallback and tail are generic; no card names in src.
- Real printings only, no mocks; every new printing has the real Scryfall oracle text. No goldens are touched (no trk goldens exist in the repo; consistent with earlier trk PRs).
- Persisted state is data: `Game.spells_cast_this_game: dict[str,int]` and `CastRecord.caster/cast_number_this_game` are pydantic fields with defaults, `game_class.json` surface updated, schema 178 -> 179 with a docstring entry in the right (descending) place, dump/reload round-trip test present. Insertion-ordered dict, deterministic.
- Rules logic of the count: stamped in `_put_on_stack`, which is reached only by the two real cast paths (`_casting.py:824` cast-during-resolution, `:2392` normal cast) so casts from any zone count, copies never do (copies never reach it), a cast that fails (ValueError, payment rewound) is never counted because it raises before `put_on_stack`. Stamp is fixed at cast, so a spell cast in response does not steal "first". Counted per caster, so an opponent's spell does not count. Correct.
- Parsers sit in the right family modules (conditions/cast_record.py, effects/library.py, merges.py, removal.py, modal.py).
- Second differently worded proof: Hit It! / Shigeki (look vs reveal, mandatory vs may, "and the rest" vs own sentence), Temporal Conqueror / Patient Naturalist (graveyard vs milled). Documented reasons for the two single-card mechanics (Deep Space 9 "exiled this way"; First Contact) are acceptable.

## Findings

1. real-blocker - docs/card_coverage/297-trk/status.md not updated. It still lists Deep Space 9 (line ~35), First Contact, Hit It!, Temporal Conqueror as `silent` / not_working and the bucket counts are unchanged (Tested 99 ...). Every earlier trk PR (#35, #36, #39, #45) regenerated it in the same PR. Regenerate with scripts/card_coverage.py and commit.

2. real-minor - schema 179 collides with open PRs #46 and #49, which also set `CURRENT_SCHEMA_VERSION = 179` (src/magic_cards_model/models/game/__init__.py:2020). Whichever merges second must rebase and take 180 (and move its docstring entry); also tests/dispatch_fingerprint_baseline.json will conflict. Merge-order note, not a defect here.

3. real-minor - src/magic_cards_model/machines/effects/library.py:6070-6095 (`_parse_mill_then_return_to_hand_clause`) and :6326-6333 (milled runner): the "refused after a may" branch (`return None` when `optional`/not `mandatory`) has no test. tests/scenarios/test_if_you_cant_fallback.py only exercises the mandatory shapes. Add one negative test (text with "you may return ... If you can't, ..." stays unread / fails closed) so the CR 101.3 vs declined-option rule is pinned.

4. real-minor - tests/scenarios/test_spells_cast_this_game.py: the claim "casts from other zones count" is not pinned. Add one case casting First Contact (or any spell) from a non-hand zone (flashback, or cast-during-resolution path at _casting.py:824) and assert the count increments and the stamp is set. The two call sites are the only counters; only one is tested.

5. nit - library.py:6249 `_mill_then_may_take_from_milled_runner` return type loosened from `Callable[["Game", Player, str, str | None], None]` to `Callable[..., None]`; the real signature gained an optional `stack_object` param, so a precise Callable (5th arg `StackObject | None`) keeps the type check.

6. nit - library.py:6236-6240 the new `tail` group accepts any trailing sentence of the mill-take shape (read the ordinary way, fail-closed if unreadable). Fine and covered by the dispatch fingerprint, but First Contact is its only proof; worth one line in the coverage row saying the tail is generic.

7. nit - docs/engine-coverage.md new section: row 4 lists 117.1a (instant timing) as a CR for the "spells cast this game" mechanic; it is only relevant to the test, not the reader. Harmless.

8. nit - MEMORY.md new section: "Noted, not doing now" for Once Upon a Time / Approach of the Second Sun is stated; fine.
