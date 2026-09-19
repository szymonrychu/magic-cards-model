# DDR episodes covered by judge scenario tests

The ledger for the DDR (Daily Dose of Rulings) conversion loop: every episode
whose ruling has been turned into a test, so successive waves neither collide
nor redo work.

**Order of work is highest episode number first.** `knowledge_search` is
semantic only - it has no numeric filter, and querying `"DDR#1011"` returns
unrelated episodes - so an exact 1012->1 walk is not possible. A wave instead
harvests episode titles across many varied rules queries, then takes the
highest-numbered ones not already listed here.

**A newer episode outranks an older one.** These transcripts span years and a
later episode sometimes restates or corrects an earlier explanation. Where two
episodes disagree, the higher number wins, and an existing test written from
the higher-numbered episode is **not** to be rewritten to match an older one.
If an older episode contradicts a test already here, record the conflict in the
Conflicts section rather than changing the test.

**Not every episode is testable.** Many are tournament policy rather than rules
- investigations, deck checks, playing the wrong opponent, appealing a ruling,
rolling a die. Those have no game state to build and are logged as `policy`
rather than skipped silently.

| Episode | Ruling | Where |
|---|---|---|
| DDR#944 | Transcendent Dragon's whole "counter, then exile it instead and recast" line is one trigger paragraph (CR 603.1), so its replacement-shaped sentence is never even offered to the parser, and the ability has no scripted effect either | `test_judge_countering.py` (passing half + xfail) |
| DDR#901 | Stridehangar Automaton's "one or more artifact tokens would be created ... instead" parses into a real `IF_WOULD_INSTEAD`, on a card with no row in `replacements_of` | `test_judge_replacement_effects.py` (passing half + xfail) |
| DDR#886 | Captain Howler's "whenever you discard one or more cards" has no `TriggerEvent` shape at all, and Mind Rot's own discard clause has no scripted effect either | `test_judge_triggers.py` (passing halves + xfail) |
| DDR#833 | an opponent's Leyline of the Void reaches a player's own self-mill, because "opponent's graveyard" is judged from the Leyline's controller | `test_judge_replacement_effects.py` (passing half + xfail on Nashi's own unscripted trigger) |
| DDR#951 | copying a spell (CR 707.2/707.10) is not implemented anywhere in the engine - Frontline Heroism's "then copy that spell" clause is fail-closed to no effect at all | `test_judge_copying.py` (xfail) |
| DDR#943 | lifelink gains life straight off real combat damage, independent of a *different*, unregistered replacement effect (The Darkness Crystal) watching the same event | `test_judge_replacement_effects.py` (passing half + xfail half) |
| DDR#939 | a permanent's own "all damage ... is dealt to this creature instead" redirection parses as `UNPARSED`, not `IF_WOULD_INSTEAD`, and has no row in the replacement registry either way | `test_judge_replacement_effects.py` (passing half + xfail half) |
| DDR#830 | two damage replacements that *do* parse into real `ReplacementKind` values (one `IF_WOULD_INSTEAD`, one `PREVENT_IF_WOULD`) still do nothing, because parsing and the hand-written `replacements_of` registry are different things | `test_judge_replacement_effects.py` (passing half + xfail half) |
| DDR#1016 | Grist's own creature-type text only functions off the battlefield, so Dress Down has nothing to strip | `test_judge_layers.py` |
| DDR#997 | an ability that says "pay its mana cost" sees the real cost, not the card's own alternative cost | `test_judge_costs.py` (xfail) |
| DDR#991 | Waterbend lets untapped artifacts/creatures each pay for {1} instead of mana | `test_judge_costs.py` (xfail) |
| DDR#982 | two static abilities granting the same keyword make two independent instances of it | `test_judge_layers.py` (xfail) |
| DDR#978 | a generic "spells cost {1} more" static ability taxes every spell, symbol-less ones included | `test_judge_costs.py` (was xfail through wave 2; a concurrent engine wave landed cost increases in wave 3, so it now passes as an ordinary test) |
| DDR#932 | a death-replacer worded as a "would die" trigger | `test_judge_dies_triggers.py` |
| DDR#918 | the same replacement, aimed by controller rather than owner | `test_judge_dies_triggers.py` |
| DDR#857 | killing the blocker before damage does not unblock the attacker | `test_judge_combat_damage.py` |
| DDR#853 | two shields, one destruction, one shield spent | `test_judge_replacement_effects.py` |
| DDR#814 | the target changed zones, so the spell is countered | `test_judge_targeting.py` |
| DDR#775 | the legend rule is per controller, not per game | `test_judge_state_based_actions.py` |
| DDR#707 | an ability is its own object once on the stack | `test_judge_replacement_effects.py` |
| DDR#699 | three damage on a 4/4 means only one more is lethal | `test_judge_combat_damage.py` |
| DDR#694 | one illegal target does not counter the spell | `test_judge_targeting.py` |
| DDR#662 | the legend rule applies to any legendary permanent | `test_judge_state_based_actions.py` |
| DDR#497 | marked damage stays, rechecked against the new toughness | `test_judge_layers.py` |
| DDR#410 | prevention removes the damage event, not just its result | `test_judge_combat_damage.py` |
| DDR#403 | destruction is replaced, so the creature never leaves | `test_judge_replacement_effects.py` |
| DDR#366 | Humility's 7b lands on top with the latest timestamp | `test_judge_layers.py` |
| DDR#319 | "in addition to" is not a land-type replacement | `test_judge_layers.py` |
| DDR#193 | the zone change is replaced before it happens | `test_judge_dies_triggers.py` |
| DDR#71 | the target stays in its zone but stops being legal | `test_judge_targeting.py` |
| DDR#66 | Rest in Peace cannot replace its own death | `test_judge_dies_triggers.py` |
| DDR#20 | lethal damage is checked against current toughness | `test_judge_state_based_actions.py` |
| DDR#14 | competing replacements for a single zone change | `test_judge_replacement_effects.py` |
| DDR#3 | a static ability, not a trigger; the SBA does the work | `test_judge_state_based_actions.py` |
| DDR#1009 | "Any number of target spells" is CR 107.1c's zero-or-more, a Trap aimed at one spell has exactly one target, a spell may not target itself (CR 115.5), the alternative cost leaves the mana cost and mana value alone (CR 118.9c), and the conditional sentence-form alternative cost is read and paid. Not modelled: exiling a spell off the stack | `test_judge_mindbreak_trap.py` (7 passing + 1 xfail) |
| DDR#1008 | Each Parallel Lives is its own replacement effect (CR 616.1) with one opportunity each (CR 614.5), so N of them multiply the token count by 2^N - the mechanism behind the episode's 2^5 = 32 | `test_judge_token_doublers.py` (5 passing) |
| DDR#666 | Ante (CR 407) is not modelled: `Zone` is CR 400.1's seven zones plus a sideboard, with no ante zone, so nothing can be anted and Jeweled Bird's ability is unscripted | `test_judge_ante.py` (1 passing + 2 xfail) |
| DDR#1007 | "Hexproof from [quality]" (CR 702.11d) and CR 702.11f's shorthand are **now modelled**: `Casting._hexproof_refusal` reads the permanent's own ability text instead of Scryfall's `keywords` field, which carries a bare "Hexproof" alongside "Hexproof from" and used to give Nevinyrral full hexproof (CR 702.11b), refusing spells the printed card allows. `machines/abilities` still leaves the printed line an `UnparsedAbility` | `test_judge_hexproof_from.py` (3 passing), `scenarios/test_hexproof.py` |
| DDR#1006 | CR 106.7's "could produce" is unmodelled in both directions: Reflecting Pool parses to *no* mana ability at all, and Exotic Orchard parses to an unconditional any-colour one that ignores what the opponent's lands could make. `models/mana.Color` is CR 106.1b's six types in one enum, so the color/type distinction the episode opens with cannot be represented | `test_judge_mana_could_produce.py` (2 passing + 2 xfail) |
| DDR#1004 | A trigger caused by *paying an activation cost* (CR 602.1a, 602.2a-b) goes on the stack above the ability it paid for (CR 603.3) and resolves first (CR 608.1) - Blood Artist's drain lands before Vampiric Rites' draw | `test_judge_cost_payment_triggers.py` (4 passing) |
| DDR#1003 | A keyword *granted* to a spell by another permanent's static ability (Ashling's "gain evoke {4} as you cast them") is read at announcement (CR 610.5) and the Hound is cast for {4}; the *trigger* half of evoke (CR 702.74a) still does not reach a granted keyword, so CR 400.7b/611.3d's survival of the granter's death cannot be shown | `test_judge_granted_evoke.py` (2 passing + 1 xfail) |
| DDR#1002 | A creature that began the game on the battlefield attacks on turn one with no haste (CR 508.1a, 302.6, 702.10b), one that arrived during the turn may not, and the legend rule waits for the first state-based-action check (CR 704.3, 704.5j). The pregame procedure itself (CR 103.1-103.3) is not modelled | `test_judge_starting_the_game.py` (3 passing + 1 xfail) |
| DDR#1000 | Both players losing at one state-based-action check is a draw (CR 104.4a, 704.5a, 704.5b, 121.4); a spell with one of two targets now illegal still resolves (CR 608.2b) | `test_judge_practice_exam_rules.py` (4 passing) |
| DDR#999 | "Whenever one or more cards are put into a library from anywhere" has no `TriggerEvent` shape at all, so Wan Shi Tong never triggers - neither on a Brainstorm (which should) nor on a scry (which should not, CR 701.22a) | `test_judge_put_into_library.py` (2 passing + 1 xfail) |
| DDR#998 | CR 601.2f settles the total cost before CR 601.2g's mana abilities and CR 601.2h's payment, so an untap-for-mana trick can never reach back and lower it | `test_judge_costs.py` (passing half on a cost increaser that dies mid-payment + xfail on Umbral Mantle's granted `{3}, {Q}` ability, which has no reader at all) |
| DDR#249 | CR 111.4 names an unnamed token after its subtypes plus "Token", so Urza's Factory makes an "Assembly-Worker Token" that a name-matching pump misses | `test_judge_names.py` (passing half on the token's name + xfail on Echoing Courage's unscripted pump and on Mishra's Factory's unexecuted animation) |
| DDR#996 | CR 601.2a moves the spell out of the graveyard before CR 601.2f counts it, so flashing back one of exactly three Lessons loses Gran-Gran's discount | `test_judge_costs.py` (passing: Iroh's CR 400.7g flashback grant is read by `Casting.granted_cast_options`, and `Casting` now makes CR 601.2a's move to the stack as the proposal begins, so the flashed-back Lesson is out of the graveyard before CR 601.2f counts it) |
| DDR#995 | a creature targeted at CR 601.2c can be sacrificed for mana at CR 601.2g, and CR 608.2b only removes the spell if *every* target is illegal | `test_judge_targeting.py` (passing half via `Game.fizzled` + xfail on Run Away Together's unscripted bounce and on its unread "different players" restriction) |
| DDR#994 | Blood Moon's layer 4 effect is dependent on Toph's (CR 613.8, 613.8b), so it waits, and the artifacts end up artifact land Mountains | `test_judge_layers.py` (passing control on Blood Moon alone + xfail on Toph's missing `LAYER_EFFECTS` row) |
| DDR#993 | CR 603.4 reads the intervening *if* the moment the ability would trigger, so Phoenix Fleet Airship never triggers at all and CR 603.3b's ordering is moot | `test_judge_triggers.py` (passing half, with the `InterveningIfNotice` asserted so it cannot silently pass for the wrong reason, + two xfails) |
| DDR#990 | CR 605.1b keeps Caged Sun's trigger a mana ability whatever it triggers from, so CR 605.4a denies anyone priority and CR 104.4b draws the game | `test_judge_mana_abilities.py` (xfail: Caged Sun is entirely unparsed, and `Game.drawn` covers only CR 104.4a) |
| DDR#989 | CR 603.7e fixes the earthbend return's controller as the earthbender, so the land comes back to them even after someone else took and sacrificed it | `test_judge_bending.py` (passing half asserting both delayed triggers' recorded controller + xfail on the Threaten half) |
| DDR#988 | firebending is not a mana ability (CR 605.1b), and CR 608.2h reads its self-defined X as the ability resolves, so pumping in response gets more mana | `test_judge_mana_abilities.py` (xfail: the CR 702.189a keyword line is never expanded into a trigger) |
| DDR#986 | Superior Spider-Man entering *as a copy* of a graveyard card is a CR 614.1c replacement effect with no `replacements_of` row, so no copy, no acquired ETB trigger, and nothing exiled | `test_judge_copying.py` (two passing halves + xfail) |
| DDR#983 | two attack triggers under one controller do both reach the stack, but `Game.put_triggers_on_stack` never offers CR 603.3b's ordering choice, and neither card's CR 118.12 "you may ... if you do" clause has a scripted effect | `test_judge_triggers.py` (three passing halves + xfail) |
| DDR#981 | Panharmonicon has no `LAYER_EFFECTS` row and no trigger-multiplying machinery, and Lagrella's enters trigger has no scripted effect - the engine reaches the episode's *counter* answer for the wrong reason, and misses its *exile* answer | `test_judge_triggers.py` (two passing halves + xfail) |
| DDR#32 | Purelace's "target spell or permanent" really can target a spell on the stack, but `effect_for('Purelace')` is `None` and Clone's enter-as-a-copy has no replacement row, so CR 613.3's "CDAs first within layers 2-6" never gets exercised | `test_judge_copying.py` (passing half + xfail) |
| DDR#980 | a token copy of an animated land, and its copy-effect-granted ETB fight - `effect_for` is `None` for both Jolrael and Aggressive Biomancy | `test_judge_copying.py` (passing half + xfail) |
| DDR#979 | suspend's "your upkeep"/"you may play it" belong to the card's **owner** (CR 109.5, CR 108.3), never to whoever performed the exile - **fixed**: `finish_suspend` grants the CR 702.62a free cast to `CardState.owner`, falling back to `ExileAnnotation.owner` (the exiling player) only when nothing recorded an owner | `test_judge_suspend.py` (4 passing) |
| DDR#977 | a *targeted* copy ability is removed from the stack when the spell it targets is countered in response (CR 608.2b/608.3b) - **the engine already gets this right**; the untargeted contrast case (Flamehold Grappler copying off last known information) does not | `test_judge_copying.py` (passing + xfail) |
| DDR#976 | APNAP (CR 101.4): every state-based action is one simultaneous event (CR 704.3), so two players' extra legends are binned by the same check; and CR 603.3b's APNAP trigger ordering starts at the *active* player, not the first seat | `test_judge_apnap.py` (4 passing + xfail on the legend rule never asking its controller which copy to keep) |
| DDR#975 | a draw replacement really applies (`ReplacementKind.DRAW`), but CR 614.5's "each effect gets one opportunity" second copy does not, and neither of the episode's own cards compiles to a replacement at all | `test_judge_draw_replacements.py` (1 passing + 2 xfail) |
| DDR#974 | exchanging life totals with a player who can't gain life: CR 119.7 stops the gain and CR 701.12a/701.12g stop the whole exchange - nothing is modelled, and Screaming Nemesis's "whenever this creature is dealt damage" has no `TriggerEvent` shape either | `test_judge_life_exchange.py` (2 passing + 2 xfail) |
| DDR#973 | mana spent paying a ward trigger (CR 702.21a) is not mana spent to cast the spell (CR 601.2h), so Prismatic Ending's Converge does not count it - the engine gets this right | `test_judge_ward_and_mana_spent.py` (4 passing) |
| DDR#972 | suspending is a special action (CR 116.2f, CR 405.6d) with nothing on the stack to respond to, and a resolved Orim's Chant still stops it through CR 702.62c's "could begin to cast" gate | `test_judge_suspend_special_action.py` (4 passing) |
| DDR#970 | Gollum's "Return this card from your graveyard to your hand" ability functions only in a graveyard (CR 113.6m), so it cannot be activated on the battlefield by sacrificing Gollum to itself | `test_judge_ability_zones.py` (3 passing + xfail on `Game.activate_ability` not enforcing the zone) |
| DDR#969 | Breeding Pool's "as this land enters, you may pay 2 life" (CR 614.1c, CR 614.12a) works both ways; Lakeside Shack's conditional "enters tapped unless a player has 13 or less life" is not modelled, so CR 616.1's single-object scope has nothing to demonstrate | `test_judge_entering_replacements.py` (2 passing + 2 xfail) |
| DDR#968 | drawing from an empty library loses at the next check (CR 121.4, CR 704.5b), an unpayable cast is reversed with its payments (CR 733.1, CR 733.2), and CR 601.2a's "first moves that card ... to the stack" is now how announcement works | `test_judge_illegal_play_win.py` (4 passing); the IPG half is `policy`, below |
| DDR#967 | the cleanup discard to maximum hand size (CR 703.4n, CR 514.1) happens in a step where no player receives priority (CR 514.3), so flash does not help; mayhem (CR 702.187b) is not modelled | `test_judge_cleanup_discard.py` (3 passing + xfail) |
| DDR#31 | modal double-faced cards *can* transform now (CR 712.3) and a single-faced permanent simply does not (CR 701.27c); a back face that is an instant should also do nothing (CR 701.27d) and does not | `test_judge_transform.py` (3 passing + 2 xfail) |
| DDR#966 | Blood Moon reaches only nonbasic *lands*, so a Hydro-Man that is still a creature is untouched, and a nonbasic land loses its abilities in layer 4 along with its subtypes | `test_judge_blood_moon_layers.py` (4 passing + xfail on Hydro-Man's own type-changing trigger and the CR 613.8a dependency it would create) |
| DDR#965 | a creature card put onto the battlefield tapped and attacking by Ilharg (CR 508.4, 508.4c), which deals its combat damage (the step it needs exists, CR 508.8) and is returned by "that creature" whether or not it is still one - Purphoros' devotion-gated "isn't a creature" has no `LAYER_EFFECTS` row | `test_judge_put_onto_the_battlefield_attacking.py` (9 passing) |
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

