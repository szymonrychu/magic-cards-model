# DDR episodes covered - wave A (to be merged into COVERED.md)

Wave A worked from the **raw transcripts on disk**
(`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/`) rather than from
`knowledge_search` excerpts, so every ruling below was read in full rather than
inferred from a truncated chunk. Twelve episodes, newest first, each with an
outcome.

Every CR number written in this wave's tests was verified with
`knowledge_search(type="rules")` in the session that wrote them; every card's
text was verified with `resolve_cards` before use.

| Episode | Ruling | Where |
|---|---|---|
| DDR#1009 | "Any number of target spells" is CR 107.1c's zero-or-more, a Trap aimed at one spell has exactly one target, a spell may not target itself (CR 115.5), and the alternative cost leaves the mana cost and mana value alone (CR 118.9c). Not modelled: the sentence-form alternative cost, and exiling a spell off the stack | `test_judge_mindbreak_trap.py` (6 passing + 2 xfail) |
| DDR#1008 | Each Parallel Lives is its own replacement effect (CR 616.1) with one opportunity each (CR 614.5), so N of them multiply the token count by 2^N - the mechanism behind the episode's 2^5 = 32 | `test_judge_token_doublers.py` (5 passing) |
| DDR#666 | Ante (CR 407) is not modelled: `Zone` is CR 400.1's seven zones plus a sideboard, with no ante zone, so nothing can be anted and Jeweled Bird's ability is unscripted | `test_judge_ante.py` (1 passing + 2 xfail) |
| DDR#1007 | "Hexproof from [quality]" (CR 702.11d) and CR 702.11f's shorthand are unmodelled - **and worse**: Scryfall's `keywords` field carries a bare "Hexproof" alongside "Hexproof from", which `Casting._hexproof_refusal` reads, so Nevinyrral gets full hexproof (CR 702.11b) and refuses spells the printed card allows | `test_judge_hexproof_from.py` (2 passing + 1 xfail) |
| DDR#1006 | CR 106.7's "could produce" is unmodelled in both directions: Reflecting Pool parses to *no* mana ability at all, and Exotic Orchard parses to an unconditional any-colour one that ignores what the opponent's lands could make. `models/mana.Color` is CR 106.1b's six types in one enum, so the color/type distinction the episode opens with cannot be represented | `test_judge_mana_could_produce.py` (2 passing + 2 xfail) |
| DDR#1004 | A trigger caused by *paying an activation cost* (CR 602.1a, 602.2a-b) goes on the stack above the ability it paid for (CR 603.3) and resolves first (CR 608.1) - Blood Artist's drain lands before Vampiric Rites' draw | `test_judge_cost_payment_triggers.py` (4 passing) |
| DDR#1003 | A keyword *granted* to a spell by another permanent's static ability (Ashling's "gain evoke {4} as you cast them") is not read at all, so neither the grant nor CR 400.7b/611.3d's survival of the granter's death can be shown | `test_judge_granted_evoke.py` (1 passing + 2 xfail) |
| DDR#1002 | A creature that began the game on the battlefield attacks on turn one with no haste (CR 508.1a, 302.6, 702.10b), one that arrived during the turn may not, and the legend rule waits for the first state-based-action check (CR 704.3, 704.5j). The pregame procedure itself (CR 103.1-103.3) is not modelled | `test_judge_starting_the_game.py` (3 passing + 1 xfail) |
| DDR#1000 | Both players losing at one state-based-action check is a draw (CR 104.4a, 704.5a, 704.5b, 121.4); a spell with one of two targets now illegal still resolves (CR 608.2b) | `test_judge_practice_exam_rules.py` (4 passing) |
| DDR#999 | "Whenever one or more cards are put into a library from anywhere" has no `TriggerEvent` shape at all, so Wan Shi Tong never triggers - neither on a Brainstorm (which should) nor on a scry (which should not, CR 701.22a) | `test_judge_put_into_library.py` (2 passing + 1 xfail) |

## Policy episodes - no rules test possible

- **DDR#1005** (When can players agree to break the rules) - entirely
  tournament policy: which MTR/IPG rules two players may dispense with by
  agreement (sideboard presentation, a revealed top card, an agreed-on partial
  fix for a missed Thalia tax), which they may not (bribery, using a sideboard
  card as a token, skipping a mandatory Essence Warden trigger to save time),
  and the philosophy behind the difference. No game state to build.
- **DDR#1000b** (L2 Practice Exam - Policy) - fifteen questions, all IPG/MTR:
  theft and disqualification, free vs. derived information at regular and
  competitive rel, missed triggers and whether they are detrimental, looking at
  extra cards vs. hidden card error, deck list problems, game rule violations
  and partial fixes, mulligan procedure errors, the "go to combat" shortcut,
  and who plays first after a drawn game. Nothing here is a Comprehensive
  Rules question.
