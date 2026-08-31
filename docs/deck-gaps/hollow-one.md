# Effect gaps: Modern "hollow one"

List: **hockeybro26**, event 2026-08-29, source deck `videre-58656118`
(`statistics_decks(format="modern", archetype_name="hollow one")`).
Decklist file: `decks/hollow_one.txt` in the `magic-cards-model-api` repo.
Twenty-six distinct names, all Modern-legal (`resolve_cards(format="modern",
fields="legality")`, 2026-08-31).

## How this was measured

Not by `EFFECTS` membership - that over-reports badly, because
`effect_for`/`trigger_effect_for`/`activated_effect_for` all fall back to text
parsers when a card has no registry row. Every card here was parsed with
`machines/abilities.parse_abilities` and every ability pushed through the
dispatcher it would actually reach in a game, which is what
`scripts/survey_cards.py --deck` runs:

```
uv run python scripts/survey_cards.py --deck .../decks/hollow_one.txt
```

## The split

| Category | Count | Cards |
|---|---|---|
| handled | 13 | Arid Mesa, Blazing Rootwalla, Bloodstained Mire, Elegant Parlor, Faithless Looting, Hardened Academic, Lightning Bolt, Prismatic Ending, Scalding Tarn, Surgical Extraction, Vexing Bauble, Wear // Tear, Wooded Foothills |
| notice (fails closed) | 1 | Practiced Offense |
| silent | 5 | Burning Inquiry, Enter the Avatar State, Marauding Mako, Rough // Tumble, Vengevine |
| no_rules_text | 7 | Arena of Glory, Damping Sphere, Detective's Phoenix, Hollow One, Mountain, Sacred Foundry, Street Wraith |

