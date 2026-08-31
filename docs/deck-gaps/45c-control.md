# Effect gaps: Modern "45c control"

The list: **pilot albertosd87**, tournament date **2026-08-28**, source
`videre-58655085`. Mainboard 60, sideboard 15, 37 distinct names, all confirmed
`legal` in modern by `resolve_cards(format="modern", fields="legality")`.
Decklist at `magic-cards-model-api/decks/45c_control.txt`; smoke test at
`tests/scenarios/test_45c_control_deck.py`.

Every CR number below was verified with `knowledge_search(type="rules")` in the
session that wrote this file. Where a rule could not be confirmed, it is left
uncited and said so.

## How this was measured, and what the measurement lies about

`scripts/survey_cards.py --deck` reports **20 handled / 4 silent / 13
no_rules_text**. That headline is not the answer, for four reasons that were
each reproduced here rather than taken on trust:

1. **`classify_card` reports the best outcome per card** - "a card is only
   genuinely dead if *nothing* on it does anything", per its own docstring. A
   dead clause hides behind a working one on the same card. Four cards in this
   deck are green only because of a clause nobody plays them for.
2. **`has_rules_text` skips every static line on a permanent**, so a permanent
   whose entire function is a static ability lands in `no_rules_text` - a bucket
   that reads like "nothing to check" and is not.
3. **The unparsed-layer detector fails silently open.** For Starfield Vocalist,
   High Noon and Quantum Riddler, `parsed_layer_effects(line)` returns `None`
   *and* `looks_like_unparsed_layer_effect(line)` returns `False`. Nothing is
   flagged. "Nothing was flagged" is not evidence of coverage.
4. **The ignored-keyword report is a category error for three of its four
   entries.** Domain, Converge and Revolt are *ability words*, and CR 207.2c
   says ability words "have no special rules meaning". Being "ignored" is
   correct for the word; the question is whether the sentence it heads works.
   For Converge it does; for Domain and Revolt it does not.

`EFFECTS` registry membership was not used at all. Everything below went through
`effect_for` / `trigger_effect_for` / `activated_effect_for`, or through the
real `Game` / `Casting` path, one clause at a time.

## The manabase

This was checked first and hardest, because a four-or-five-colour deck *is* its
manabase, and because a sibling found Eldrazi Temple, Ugin's Labyrinth, Cavern
of Souls and Gemstone Caverns producing **no mana at all** when a second
sentence (a CR 106.6 spend restriction, or an as-enters condition) made the mana
parser refuse the whole card.

**That failure does not occur in this deck.** Measured through
`parse_mana_abilities` / `intrinsic_land_ability`:

| Land | Copies | Produces | Note |
|---|---|---|---|
| Breeding Pool | 1 | G, U | shockland |
| Hallowed Fountain | 1 | U, W | shockland |
| Overgrown Tomb | 1 | B, G | shockland |
| Sacred Foundry | 1 | R, W | shockland |
| Steam Vents | 1 | R, U | shockland |
| Stomping Ground | 1 | G, R | shockland |
| Temple Garden | 1 | G, W | shockland |
| Indatha Triome | 1 | B, G, W | enters tapped, cycling |
| Raugrin Triome | 1 | R, U, W | enters tapped, cycling |
| Hedge Maze | 1 | G, U | surveil land |
| Forest | 1 | G | basic |
| Plains | 1 | W | basic |
| Witch-Blessed Meadow (DFC back) | 1 | W | back face of Witch Enchanter |
| Arid Mesa | 2 | - (correct) | fetch |
| Flooded Strand | 2 | - (correct) | fetch |
| Misty Rainforest | 2 | - (correct) | fetch |
| Windswept Heath | 4 | - (correct) | fetch |
| Wooded Foothills | 1 | - (correct) | fetch |

All seven shocklands parse their mana ability **despite** the second sentence
("As this land enters, you may pay 2 life. If you don't, it enters tapped."),
and that sentence is itself modelled - `machines/replacement.py:1886-1887,
2103`, CR 614.12a's as-enters choice. Both Triomes parse all three colours
despite "This land enters tapped." (`machines/replacement.py:141`, CR 614.1c).

Eleven of the twenty-two lands are fetchlands. Producing nothing is **correct**
for them - a fetchland has no mana ability - and their `{T}, Pay 1 life,
Sacrifice this land: Search...` activated ability classifies `handled`.

All five colours are reachable. The manabase is not the gap in this deck.

## Silent: four cards that genuinely do nothing

These four are dead in the engine. Nothing was recorded and nothing happened.

