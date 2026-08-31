# DDR episodes covered - wave B (merge into COVERED.md)

Ten transcripts read straight off disk from
`/Users/szymonri/Documents/mtg/judgingFTW/transcripts/`, newest first. Every
card's text was re-checked with `resolve_cards` and every CR number below was
looked up with `knowledge_search(type="rules")` in the session that wrote these
tests.

One transcript name did not match a real card: the episode calls the cost
reducer "Grand Gran" / "Grant Grant", which `resolve_cards` does not know. The
real card is **Gran-Gran** (found via `card_search`), and its oracle text
matches what the episode describes exactly, so it was used rather than skipped.

| Episode | Ruling | Where |
|---|---|---|
| DDR#998 | CR 601.2f settles the total cost before CR 601.2g's mana abilities and CR 601.2h's payment, so an untap-for-mana trick can never reach back and lower it | `test_judge_costs.py` (passing half on a cost increaser that dies mid-payment + xfail on Umbral Mantle's granted `{3}, {Q}` ability, which has no reader at all) |
| DDR#249 | CR 111.4 names an unnamed token after its subtypes plus "Token", so Urza's Factory makes an "Assembly-Worker Token" that a name-matching pump misses | `test_judge_names.py` (passing half on the token's name + xfail on Echoing Courage's unscripted pump and on Mishra's Factory's unexecuted animation) |
| DDR#996 | CR 601.2a moves the spell out of the graveyard before CR 601.2f counts it, so flashing back one of exactly three Lessons loses Gran-Gran's discount | `test_judge_costs.py` (xfail: neither Iroh's CR 400.7g flashback grant nor Gran-Gran's conditional reduction reaches the cost) |
| DDR#995 | a creature targeted at CR 601.2c can be sacrificed for mana at CR 601.2g, and CR 608.2b only removes the spell if *every* target is illegal | `test_judge_targeting.py` (passing half via `Game.fizzled` + xfail on Run Away Together's unscripted bounce and on its unread "different players" restriction) |
| DDR#994 | Blood Moon's layer 4 effect is dependent on Toph's (CR 613.8, 613.8b), so it waits, and the artifacts end up artifact land Mountains | `test_judge_layers.py` (passing control on Blood Moon alone + xfail on Toph's missing `LAYER_EFFECTS` row) |
| DDR#993 | CR 603.4 reads the intervening *if* the moment the ability would trigger, so Phoenix Fleet Airship never triggers at all and CR 603.3b's ordering is moot | `test_judge_triggers.py` (passing half, with the `InterveningIfNotice` asserted so it cannot silently pass for the wrong reason, + two xfails) |
| How Does Airbend Work? (2025-12-05) | CR 701.65a's airbend exiles the object and gives its owner a {2} cast; CR 111.7/704.5d kills an airbended token first | `test_judge_bending.py` (xfail: airbend has no implementation anywhere) |
| DDR#990 | CR 605.1b keeps Caged Sun's trigger a mana ability whatever it triggers from, so CR 605.4a denies anyone priority and CR 104.4b draws the game | `test_judge_mana_abilities.py` (xfail: Caged Sun is entirely unparsed, and `Game.drawn` covers only CR 104.4a) |
| DDR#989 | CR 603.7e fixes the earthbend return's controller as the earthbender, so the land comes back to them even after someone else took and sacrificed it | `test_judge_bending.py` (passing half asserting both delayed triggers' recorded controller + xfail on the Threaten half) |
| DDR#988 | firebending is not a mana ability (CR 605.1b), and CR 608.2h reads its self-defined X as the ability resolves, so pumping in response gets more mana | `test_judge_mana_abilities.py` (xfail: the CR 702.189a keyword line is never expanded into a trigger) |

## Policy episodes - no rules test possible

(none this wave - all ten transcripts carried a rules ruling)

## Reviewed and skipped this wave

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

## Conflicts

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

## Cards added to the pool this wave

`Umbral Mantle`, `Echoing Courage`, `Assembly-Worker`, `Mishra's Factory`,
`Urza's Factory`, `Iroh, Grand Lotus`, `Gran-Gran`, `Run Away Together`,
`Fire Navy Trebuchet`, `Phoenix Fleet Airship`, `Toph, the First Metalbender`,
`Caged Sun`, `Firebending Student`, `Threaten`, `Combustion Technique` - all via
`scripts/add_card.py`, all real Scryfall printings.

## CR numbers verified this wave

104.4b, 107.6, 111.4, 111.7, 113.4, 113.7a, 118.2, 301.5b, 400.7g, 601.2a, 601.2c, 601.2f, 601.2g, 601.2h, 602.2,
602.2b, 602.4, 602.5a, 603.3b, 603.4, 603.7a, 603.7e, 605.1a, 605.1b, 605.3a,
605.3b, 605.4a, 605.5a, 608.2a, 608.2b, 608.2h, 613.1b, 613.1d, 613.3, 613.7,
613.8, 613.8b, 701.21a, 701.65a, 701.66a, 701.67a, 702.6a, 702.108a, 702.189a,
704.5d.