**`no_rules_text` is not a synonym for covered.** The classifier skips a
permanent's static line and a pure mana ability by design, so a card whose
*entire* function is a static line lands in that bucket with nothing checked.
Of the seven above, only **Mountain** (a basic land's mana ability, CR 605.1a)
and **Sacred Foundry** (a shockland's "as this land enters, you may pay 2
life" replacement, owned by `machines/replacement.py`) are genuinely fine.
The other five carry real, unmodelled text and are sectioned below.

## Does the archetype's engine function? No.

The deck is three interlocking mechanics. One of the three works.

### 1. Cost reduction from cards discarded this turn - **dead**

**Hollow One** `{5}` Artifact Creature - Golem
"This spell costs {2} less to cast for each card you've cycled or discarded
this turn. / Cycling {2}"

`Game.cost_reduction_for` (CR 601.2f) reads exactly two shapes off a spell's
own text: `_COSTS_LESS_PER_CARD_TYPE` ("...for each card type among cards in
your graveyard") and `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE`. Hollow One
matches neither, and nothing anywhere in `src/` counts cards discarded or
cycled this turn - there is no `discarded_this_turn` counter to read. The
golem therefore always costs its printed `{5}`. Since the entire deck exists
to cast a 4/4 for zero on turn one, this single gap kills the archetype.
Missing primitive: **a per-turn discard/cycle counter, plus a cost-reduction
shape keyed to it.**

### 2. Madness - **works**

**Blazing Rootwalla** `{R}` Creature - Lizard, "Madness {0}".
CR 702.35a's two abilities are both modelled: the discard-replacement half is
`machines/keywords.madness_replaces_discard`, the triggered half is
`_madness_ability`, and `machines/keywords.discard` routes each discarded card
through it. `machines/cost.py` and `machines/casting.py` know the madness cost
(CR 702.35b's alternative-cost path). This is the one engine piece that is
real.

Cycling (CR 702.29a) is likewise executed - Street Wraith, Hollow One and
Marauding Mako all have a working cycling ability, and CR 702.29d's "cycles
or discards" identity is respected because `Game.discard_cards` is the single
emitter of the discard event.

### 3. Discard-triggered recursion and payoffs - **dead**

Two of the three payoffs parse a trigger the engine recognises and then reach
a dispatcher that hands back `None`; the third has no trigger event at all.

**Marauding Mako** `{R}` Creature - Shark Pirate
"Whenever you discard one or more cards, put that many +1/+1 counters on this
creature. / Cycling {2}"
The trigger event *is* recognised (`DISCARDS_A_CARD`, and `Game.discard_cards`
even emits it with `amount=len(cards)` for CR 603.2c batching), but
`trigger_effect_for` returns `None` for the effect. Missing primitive: **"put
that many +1/+1 counters on this permanent" - a counter-placement effect whose
magnitude comes from the trigger event's own amount.**

**Vengevine** `{2}{G}{G}` Creature - Elemental
"Haste / Whenever you cast a spell, if it's the second creature spell you cast
this turn, you may return this card from your graveyard to the battlefield."
Event parses as `cast_spell`; `trigger_effect_for` returns `None`. Missing
primitives: **CR 603.4's intervening-if evaluated against a per-turn count of
creature spells cast, and an optional (CR 601-style "you may") return of the
ability's own source card from graveyard to battlefield.**

**Hardened Academic** `{R}{W}` Creature - Bird Cleric
"Flying, haste / Discard a card: This creature gains lifelink until end of
turn. / Whenever one or more cards leave your graveyard, put a +1/+1 counter
on target creature you control."
Classified `handled` only on the strength of the *activated* lifelink ability.
Its triggered ability parses with `event is None` - `machines/triggers.py` has
no event for "one or more cards leave your graveyard", so in a real game it
never fires. Missing primitive: **a graveyard-departure event.**

**Detective's Phoenix** `{2}{R}` Enchantment Creature - Phoenix
"Bestow-{R}, Collect evidence 6. / Flying, haste / Enchanted creature gets
+2/+2 and has flying and haste. / You may cast this card from your graveyard
using its bestow ability."
Every recursive part of this card is unmodelled: bestow (CR 702.103a-b) and
collect evidence (CR 701.59a) are both keywords with no execution path, the
bestowed-Aura buff is an unread static line, and the graveyard-casting
permission line has no home. Only flying and haste do anything. Missing
primitives: **bestow, collect evidence, and cast-from-graveyard permission.**

## Silent spells (resolve and do nothing)

**Burning Inquiry** `{R}` Sorcery
"Each player draws three cards, then discards three cards at random."
`effect_for` returns `None`. Probing the sentence apart shows the whole family
is missing, not just the randomness: "Each player discards three cards." also
returns `None`. Missing primitives: **an each-player discard clause, and CR
701.9b's random-discard variant on top of it.** This is the deck's other
turn-one enabler, so its absence compounds gap 1.

**Rough // Tumble** `{1}{R} // {5}{R}` Sorcery // Sorcery *(sideboard)*
"Rough deals 2 damage to each creature without flying." /
"Tumble deals 6 damage to each creature with flying."
Both halves silent. Bare "deals N damage to each creature" *is* handled; the
flying filter is what breaks it. Missing primitive: **a creature-subset filter
("with/without <keyword>") on a damage-to-each-creature clause.** Its `Fuse`
keyword (CR 702.102a) also has no execution path, so the card can only ever be
cast one half at a time (CR 709.3).

**Enter the Avatar State** `{W}` Instant - Lesson *(sideboard)*
"Until end of turn, target creature you control becomes an Avatar in addition
to its other types and gains flying, first strike, lifelink, and hexproof."
Silent. Two separate causes: type-addition is unmodelled, and the leading
duration clause defeats the keyword-granting parser - "Until end of turn,
target creature you control gains flying." returns `None` while the same
sentence with the duration at the end parses. Missing primitives: **a
front-loaded "Until end of turn," duration prefix, and a creature-type
addition effect.**

## Permanents whose gaps live in other subsystems

These are not `machines/effects.py` gaps; they belong to layers, replacement,
or cost-modification and are listed separately for that reason.

**Damping Sphere** `{2}` Artifact *(sideboard)*
"If a land is tapped for two or more mana, it produces {C} instead of any
other type and amount. / Each spell a player casts costs {1} more to cast for
each other spell that player has cast this turn."
Both lines are static abilities on a permanent, so the classifier skipped them
and reported `no_rules_text`. The first is a mana-production replacement; the
second is a board-wide cost increase whose magnitude depends on a per-turn
spell count that, like the discard count above, nothing tracks. In play this
artifact does nothing at all.

**Arena of Glory** Land
"This land enters tapped unless you control a Mountain. / {T}: Add {R}. /
{R}, {T}, Exert this land: Add {R}{R}. If that mana is spent on a creature
spell, it gains haste until end of turn."
The two mana abilities parse (CR 605.1a) and `exert` has an execution path,
but the second ability's rider comes back with both `rider=None` and
`unparsed_rider=None` - the "if that mana is spent on a creature spell, it
gains haste" clause is dropped without a notice. Missing primitive: **a
spent-mana rider that grants a keyword to the spell it paid for.**

**Hollow One** - the cost-reduction line above is also a static ability on a
permanent, which is precisely why it hid in `no_rules_text`. Same failure mode
as Mox Opal's metalcraft restriction.

## Keywords with no execution path

| Keyword | CR | Cards |
|---|---|---|
| Bestow | 702.103a | Detective's Phoenix |
| Collect evidence | 701.59a | Detective's Phoenix |
| Fuse | 702.102a | Wear // Tear, Rough // Tumble *(sideboard)* |
| Converge | 207.2c (ability word) | Prismatic Ending *(sideboard)* |

Executed and working across the list: madness, cycling, flashback, haste,
flying, swampwalk/landwalk, exert.

## Unreadable targeting

`machines/targeting.py` could not read one phrase, on a sideboard card:
Prismatic Ending's "Converge - Exile target nonland permanent if its mana
value is less than or equal to the number of colors of mana spent to cast this
spell." The card is still classified `handled` on its exile clause; the
converge bound is what is missing.

## CR numbers cited here

All verified with `knowledge_search(type="rules")` in the session that wrote
this file: 100.2a, 100.4a, 103.2a, 103.3, 103.4, 103.5, 103.8, 207.2c, 401.1,
601.2f, 603.2c, 603.4, 605.1a, 701.9a, 701.9b, 701.59a, 702.29a, 702.29d,
702.35a, 702.35b, 702.102a, 702.103a, 702.103b, 709.3.

Note for anyone copying from `tests/scenarios/test_starting_a_game.py`: the
starting player taking their first turn is **CR 103.8**, not 103.7.