| Card | Copies | Dead clause |
|---|---|---|
| **Birthing Ritual** | 4 | "At the beginning of your end step, if you control a creature, look at the top seven cards... then you may sacrifice a creature..." |
| **Risen Reef** | 3 | "Whenever this creature or another Elemental you control enters, look at the top card of your library..." |
| **Renegade Rallier** | 3 | "Revolt - When this creature enters, if a permanent left the battlefield under your control this turn, return target permanent card with mana value 2 or less from your graveyard to the battlefield." |
| **Coiling Oracle** | 2 | "When this creature enters, reveal the top card of your library. If it's a land card, put it onto the battlefield..." |

Birthing Ritual is the deck's namesake engine and Risen Reef its card advantage;
between them that is 7 of 60 cards whose entire purpose is inert.

Birthing Ritual and Renegade Rallier both carry an intervening *if* clause -
CR 603.4 (the ability does not trigger unless the condition is true) and
CR 608.2a (it is rechecked on resolution). Neither reaches that check, because
the effect sentence never builds in the first place.

**Revolt could not be confirmed in the rules corpus.** `knowledge_search` has no
entry for it - independently reproducing the sibling's finding. It is therefore
left uncited here rather than guessed at.

## False greens: reported handled, behaves wrong

This is the worst category, because the survey shows a green row.

### 1. Leyline Binding - domain is never computed (4 copies)

Reported `handled`: its ETB exile trigger works. But its cost does not.

`machines/effects.py:3487` says so in its own words: *"The discount itself is
not computed anywhere in this engine."* Verified empirically rather than read -
with **all five basic land types** on the battlefield (Temple Garden, Steam
Vents, Overgrown Tomb), `Game.cost_reduction_for` returns an **empty**
`ManaCost`:

```
printed mana_cost: {5}{W}
basic land types controlled: ['Forest','Island','Mountain','Plains','Swamp'] -> 5
cost_reduction_for -> (empty)
```

So Leyline Binding is a six-mana flash enchantment in this engine, permanently,
instead of the one-mana removal spell the deck is built around. Four copies.
This is the single most consequential gap in the list, and it is invisible to
the survey.

### 2. Omnath, Locus of Creation - landfall is silent (2 copies)

Reported `handled` because `"When Omnath enters, draw a card."` works. The
clause the card is played for does not:

```
[trigger] 'When Omnath enters, draw a card.'                    -> handled
[trigger] 'Landfall - Whenever a land you control enters, ...'  -> silent
```

All three landfall modes are inert: gain 4 life, add `{R}{G}{W}{U}`, and deal 4
damage to each opponent and each planeswalker you don't control.

### 3. High Noon - the static is the card (2 sideboard)

Reported `handled` because its `{4}{R}, Sacrifice this enchantment: It deals 5
damage to any target` activated ability parses. The line it is sideboarded for -
`"Each player can't cast more than one spell each turn."` - has no
implementation anywhere in `src/`, is not a layer effect, and is **not flagged**
by `looks_like_unparsed_layer_effect`.

### 4. Quantum Riddler - the draw replacement is absent (4 copies)

Reported `handled` because `"When this creature enters, draw a card."` works.
`"As long as you have one or fewer cards in hand, if you would draw one or more
cards..."` is a draw replacement with no implementation, `parsed_layer_effects`
`None`, `looks_like_unparsed_layer_effect` `False`. Silently open.

## Confirmed *not* gaps - three prior claims that did not survive checking

Verified independently rather than inherited, since one sibling's dimir report
was contradicted on six points by a second measurement.

- **Prismatic Ending's converge bound genuinely binds.** This is *not* the
  Engineered Explosives / sunburst pattern. There is a dedicated parser,
  `_parse_converge_exile_by_colors_spent` (`machines/effects.py:8734`), which
  reads `game.cast_record(spell).mana_spent`, counts distinct non-colorless
  colours, and gates on `mana_value <= colors_spent`. The survey's
  `ignored keywords: Converge` and `unreadable targeting: [static] Converge -
  Exile target nonland permanent...` lines are **false alarms** from the side
  reports, not findings.
