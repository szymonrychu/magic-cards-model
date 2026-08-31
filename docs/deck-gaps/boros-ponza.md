# Effect gaps: Modern boros ponza

Deck: `decks/boros_ponza.txt` in `magic-cards-model-api` - pilot **Zompatanfo**,
tournament date **2026-08-30**, source deck `videre-58656392`. All 25 distinct
cards verified Modern-legal with `resolve_cards(format="modern",
fields="legality")` on 2026-08-31.

Every card in the list was run through `scripts/survey_cards.py --deck`, which
uses the same classifier `scripts/sweep_pool.py` runs over the fixture pool. Of
25 distinct cards: 16 handled, 4 silent, 5 no rules text. Oracle text below is
verbatim from `resolve_cards`.

**Nothing in `machines/effects.py` was edited by this pass.** This file is the
work list for the follow-up.

## Mana denial / land destruction

### Field of Ruin - `silent`

Land.

```
{T}: Add {C}.
{2}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. Each player searches their library for a basic land card, puts it onto the battlefield, then shuffles.
```

Needs the activated ability to destroy the targeted nonbasic land, then have
**each player in turn order** search their own library for a basic land, put it
onto the battlefield, and shuffle. Note the contrast with Demolition Field,
which the engine already handles: Demolition Field's searches are two separate
optional ("may") searches by named players, Field of Ruin's is one mandatory
"each player searches" clause - that per-player fan-out is the missing shape,
not the destroy half.

This is the deck's headline card and the reason the archetype is called ponza;
four copies mainboard currently resolve as a colorless mana source and nothing
else.

## Impulse card advantage (play-from-exile)

### Cori Mountain Monastery - `silent`

Land.

```
This land enters tapped unless you control a Plains or an Island.
{T}: Add {R}.
{3}{R}, {T}: Exile the top card of your library. Until the end of your next turn, you may play that card.
```

Needs the activated ability to exile the top card of the library and grant its
controller permission to play that specific card from exile, with the permission
expiring at the end of that player's next turn. The "may play" permission with a
duration is the missing subsystem, not the exile. The conditional
enters-tapped clause is also unmodelled.

## Mana production

### Sunken Citadel - `silent`

Land - Cave.

```
This land enters tapped. As it enters, choose a color.
{T}: Add one mana of the chosen color.
{T}: Add two mana of the chosen color. Spend this mana only to activate abilities of land sources.
```

Needs three things: an as-enters colour choice recorded on the permanent, two
mana abilities that read that stored choice rather than a literal colour symbol
(`machines/abilities.py` only parses literal `{T}: Add {R}`-shaped text), and a
spend restriction on the second ability's mana - CR 106.6 covers mana whose
producing ability restricts how it may be spent, and CR 106.4 puts it in the
pool. The restriction here is "only to activate abilities of land sources",
which is what makes the Field of Ruin / Demolition Field / Cori Mountain
Monastery activations castable in this deck, so it is load-bearing rather than
cosmetic.

## Board wipes

### Wrath of God - `silent`

`{2}{W}{W}` Sorcery. Sideboard, 1 copy.

```
Destroy all creatures. They can't be regenerated.
```

Needs a mass-destroy of every creature on the battlefield regardless of
controller, with regeneration shields suppressed. CR 701.19 defines regenerate
as a destruction-replacement shield, and CR 701.19c is the rule that "can't be
regenerated" turns off - a shield already on the creature does not save it. Note
the mainboard sweeper Wrath of the Skies is already handled, so this is the
narrower "and can't be regenerated" rider on top of an existing shape.

## Keywords with no execution path

These three cards classify as handled or as having no rules text, but carry a
keyword the engine skips. Listed so the follow-up pass does not read the survey
counts as full coverage.

### Kaheera, the Orphanguard - `no_rules_text`, ignored keyword `Companion`

`{1}{G/W}{G/W}` Legendary Creature - Cat Beast, 3/2. Sideboard, 1 copy.

```
Companion - Each creature card in your starting deck is a Cat, Elemental, Nightmare, Dinosaur, or Beast card. (If this card is your chosen companion, you may put it into your hand from outside the game for {3} as a sorcery.)
Vigilance
Each other creature you control that's a Cat, Elemental, Nightmare, Dinosaur, or Beast gets +1/+1 and has vigilance.
```

Nothing here is modelled. Needs: companion as an outside-the-game ability
checked before the game begins against the deck's creature cards, and the
special action to move it to hand for `{3}` (CR 702.139, 702.139a); vigilance on
itself; and the static +1/+1-and-vigilance anthem over the named creature types.
In this deck the companion condition is satisfied vacuously - Solitude is an
Elemental and it is the only creature type in the mainboard - so the companion
half is what actually matters, not the anthem.

### The Legend of Roku // Avatar Roku - handled, ignored keyword `Firebending`

Enchantment - Saga, `{2}{R}{R}`. The Saga chapters are handled; the transformed
back face's `Firebending 4 (Whenever this creature attacks, add {R}{R}{R}{R}.
This mana lasts until end of combat.)` has no execution path. Needs an
attack-triggered mana ability whose mana survives the usual step-boundary
emptying until end of combat.

### Wear // Tear - handled, ignored keyword `Fuse`

Both halves are handled individually. Fuse - casting both halves as one spell
from hand - is not executed. `machines/effects.py` already carries a note about
fuse's reminder-text line, so the parser sees it; what is missing is the
casting-time option.

## Handled, for the record

Avengers Disassembled, Castle Ardenvale, Cleansing Wildfire, Demolition Field,
Erode, Galvanic Discharge, High Noon, Orim's Chant, Path to Exile, Price of
Freedom, Rest in Peace, Solitude, Surgical Extraction, Wrath of the Skies, plus
The Legend of Roku and Wear // Tear with the keyword caveats above.

No rules text (nothing to model): Mountain, Plains, Rustvale Bridge, Sacred
Foundry, and Kaheera as classified - though Kaheera is a gap, see above.

## CR numbers cited here

All verified with `knowledge_search(type="rules")` in the session that wrote
this file: 106.4, 106.6, 701.19, 701.19c, 702.139, 702.139a.
