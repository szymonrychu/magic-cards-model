# Effect gaps: Modern storm

The deck: **pilot IrIWANG, 2026-08-29, source deck `videre-58655658`**, archetype
`storm`. Decklist at `magic-cards-model-api/decks/storm.txt`. Three separate
`Mountain` rows in the source were merged into one; nothing else was changed.

**This is not `ruby_storm.txt` under another name.** Four of the five `storm`
lists pulled for 2026-06-01 onward *are* effectively that deck (same 39 spells,
lands shuffled by one or two). This one is the Lesson/Learn build: 4 First Day
of Class, 4 Highway Robbery and 2 maindeck Stormscale Scion in place of Reckless
Impulse, Wish, Artist's Talent and Grapeshot, over a fifteen-card sideboard that
is entirely Lesson cards fetched by Learn. Sixteen mainboard slots differ.

Measured with `scripts/survey_cards.py --deck`, the production classifier, and
then per ability with `effect_for` / `trigger_effect_for` / `activated_effect_for`
through `parse_abilities`. `EFFECTS` registry membership was **not** used.

    33 distinct cards: handled 21, silent 7, no_rules_text 5

---

## Can this deck actually kill? Partly - the engine counts, but the kill card is dead

The three primitives the archetype stands on all work. Each is asserted in
`tests/scenarios/test_storm_deck.py`:

| Primitive | State | Evidence |
|---|---|---|
| Spells cast this turn | **works** | `Game.spells_cast_this_turn` (`models/game.py:970`, appended in `put_on_stack`, `models/game.py:1716`), reset per turn |
| Storm keyword (CR 702.40a) | **works** | `machines/keywords.py:284` `_storm_ability`, `:2090` `_storm_effect`. Two rituals then Stormscale Scion produced two copies and three Dragons resolved. Copies stay out of the cast count (CR 707.10, `Game.copy_spell`) so the count does not run away |
| Rituals add mana (CR 106.4) | **works** | Pyretic Ritual and Desperate Ritual both parse `Add {R}{R}{R}` and resolve `handled`. Two Mountains in, pool ends `{R}{R}{R}` - net +1 |
| Ruby Medallion discount (CR 601.2f) | **works** | `cost_modifier_effect` (`machines/cost.py:1528`) reads it as `COLOR_DECREASE` amount 1; `Game.static_cost_modifiers_for` (`models/game.py:5809`) folds it into `Casting.total_cost`. Hex Magic {2}{R} -> {1}{R} |
| Ral, Monsoon Mage | **works** | Its own static discount is read by the same `COLOR_DECREASE`/type path; the coin-flip cast trigger dispatches on `cast_spell`; all three loyalty abilities on the back face resolve |

