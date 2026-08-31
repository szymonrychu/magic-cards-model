# DDR episodes covered by judge scenario tests - wave E

Wave E worked the ten newest DDR transcripts on disk
(`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/`, DDR#955-#965), read
directly rather than through `knowledge_search`. Merge into `COVERED.md`.

Every card's oracle text was verified with `resolve_cards` in this session, and
every CR number written in the new files was verified with
`knowledge_search(type="rules")` in this session.

| Episode | Ruling | Where |
|---|---|---|
| DDR#965 | a creature card put onto the battlefield tapped and attacking by Ilharg (CR 508.4, 508.4c), returned by "that creature" whether or not it is still one - Ilharg's attack trigger reaches the stack and performs nothing, and Purphoros' devotion-gated "isn't a creature" has no `LAYER_EFFECTS` row | `test_judge_put_onto_the_battlefield_attacking.py` (3 passing + xfail) |
| DDR#964 | CR 602.1a's colon: a life payment before it must be payable (Mana Confluence at 0 life is refused), a life gain after it is only an instruction (Armistice) - Leyline of Punishment's "Players can't gain life" is not modelled | `test_judge_paying_life.py` (3 passing + xfail) |
| DDR#963 | warp's permission to cast from exile comes only from its own delayed trigger (CR 702.185a/b, 601.3), so a warp permanent exiled by Solitude cannot be recast - Syncopate's `{X}` counter-unless-pays clause is unread | `test_judge_warp_from_exile.py` (3 passing + xfail) |
| DDR#961 | CR 603.8's state trigger re-triggers the moment the countered first copy leaves the stack, before Tishana's Tidebinder's second sentence strips the abilities - state triggers are not modelled, and the Calendar's condition misparses at the comma in "1,000" | `test_judge_state_triggers.py` (2 passing + xfail) |
| DDR#960 | CR 603.4's intervening *if* gates the counter *and* the search, one ability - "it has fewer than four +1/+1 counters on it" is a clause `intervening_if_holds` cannot read, so it fails closed with an `InterveningIfNotice` and the ability never triggers at any counter count | `test_judge_intervening_if.py` (3 passing + xfail) |
| DDR#959 | Deflecting Swat may legally target a spell with no targets of its own (CR 115.1, 601.2c, 101.3) - the announcement is legal and the resolution simply does nothing | `test_judge_retargeting.py` (3 passing + 2 xfail) |
| DDR#958 | paying life is losing life (CR 118.3b) exactly as damage is (CR 119.2) - shown through a Bolt and a Mana Confluence activation; Children of Korlis' "life you've lost this turn" has no ledger to read | `test_judge_paying_life.py` (1 passing + xfail) |
| DDR#957 | ending the turn (CR 724.1b/d) exiles the resolving Time Stop but CR 608.2m finishes it anyway, so the spliced Everdream draw happens inside the cleanup step, before CR 514.2 ends Plagiarize - none of the three cards' effects exist | `test_judge_ending_the_turn.py` (3 passing + xfail) |
| DDR#956 | a card exiled face down has no characteristics (CR 406.3a), so its mana value is 0 (CR 202.3a) - `face_up_cards_in_exile` honours CR 406.3's choosability half, but nothing blanks the characteristics | `test_judge_face_down_exile.py` (1 passing + 2 xfail) |
| DDR#955 | one total cost, paid in any order (CR 601.2h, 118.8a): sacrifice Omnath before spending the floating green mana and it is a 5/5 - the additional cost is read and paid, but Omnath has no `LAYER_EFFECTS` row and Momentous Fall's own effect is unread | `test_judge_cost_payment_order.py` (3 passing + xfail) |

## Policy episodes - no rules test possible

(none this wave; all ten episodes were rules episodes)

## Reviewed and skipped this wave

(none - every one of the ten produced a test file)

Two of the episodes' *challenge questions* were left out rather than tested,
and are recorded here so a later wave does not re-derive why:

- **DDR#964's Grove of the Burn-Willows aside.** `resolve_cards(["Grove of the
  Burn-Willows"])` returns `not_found`, so there is no printing to build a test
  from. The same episode's Karplusan Forest and Angel of Jubilation asides make
  the identical CR 602.1a point the Mana Confluence and Armistice tests already
  cover, so nothing is lost.
- **DDR#955's Underworld Breach / Big Score challenge question.** Escape's
  "exile three other cards from your graveyard" plus Big Score's additional
  discard is a second, independent cost-ordering case; Underworld Breach is
  banned in Modern (`resolve_cards` legality) and escape is a keyword this
  engine does not execute, so it would be a third gap stacked on the two the
  DDR#955 xfail already names.

## Conflicts between episodes

None found. No test written this wave contradicts an existing passing test, and
no transcript in this slice restates a ruling an existing test already encodes
differently.

One **CR-number defect in an existing file**, not a conflict and not touched by
this wave (it is another wave's file): `test_judge_countering.py` cites
countering as **CR 701.5a** / **CR 701.5** in two docstrings. Verified this
session with `knowledge_search(type="rules")`: countering is **CR 701.6a** ("To
counter a spell or ability means to cancel it, removing it from the stack. It
doesn't resolve and none of its effects occur. A countered spell is put into
its owner's graveyard."); **CR 701.5** is *Cast*. Left for whoever owns that
file to correct.

## Engine defects this wave found

Recorded here because each is a concrete, reproducible gap rather than a
missing feature in the abstract:

1. **`machines/abilities.py` splits a trigger condition on the first comma**,
   which falls inside a thousand separator. The Millennium Calendar's
   `condition` parses as `"there are 1"` and its effect as `"000 or more time
   counters ..."`. Asserted in `test_judge_state_triggers.py`.
2. **`machines/targeting.py` reads "with a single target" as a second targeting
   requirement.** `targeting_profile(card("Bolt Bend"))` returns two
   requirements, so Bolt Bend demands two targets and cannot legally be cast at
   anything. CR 115.9a makes that phrase a property of the *targeted* spell.
   Asserted in `test_judge_retargeting.py`.
3. **`Game.why_cannot_activate` does not consult a life cost.** Mana Confluence
   at 0 life answers `None`, and the refusal only arrives when `CostPayment.pay`
   raises. CR 118.3 / CR 614.17b would have it answer up front. Noted in
   `test_judge_paying_life.py`'s docstring.
4. **`_COUNTER_UNLESS_PAYS_RE` accepts a literal digit only**, so Syncopate's
   `{X}` never matches and `effect_for("Syncopate", ...)` is None - the same
   "announced X never reaches the code that needs it" family as DDR#984 and
   DDR#940 in `COVERED.md`. Asserted in `test_judge_warp_from_exile.py`.
5. **No per-turn life-loss ledger.** `Game.life_gained_this_turn` exists (a set
   of usernames, for CR 119.9) with no losing counterpart, so "the life you've
   lost this turn" resolves as 0. `test_judge_paying_life.py`.
6. **CR 406.3a is not modelled for exile.** `CardState` blanks characteristics
   only through `face_down_characteristics`, which the morph/manifest path sets;
   a card turned face down in exile keeps its name, types, and mana value.
   `test_judge_face_down_exile.py`.
