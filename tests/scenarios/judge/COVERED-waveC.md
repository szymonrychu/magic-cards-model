# Wave C - DDR episodes converted from the on-disk transcripts

To be merged into `COVERED.md`. Same conventions apply: a newer episode
outranks an older one, and an existing passing test is never rewritten to
match an older transcript.

This wave read the raw transcripts directly from
`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/` rather than harvesting
them through `knowledge_search`, so no episode in the slice was lost to a
truncated excerpt the way DDR#1015/#1012 were in earlier waves. Every card was
verified with `resolve_cards` and every CR number with
`knowledge_search(type="rules")` in the session that wrote these tests.

| Episode | Ruling | Where |
|---|---|---|
| DDR#986 | Superior Spider-Man entering *as a copy* of a graveyard card is a CR 614.1c replacement effect with no `replacements_of` row, so no copy, no acquired ETB trigger, and nothing exiled | `test_judge_copying.py` (two passing halves + xfail) |
| DDR#983 | two attack triggers under one controller do both reach the stack, but `Game.put_triggers_on_stack` never offers CR 603.3b's ordering choice, and neither card's CR 118.12 "you may ... if you do" clause has a scripted effect | `test_judge_triggers.py` (three passing halves + xfail) |
| DDR#981 | Panharmonicon has no `LAYER_EFFECTS` row and no trigger-multiplying machinery, and Lagrella's enters trigger has no scripted effect - the engine reaches the episode's *counter* answer for the wrong reason, and misses its *exile* answer | `test_judge_triggers.py` (two passing halves + xfail) |
| DDR#32 | Purelace's "target spell or permanent" really can target a spell on the stack, but `effect_for('Purelace')` is `None` and Clone's enter-as-a-copy has no replacement row, so CR 613.3's "CDAs first within layers 2-6" never gets exercised | `test_judge_copying.py` (passing half + xfail) |
| DDR#980 | a token copy of an animated land, and its copy-effect-granted ETB fight - `effect_for` is `None` for both Jolrael and Aggressive Biomancy | `test_judge_copying.py` (passing half + xfail) |
| DDR#979 | suspend's "your upkeep"/"you may play it" belong to the card's **owner** (CR 109.5), never to whoever performed the exile - `finish_suspend` reads `ExileAnnotation.owner`, which is the exiling player | `test_judge_suspend.py` (two passing halves + xfail) |
| DDR#977 | a *targeted* copy ability is removed from the stack when the spell it targets is countered in response (CR 608.2b/608.3b) - **the engine already gets this right**; the untargeted contrast case (Flamehold Grappler copying off last known information) does not | `test_judge_copying.py` (passing + xfail) |

## Policy episodes - no rules test possible

- **DDR#65** ("How does Tardiness Work?") - entirely tournament policy: the
  competitive-rel game loss for arriving late, its downgrade to a warning
  under one minute, the tournament-error upgrade path (second and subsequent
  offences, unlike gameplay errors' third), the other forms of tardiness (a
  late decklist, exceeding the ten minutes allowed to replace missing cards),
  the ten-minute cutoff after which the absent player is treated as a no-show
  and dropped, requested delays, and rounds started early. No game state at
  all.
- **DDR#985** ("Going to time while shuffling for game 3") - tournament
  policy: once time is called no new game begins, and shuffling, presenting,
  and mulligans are all pregame procedure, so the game is not underway until
  both players have kept. A restart (Karn Liberated's -3, per the episode's
  garbled "K") is officially ending the current game and starting a new one,
  so it evaluates identically. The rest is slow play / stalling, which is
  subjective by construction. Nothing here is a rules fact the engine models.
- **Special Clip - "Reversing Decisions"** (2025-10-31) - MTR policy, not
  rules: a player may take back a decision only if they have gained no new
  information since communicating it, plus the judge-craft around applying
  that (rel, relevance of the information, elapsed time, player interviews).
  No game state to build; the engine has no notion of a communicated decision
  being retracted at all.

## Reviewed and skipped this wave

(none - all ten episodes in the slice produced a test or a policy entry)

## Conflicts between episodes

None found: no episode in this slice contradicts a test already in the repo.
Two related observations recorded here rather than acted on, since neither is
an episode conflict:

- **DDR#981 gets the right number for the wrong reason.** The engine puts no
  +1/+1 counters on anything, which happens to match the episode's "no
  additional counters" answer. The episode's *other* half - Panharmonicon
  genuinely doubling Lagrella's enters trigger, so the exile happens twice -
  is not modelled. `test_panharmonicon_does_not_make_lagrella_trigger_twice_here`
  pins the current behaviour down and says so explicitly, so a later wave
  feeding Panharmonicon into the engine can tell the two apart.
- **Purelace's targeting requirement is narrower than its printed text.**
  `targeting_profile(card("Purelace"))` builds one requirement for "target
  spell or permanent" whose `zones` is `{Zone.STACK}` alone, so the parse
  would refuse the "or permanent" half. Not DDR#32's point (the episode laces
  the Clone *spell*), so it is logged here rather than turned into a test.