**What is dead: the kill.** This list's win is Stormscale Scion plus copies
attacking the turn they arrive, and the haste comes from First Day of Class.
First Day of Class is **silent on both halves** - its spell face and its
`enters_the_battlefield` trigger. The Dragons therefore enter with no +1/+1
counter and no haste and cannot attack, and Stormscale Scion's own
`Other Dragons you control get +1/+1` anthem is unmodelled too (see the layer
section). So the engine can storm out an arbitrary pile of 4/4 Dragons on turn
three and then do **nothing with them until the following turn**. Combined with
4 Highway Robbery (the deck's card-advantage engine) also resolving as nothing,
the deck assembles its combo correctly and cannot convert it.

Note this is the *Lesson* build's problem specifically. The Grapeshot builds of
the archetype would go through `_storm_effect` into damage, which is modelled.

---

## Silent spells - `effect_for` returned `None` for every clause

Grouped by the missing primitive. Oracle text is the fixture's, verbatim.

### Delayed "this turn" trigger created by an instant (1 card, 4 copies)

- **First Day of Class** `{1}{R}` Instant -
  *"Whenever a creature you control enters this turn, put a +1/+1 counter on it
  and it gains haste until end of turn. / Learn."*
  The spell face is silent, and `parse_abilities` does read the clause as a
  `TriggeredAbility` with `event=enters_the_battlefield`, but
  `trigger_effect_for` has no entry, so it is silent too. Two primitives are
  missing: a **spell that installs a delayed trigger lasting the rest of the
  turn** (this ability is not on a permanent - nothing survives resolution to
  carry it), and the trigger body's **"put a counter on it and it gains haste
  until end of turn"** pair.

### Optional cost then draw (1 card, 4 copies)

- **Highway Robbery** `{1}{R}` Sorcery -
  *"You may discard a card or sacrifice a land. If you do, draw two cards. /
  Plot {1}{R}"*
  Missing primitive: an **either/or optional self-cost** ("discard a card **or**
  sacrifice a land") gating a draw. The engine handles the single-choice shape -
  Abandon Attachments (*"You may discard a card. If you do, draw two cards."*)
  is `handled` in the same sideboard - so this is specifically the two-option
  disjunction that fails. `Plot` itself is **not** in the ignored-keyword report,
  so plot has an execution path.

### Bounce a spell on the stack (1 card, 3 copies, sideboard)

- **Divide by Zero** `{2}{U}` Instant -
  *"Return target spell or permanent with mana value 1 or greater to its owner's
  hand. / Learn."*
  Missing primitive: **returning a spell from the stack to hand**, plus the
  `mana value 1 or greater` restriction on the target. Boomerang Basics
  (*"Return target nonland permanent to its owner's hand"*) is `handled`, so
  permanent bounce exists; it is the spell half and the mana-value clause that
  do not.

### Change a spell's target (1 card, 2 copies, sideboard)

- **Redirect Lightning** `{R}` Instant -
  *"As an additional cost to cast this spell, pay 5 life or pay {2}. / Change
  the target of target spell or ability with a single target."*
  Missing primitive: **retargeting** - nothing in `machines/effects.py` changes
  an object's chosen targets. The additional cost is also an either/or
  disjunction (pay life **or** pay mana), the same shape Highway Robbery trips.

### Exile-until-threshold then cast for free (1 card, 1 copy, sideboard)

- **Improvisation Capstone** `{5}{R}{R}` Sorcery -
  *"Exile cards from the top of your library until you exile cards with total
  mana value 4 or greater. You may cast any number of spells from among them
  without paying their mana costs. / Paradigm"*
  Missing primitive: **exile-until an accumulated-mana-value threshold**. The
  engine has exile-N-then-cast (Wrenn's Resolve, Ral's -8 - both `handled`); it
  is the running-total stop condition that has no parser.

### Create several differently-statted tokens in one clause (1 card, 1 copy, sideboard)

- **Mascot Exhibition** `{7}` Sorcery -
  *"Create a 2/1 white and black Inkling creature token with flying, a 3/2 red
  and white Spirit creature token, and a 4/4 blue and red Elemental creature
  token."*
  Missing primitive: a **multi-token clause creating three distinct token
  bodies** in one sentence, two of them multicolored.

### Kicker-conditional damage (1 card, 1 copy, sideboard)

- **Firebending Lesson** `{R}` Instant -
  *"Kicker {4} / Firebending Lesson deals 2 damage to target creature. If this
  spell was kicked, it deals 5 damage to that creature instead."*
  Missing primitive: **"if this spell was kicked, ... instead"** - a
  resolution-time read of whether an optional additional cost was paid.
  `Kicker` is not in the ignored-keyword report, so the cost side is payable;
  it is the conditional damage substitution that is silent, which makes the
  whole card do nothing either way.

---

## Permanent, trigger and layer gaps (kept separate)

- **Stormscale Scion** - *"Other Dragons you control get +1/+1."* A static
  anthem on a permanent. Not in `LAYER_EFFECTS` (`machines/layers.py:3004`),
  `parsed_layer_effects` (`:2194`) returns `None`, and
  `looks_like_unparsed_layer_effect` (`:2232`) returns `False` - so it is
  neither applied **nor** flagged with a notice. It fails **silently open**:
  the Dragons are all 4/4 when a real board of three would be 5/5 each. This is
  the one gap in this deck that shows up as wrong numbers rather than as
  nothing happening.
- **First Day of Class** - the `enters_the_battlefield` trigger described above
  is recognised by `machines/triggers.py` but has no effect body.
- Everything else with a trigger is `handled`: Commercial District and
  Thundering Falls (`When this land enters, surveil 1`), Ral, Monsoon Mage's
  cast trigger, and storm itself.

---

## `no_rules_text` bucket - hand-audited three ways

`sweep_pool.has_rules_text` skips every static line on a permanent, so this
bucket is not a coverage claim. All five audited by hand.

### Genuinely empty (1)

- **Mountain** - only the parenthetical mana reminder. `parse_abilities` yields
  the mana ability, which `machines/abilities.py` handles; nothing else on it.

### Static modelled elsewhere (3)

- **Ruby Medallion** - *"Red spells you cast cost {1} less to cast."*
  Read by `cost_modifier_effect`, `machines/cost.py:1528`, as
  `CostModifierKind.COLOR_DECREASE` amount 1 applying to red; applied by
  `Game.static_cost_modifiers_for`, `models/game.py:5809`, which names the
  Medallion cycle explicitly in its docstring. Verified live: Hex Magic prices
  at `{1}{R}` with a Medallion on the battlefield and `{2}{R}` without.
- **Steam Vents** - *"As this land enters, you may pay 2 life. If you don't, it
  enters tapped."* `parse_replacement_effects`
  (`machines/replacement.py:423`) splits it into a parsed
  `ReplacementKind.AS_ENTERS` (optional, `you may pay 2 life`) and a parsed
  `ReplacementKind.ENTERS_TAPPED` gated on `condition="you don't"`.
- **Stomping Ground** - identical text, identical parse.

### Static unmodelled (1)

- **Stormscale Scion** - *"Other Dragons you control get +1/+1."* Detailed in
  the layer section above. It lands here only because `has_rules_text` skips
  static lines on permanents; it is a real gap, and a silent-open one.

---

## Keywords with no execution path

Four occurrences across three keywords. Each is checked against
`sweep_pool.executed_keywords`.

- **Splice** - Desperate Ritual (4 copies). *"Splice onto Arcane {1}{R}"*. The
  ritual's own `Add {R}{R}{R}` resolves fine, so the card works as a ritual; what
  is missing is splicing it onto Hex Magic (Sorcery - Arcane, 4 copies) for
  extra mana, a real line in this deck.
- **Learn** - First Day of Class (4), Divide by Zero (3). No path from a Learn
  clause to the sideboard, which is what the entire eleven-card Lesson sideboard
  exists for. With Learn unimplemented, **none of the fifteen sideboard cards is
  reachable in play** in this build, independently of whether each one's own
  effect is modelled.
- **Paradigm** - Improvisation Capstone (1).

Keywords in the deck that are absent from this list, and why: Storm, Flying,
Flashback (Past in Flames), Plot (Highway Robbery) and Kicker (Firebending
Lesson) are all in `executed_keywords` - a machine acts on each. Channel
(Boseiju) is an ability word, and Transform (Ral) is in `NEEDS_NO_CODE`;
neither needs its own handler.

`0 unreadable targeting phrase(s)` - `machines/targeting.py` read every
targeting clause in the deck.

## Rejections and data notes

- No `Flashback`-as-a-card artifact appeared in any of the five `storm` lists
  pulled, despite the archetype running Past in Flames. No list was rejected on
  those grounds.
- `resolve_cards` dropped two double-faced names - Ral, Monsoon Mage and Valakut
  Awakening - from a 22-name batch while reporting `not_found: []`. Both
  re-resolved legal under their full `Front // Back` names. Row counts checked
  on every batch.
- Every one of the 33 names is Modern-legal as of 2026-08-31.