(none recorded yet; add them here rather than dropping them silently)

## Reviewed and skipped this wave

Harvested but not turned into tests - recorded so a later wave does not spend
the same searches re-discovering why.

- **DDR#987** (Wight + Mortarpod) - the transcript's "Wight" does not match
  `resolve_cards("Reclusive Wight")`'s actual oracle text (no dies trigger at
  all, only an upkeep sacrifice), and the "White's life drain ability" clip
  attached to `Defiler of Faith`/`Horned Turtle` matches neither of those
  cards' real text either. Bad transcription/tagging on this one specifically -
  skipped rather than guessing which real card was meant. The general point it
  argues (a leaves-the-battlefield trigger fires off last known information,
  CR 603.10a) is already covered by DDR#932/#918/#193 in this file anyway.
- **DDR#1015** (MagicCon Amsterdam Tournament Report) and **DDR#1012** (SCG
  Cincinnati Tournament Report) - tournament-report episodes bundle several
  short rulings, and the `knowledge_search` excerpts for both (Painter's
  Servant + Kozilek's Command; Valley Floodcaller + a changeling creature) are
  cut at the ~200-character truncation before the actual ruling lands. Not
  enough to build a scenario without guessing what the judges actually
  concluded - left for a future wave with a more targeted query, rather than
  writing a test from a paraphrase that might be wrong.
- **DDR#1015** and **DDR#1012** again, wave 2: two more targeted queries
  ("Painter's Servant Kozilek's Command color ruling", "Valley Floodcaller
  changeling ruling") still only surface excerpts that cut off mid-sentence
  before the actual conclusion ("...It on...", "...becomes a new creature with
  Phlage's characteristics. Then, during the control exchange, the Stormdrake's
  contro..." - that one is DDR#788, not even the right episode). DDR#1015 did
  not surface a single new chunk this wave. Still left for a future wave.
- **DDR#984** (Angel of Suffering vs. Unpreventable Damage / Divine Deflection
  vs. Banefire) - Banefire's "Banefire deals X damage to any target. If X is 5
  or more ... the damage can't be prevented" cannot be built as a scenario at
  all: `Game.resolve_top` calls `effect_for(spell.card.name, spell.card.oracle_text)`
  with the card's raw printed text, never substituting the caster's announced X
  (`machines/casting.py`'s `x_value` never reaches `effects.py`), so an X spell's
  damage amount is not computed by anything generic. Swapping in a fixed-damage
  "can't be prevented" printing (Combust) does not rescue the episode's actual
  point either: `effect_for('Combust', ...)` returns `None` outright, because
  `_parse_targeted_clauses` fails closed the moment it hits the second sentence
  ("The damage can't be prevented") and throws away the whole spell, which
  would only demonstrate the *already-documented* multi-clause fail-closed
  pattern (see DDR#403/#853 above), not this episode's CR 615.12 point about a
  prevention shield being refused. Left rather than writing a scenario against
  a card the episode is not actually about.
- **DDR#971** (First Strike + Double Strike) - the episode's actual point per
  transcript ("a creature equipped with an Aura or aura granting First Strike is
  replaced with another effect, it still only gains First Strike once") is about
  *swapping* a keyword-granting Equipment/Aura between permanents without
  double-granting, which needs working Equipment/Aura attachment tracking this
  model does not have (the same gap the umbra armor xfail below already
  documents). A test built any other way would just restate
  `test_double_strike_deals_damage_in_both_steps` already in
  `tests/scenarios/test_first_strike.py`.
- **DDR#962** (Mouth of the Storm vs. Kardur, Doomscourge) - the transcript
  excerpt talks about "Battle Frenzy's granted prowess", but neither Mouth of
  the Storm, Kardur, nor Battle Frenzy's real oracle text (`resolve_cards`)
  mentions prowess at all - the same kind of transcript/card-tag mismatch wave 1
  hit on DDR#987. Skipped rather than guessing which card the judges actually
  meant.
- **DDR#942** (Hex vs. 5 Creatures) - the excerpt's point ("a spell can target
  the same creature multiple times if the word 'target' appears multiple
  times") does not match either card the title names: Kaervek's Hex has a
  single target-less "each ... creature" effect, and Incremental Blight's three
  clauses are "target creature", "**another** target creature", "a **third**
  target creature" - explicitly forcing three *different* creatures, the
  opposite of the transcript's claim. Left rather than building a scenario
  against a card whose real text contradicts the paraphrase.
- **DDR#801** (Nadu, Winged Wisdom vs. Dress Down) - straightforward on its
  face (Dress Down's layer 6 removal vs. an ability Nadu grants to other
  creatures), but Nadu has no entry in `machines/layers.LAYER_EFFECTS`, so a
  `compute_board` test would only be proving the registry gap already
  documented by DDR#982 above, not this episode's actual timestamp-ordering
  point. Left for whoever adds a Nadu entry to the registry.

### Wave 3

- **DDR#1010** (Abigale, Eloquent First Year vs. Agatha's Soul Cauldron) - the
  transcript's own point is a timestamp-ordering question between a resolving
  trigger's continuous effect and a static ability's, plus a side note about
  Equipment re-timestamping when it reattaches. Neither Abigale (a
  cost-reduction "loses all abilities, gains three keyword counters" ETB) nor
  Agatha's Soul Cauldron's "creatures with +1/+1 counters have all activated
  abilities of exiled creature cards" has a `LAYER_EFFECTS` entry, so a real
  test would only restate the DDR#982/#801 registry gap already logged above,
  not this episode's timestamp point. Equipment attachment tracking is the
  same gap DDR#971 (wave 2) was left for. Left for a future wave once one of
  the two registries is fed.
- **DDR#954** (Forgetting to Apply the Legend Rule) - mostly a tournament-policy
  episode about a judge's partial-fix options once a legend-rule violation is
  caught late; the one rules nugget (protection from a card type makes an
  Equipment's own targeted equip ability illegal) is real and the engine's
  `protection_refusal` (CR 702.16b) already covers *any* targeted spell or
  ability generically. Left this wave for time rather than depth - a future
  wave building a real equip-ability scenario against it would be the strong
  version of this test, and the tournament-policy half stays a `policy` entry
  regardless.
- **DDR#940** (March of Otherworldly Light vs. Access Denied) - the episode's
  point is that a countered X spell's mana value is read off it as it last
  existed on the stack (CR 202.3e, last known information), and turns out to
  be untestable for a reason distinct from the DDR#984 gap: March of
  Otherworldly Light's own target restriction is "mana value X or less", and
  `Casting.targeting` only ever reads `self.x_value` through the *modal* path
  (`choose_modes`) - a non-modal X spell like March never gets `x_value`
  threaded into its own targeting profile at all, so `choose_targets` raises
  `ValueError` before a target can even be chosen, let alone before Access
  Denied (whose own effect is also `None` - confirmed with
  `effect_for('Access Denied', ...)`) gets a chance to counter it. Same root
  cause DDR#984 already flagged (X never reaching something that needs it),
  a different code path (targeting instead of `effects.py`) - logged here
  rather than duplicated as a full episode.
- **DDR#925** (Ocelot Pride vs. Surveil Land) - a missed-trigger-window
  question, which is tournament policy (whether a forgotten trigger can still
  be put on the stack) rather than a rules fact the engine models at all - no
  scenario to build. `policy`.
- **DDR#920** (Dragon Cultist + Planeswalker Commander) - the ruling turns on
  an animated commander losing its planeswalker card type mid-game, which
  needs the Commander zone/format machinery (the commander's continued status
  as a commander while off the battlefield, replacement casting from the
  command zone) that this engine does not model at all - not a gap any single
  registry row would close. Left for a future wave.

## Conflicts between episodes

(none recorded yet; a newer episode always wins, and the older one is logged
here with what it claimed and which test stands)


---

## The 2026-08-31 wave: the transcripts themselves

Earlier waves had to harvest episodes through `knowledge_search`, which is
semantic only and cannot walk episode numbers in order - the note at the top
of this file explains why an exact 1012->1 walk was impossible.

**That constraint is gone.** The raw transcripts are on disk at
`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/`, one file per
episode, named `<date>_<video id>_<title>.en.txt`. Read them directly and
walk them newest-first; do not go back to harvesting by search.

Five waves covered all 63 files present. The per-wave detail below is kept
verbatim - the skips and their named blockers are the useful part, since a
later wave that feeds one of the empty registries can revisit exactly those.

### Wave A (2026-08-31 transcript pass)

#### Policy episodes - no rules test possible

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

#### Reviewed and skipped this wave

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
  - *Boon Reflection doubling lifelink life gain* - Boon Reflection's "if you
    would gain life, you gain twice that much" compiles (`_compile_life_gain_doubler`),
    but firing it off combat lifelink needs combat to raise the event, which
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

#### Conflicts between episodes and the codebase

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

### Wave B (2026-08-31 transcript pass)

#### Policy episodes - no rules test possible

(none this wave - all ten transcripts carried a rules ruling)

#### Reviewed and skipped this wave

(none skipped - every one of the ten produced at least one test)

Two things came close to a skip and did not need one:

- **DDR#996's "Grand Gran"** - the spoken name matches no card. Resolved to
  **Gran-Gran** by `card_search(oracle_text="Lesson cards in your graveyard")`,
  whose real text ("Noncreature spells you cast cost {1} less to cast as long
  as there are three or more Lesson cards in your graveyard") is exactly what
  the episode describes. Not a guess.
- **DDR#995's Eldrazi Spawn token** - not in the pool and not creatable by
  anything in it. Substituted **Skirk Prospector** ("Sacrifice a Goblin: Add
  {R}"), which is the same shape the ruling turns on: a mana ability whose cost
  sacrifices a creature. Noted in the test's own docstring.

#### Conflicts

- **DDR#993 vs. the engine's fail-closed intervening *if***: the episode's
  conclusion (Phoenix Fleet Airship does not trigger) is what the engine
  produces, but not for the episode's reason. `machines/triggers.
  intervening_if_holds` does not read "you sacrificed a permanent this turn" at
  all and refuses to trigger on any unreadable clause, recording an
  `InterveningIfNotice`. **The existing behaviour stands** - fail-closed is the
  deliberate policy documented in that function - and the passing test asserts
  the notice explicitly so it cannot survive unchanged once the clause is
  really implemented. The companion xfail
  (`test_the_airship_does_trigger_once_a_permanent_really_was_sacrificed`) is
  the case that would break.
- No transcript in this slice contradicted an existing passing test, so nothing
  was rewritten.

#### Cards added to the pool this wave

`Umbral Mantle`, `Echoing Courage`, `Assembly-Worker`, `Mishra's Factory`,
`Urza's Factory`, `Iroh, Grand Lotus`, `Gran-Gran`, `Run Away Together`,
`Fire Navy Trebuchet`, `Phoenix Fleet Airship`, `Toph, the First Metalbender`,
`Caged Sun`, `Firebending Student`, `Threaten`, `Combustion Technique` - all via
`scripts/add_card.py`, all real Scryfall printings.

#### CR numbers verified this wave

104.4b, 107.6, 111.4, 111.7, 113.4, 113.7a, 118.2, 301.5b, 400.7g, 601.2a, 601.2c, 601.2f, 601.2g, 601.2h, 602.2,
602.2b, 602.4, 602.5a, 603.3b, 603.4, 603.7a, 603.7e, 605.1a, 605.1b, 605.3a,
605.3b, 605.4a, 605.5a, 608.2a, 608.2b, 608.2h, 613.1b, 613.1d, 613.3, 613.7,
613.8, 613.8b, 701.21a, 701.65a, 701.66a, 701.67a, 702.6a, 702.108a, 702.189a,
704.5d.

### Wave C (2026-08-31 transcript pass)

#### Policy episodes - no rules test possible

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

#### Reviewed and skipped this wave

(none - all ten episodes in the slice produced a test or a policy entry)

#### Conflicts between episodes

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

### Wave D (2026-08-31 transcript pass)

#### Policy episodes - no rules test possible

- **DDR#968** (Winning the Game with an Illegal Play) - the episode's actual
  question is an IPG one: is starting a game action you know you cannot finish
  cheating, and what is the infraction and fix. Its answer is that the IPG's
  definition of cheating requires a broken rule and no rule was broken, so
  nothing is done. There is no game state that can hold "was this an
  infraction". The *rules* chain the setup rides on is tested (see the table);
  the policy conclusion is recorded here.
- **DDR#973** (Prismatic Ending vs. Ward) - roughly half the episode is policy:
  regular-REL take-backs, whether the ward trigger was missed, the game-rule
  violation warning to both players, and when a judge should intervene at all.
  None of that is game state. The rules half is a full passing test file.

#### Reviewed and skipped this wave

(nothing was skipped; every episode in the slice produced a test file)

#### Conflicts between episodes

- **DDR#31 vs. its own earlier version.** The episode is an explicit re-shoot
  of a much older DDR because the rules changed: modal double-faced cards used
  to be unable to transform, and since the Spider-Man set they can (CR 712.3,
  verified this session). Anything in `COVERED.md` written from the older
  ruling is superseded. No existing test in this repo asserted the old
  behaviour, so nothing was rewritten.
- **DDR#973's card name.** The transcript says "Lava Spike Boots"; no such card
  exists. `resolve_cards` and `card_search` identify the real printing as
  **Lavaspur Boots** ("Equipped creature gets +1/+0 and has haste and ward
  {1}"). The test does not use it: this engine reads ward off the printing and
  models no Equipment attachment, so the board uses **Gavony Dawnguard**, a
  real printing with `Ward {1}` and the mana value 3 the episode specifies.
  Nothing in the ruling depends on where the ward came from.

#### Engine defects this wave surfaced

Recorded here because each is a live `xfail` with a named cause, not a vague
gap:

1. `Game.activate_ability` ignores `ActivatedAbility.zone`, so a graveyard-only
   ability can be activated from the battlefield. `machines/keywords.
   off_battlefield_activation` enforces CR 113.6m correctly; the two paths
   disagree. (DDR#970)
2. `CardState.transform` turns a permanent into a back face that is an Instant,
   which CR 701.27d / CR 712.10 say must do nothing. (DDR#31)
3. ~~`Casting.cast` does not move the card to the stack at CR 601.2a's
   announcement; it stays in its origin zone until `put_on_stack`.~~ **Fixed:**
   `Casting.model_post_init` makes the move as the proposal begins, and
   `Casting.cancel` (CR 601.6, CR 733.1) is what puts the card back. (DDR#968)
4. Only one replacement effect is applied per draw, so CR 614.5's "each effect
   gets one opportunity" is not honoured for a second identical permanent.
   (DDR#975)
5. Lakeside Shack's "enters tapped unless a player has 13 or less life"
   compiles to no replacement effect. (DDR#969)
6. "Whenever this creature is dealt damage" has no `TriggerEvent`, so Screaming
   Nemesis never triggers. (DDR#974)
7. The legend rule (CR 704.5j) never asks its controller which copy to keep, so
   CR 101.4's APNAP ordering of that choice is unobservable. (DDR#976)
8. Mayhem (CR 702.187) parses as a keyword and grants nothing. (DDR#967)

### Wave E (2026-08-31 transcript pass)

#### Policy episodes - no rules test possible

(none this wave; all ten episodes were rules episodes)

#### Reviewed and skipped this wave

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

#### Conflicts between episodes

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

#### Engine defects this wave found

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