- **Clarion Conqueror is modelled**, despite landing in `no_rules_text`.
  `models/game.py:456 _parse_activation_prohibition` reads
  `"Activated abilities of artifacts, creatures, and planeswalkers can't be
  activated."` into all three types with `opponents_only=False` - correctly
  symmetric. Enforced at CR 602.5 ("A player can't begin to activate an ability
  that's prohibited from being activated"). Not a gap.
- **Evoke works** on Solitude (4) and Endurance (3, sideboard).
  `Casting.alternative_costs` offers an `AlternativeCostOption` citing
  **CR 702.74a**, with the exile-a-white-card / exile-a-green-card component
  built. Free-spell casting is available, which matters more for this deck than
  most.

## `no_rules_text`, audited by hand, split three ways

`has_rules_text` skips static lines on permanents, so this bucket needed reading
card by card. It is **not** 13 blank cards.

**Genuinely empty (2)** - a basic land, intrinsic mana ability only:
Forest, Plains.

**Static modelled elsewhere (10)** - named file and line:

| Card | Static line | Modelled at |
|---|---|---|
| Breeding Pool, Hallowed Fountain, Overgrown Tomb, Sacred Foundry, Steam Vents, Stomping Ground, Temple Garden | "As this land enters, you may pay 2 life. If you don't, it enters tapped." | `machines/replacement.py:1886-1887, 2103` (CR 614.12a) |
| Indatha Triome, Raugrin Triome | "This land enters tapped." + `Cycling {3}` | `machines/replacement.py:141` (CR 614.1c); `machines/keywords.py:631, 659` (cycling) |
| Clarion Conqueror | "Activated abilities of artifacts, creatures, and planeswalkers can't be activated." | `models/game.py:456` (CR 602.5) |

**Static unmodelled (1)**:

| Card | Copies | Line |
|---|---|---|
| **Starfield Vocalist** | 3 | "If a permanent entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time." |

Grepping `src/` for `an additional time` returns **zero** hits - there is no
trigger-doubling subsystem, and no Panharmonicon-shaped handler for it to join.
`parsed_layer_effects` returns `None` and `looks_like_unparsed_layer_effect`
returns `False`: nothing is flagged. Exactly the silent-open shape.

## Clause-by-clause: everything that does work

Confirmed through the real dispatchers, one clause at a time.

| Card | Working clause |
|---|---|
| Arid Mesa, Flooded Strand, Misty Rainforest, Windswept Heath, Wooded Foothills | fetch activated ability |
| Consign to Memory | "Counter target triggered ability or colorless spell." |
| Endurance | ETB graveyard-to-library trigger; Evoke |
| Ephemerate | blink resolution |
| Hedge Maze | "When this land enters, surveil 1." |
| High Noon | `{4}{R}, Sacrifice: 5 damage to any target` (see false green above) |
| Leyline Binding | ETB exile trigger (see false green above) |
| Omnath | ETB draw (see false green above) |
| Pest Control | "Destroy all nonland permanents with mana value 1 or less." |
| Phelia, Exuberant Shepherd | attack trigger |
| Prismatic Ending | converge exile, bound correctly |
| Quantum Riddler | ETB draw (see false green above) |
| Solitude | ETB exile trigger; Evoke |
| Voice of Resurgence | opponent-casts / dies trigger |
| White Orchid Phantom | ETB destroy-nonbasic trigger |
| Witch Enchanter | ETB destroy artifact/enchantment trigger; back face taps for W |

`Phelia, Exuberant Shepherd`'s top-level spell dispatch reports `notice` rather
than `handled`. That is correct and not a gap: a permanent spell has no
resolution text of its own to dispatch.

## Ignored keywords, in full

Four occurrences. Three are ability words (CR 207.2c - no special rules
meaning), so the word being ignored is right and only the sentence matters.

| Reported | Card | Real status |
|---|---|---|
| Converge | Prismatic Ending | ability word; sentence **is** modelled. False alarm. |
| Domain | Leyline Binding | ability word; sentence **not** modelled - the cost reduction never applies. Real. |
| Revolt | Renegade Rallier | ability word; sentence **not** modelled, card silent. Real. No CR entry exists for revolt. |
| Replicate | Consign to Memory | real keyword, **CR 702.56a**. Its line is stripped so the resolution sentence parses (`machines/effects.py:3350-3360`); replicate itself is not payable. |

Keywords the survey did **not** flag and that were checked anyway, all working:
Evoke (CR 702.74a), Flash, Flying, Lifelink, Reach, First strike, Cycling,
Rebound, Warp.

## Ranked, by cards affected

1. **Leyline Binding** - domain never reduces; 4 copies at {5}{W} instead of {W}.
2. **Birthing Ritual** - 4 copies, wholly silent; the deck's engine.
3. **Quantum Riddler** - 4 copies, draw replacement absent and unflagged.
4. **Risen Reef** - 3 copies, wholly silent.
5. **Renegade Rallier** - 3 copies, wholly silent.
6. **Starfield Vocalist** - 3 copies, trigger doubling absent and unflagged.
7. **Omnath, Locus of Creation** - 2 copies, all three landfall modes silent.
8. **Coiling Oracle** - 2 copies, wholly silent.
9. **High Noon** - 2 sideboard, the static that defines it is absent.

## CR numbers cited, all verified this session

100.2a, 100.4a, 103.5, 103.8a, 106.6, 207.2c, 602.5, 603.4, 608.2a, 614.1c,
614.12a, 702.56a, 702.74a.

Not verifiable: **revolt** has no entry in the rules corpus and is left uncited.
