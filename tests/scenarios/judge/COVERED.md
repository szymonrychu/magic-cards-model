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