- **DDR#1004** (Limited RCQ Tournament Report) - the *back half* of this episode
  is policy too (a sealed pack opened with no rare, DFC handling in draft,
  reviewing your picks at competitive rel and the limited procedure violation
  that follows). Its two rules questions are tested; the policy half is logged
  here.

## Reviewed and skipped this wave

- **DDR#1008's actual combo** (Miirym, Sentinel Wyrm + Astral Dragon) - both
  cards' triggers ("create a token that's a copy of it" / "create two tokens
  that are copies of target noncreature permanent") have no entry in
  `machines/effects.py` and no generic parser reaches them, so the combo's own
  loop cannot be built. The replacement-effect multiplication it rests on is
  tested instead, at a size that fits. The episode's other content - whether a
  judge would rule the token count indeterminate, loops and shortcuts, the
  smallest prime above a billion - is judge philosophy with no game state.
- **DDR#1000's remaining exam questions**, each with why:
  - *Rest in Peace vs. Lapse of Certainty* (self-replacement effects apply
    first) - needs Lapse of Certainty's own "put it on top of its owner's
    library instead" self-replacement, which nothing parses; the same point
    recurs in DDR#1006's Gemstone Caverns question.
  - *Leyline of the Void vs. a dies trigger* - already covered:
    `test_judge_dies_triggers.py::test_the_fiend_never_dies_so_it_is_never_in_a_graveyard`
    and `::test_leyline_of_the_void_only_catches_the_opponents_cards`.
  - *Might Makes Right's intervening `if` rechecked on resolution* - already
    covered generically by
    `tests/scenarios/test_triggered_abilities.py::test_an_intervening_if_is_checked_again_on_resolution`
    (CR 603.4, 608.2a); Might Makes Right itself has no scripted effect.
  - *Fireball's casting order* (X announced, then targets, then the cost) -
    blocked by the same gap COVERED.md already logs for DDR#984/#940: X never
    reaches `machines/effects.py`, and there is no divided-damage X spell in
    the pool whose effect would run.
  - *Darkest Hour + Living Terrain*, *Fairy Conclave + Conspiracy* (layer 4/5
    ordering and dependency), *Cytoshape + Nixathid* (linked abilities),
    *Crucible of the Spirit Dragon* (what "a Dragon" means without a
    qualifier), *Reshape + Twincast* (copying a spell) - each needs a
    `LAYER_EFFECTS`/`EFFECTS` registry row or a mechanic the engine lacks
    (copying spells is already logged as absent under DDR#951).
  - *Two-headed giant* (mountainwalk against a team, a team losing to an empty
    library) and the two *commander* questions (color identity, the command
    zone replacement) - variant formats this engine does not model.
  - *Boon Reflection doubling lifelink life gain* - Boon Reflection is not in
    the pool and its "if you would gain life, you gain twice that much" would
    need the life-gain-doubler shape to fire off combat lifelink, which
    `machines/combat.py` does not route through a replaceable event.
  - *Whipgrass Entangler / Deathrite Shaman / Sentinel's Stalwart* (paying an
    attack cost, and when mana can be made for it) - the attack-cost half of
    CR 508.1e-g is not modelled.
- **DDR#1002's pregame questions** other than summoning sickness (Providence +
  Leyline of Hope, two Leylines of Singularity, Gemstone Caverns on one card,
  Chancellor of the Annex vs. Leyline of Lifeforce) - all need the pregame
  procedure and the opening-hand-effect step, which do not exist here; the one
  that does not (the legend rule waiting for a check) is tested.
- **DDR#666's Tempest Efreet question** (a token sacrificed to its own cost
  ceases to exist, so CR 701.12a's exchange cannot be completed and nothing at
  all happens) - the token half is already covered by
  `tests/scenarios/test_tokens.py` (CR 704.5d), and the exchange half needs the
  ante zone the rest of that file is `xfail` for.

## Conflicts between episodes and the codebase

- **DDR#1000 vs. `tests/scenarios/harness.py` and `machines/combat.py`** - the
  episode (recorded 2025-12-31) states, in its Giant Growth blocking question,
  that "there's no more damage assignment orders" after the Foundations combat
  changes: the attacking player simply divides its damage among the blockers
  however they like. The codebase implements ordered assignment -
  `PlayedScenario.block(attacker, *blockers)` documents its blockers as being
  "in damage assignment order", and `machines/combat.py` assigns lethal damage
  down that order. **The codebase stands** for this wave, per the standing
  instruction to favour the existing implementation; no existing test was
  rewritten, and no new test asserts either behaviour. Whoever revisits combat
  should decide this one deliberately rather than inheriting it from here.
- No episode-vs-episode conflicts were found in this slice.
