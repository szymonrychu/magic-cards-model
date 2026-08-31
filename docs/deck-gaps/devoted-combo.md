# Devoted combo - effect gaps

The Modern "devoted combo" archetype (Devoted Druid + Vizier of Remedies /
Tyvar, Jubilant Brawler, into Walking Ballista or Tyvar, the Pummeler), as one
real registered list.

- **List**: pilot `musasabi`, tournament 2026-08-29, source deck
  `videre-58655572`, pulled with
  `statistics_decks(format="modern", archetype_name="devoted combo",
  date_from="2026-06-01", include_cards="full", limit=5)`.
- **Legality**: all 38 distinct names came back `legal` from
  `resolve_cards(names=[...], format="modern", fields="legality")`. Nothing in
  the list is banned or unavailable in Modern.
- **Decklist file**: `magic-cards-model-api/decks/devoted_combo.txt`.
- **Smoke test**: `tests/scenarios/test_devoted_combo_deck.py`.

## How this was measured

Not by grepping `machines/effects.py`. Each printing was run through the
production dispatchers - `effect_for`, `trigger_effect_for`,
`activated_effect_for`, with the card's abilities split by
`parse_abilities` - using `scripts/survey_cards.py --deck`, which reuses
`scripts/sweep_pool.classify_card` verbatim. That matters here: eight cards in
this list carry rules text and have **no** row in any registry, yet are fully
covered by a text parser or by a different subsystem entirely. Grepping the
registry would have reported them as gaps.

Whole-deck result (38 distinct cards):

| outcome | count |
|---|---|
| handled | 27 |
| silent (a real gap) | 1 |
| no rules text the classifier judges | 10 |

`no_rules_text` is not the same as "not implemented" - `has_rules_text` gates
out a permanent's static line that is not a continuous-effect shape, because
those belong to subsystems this classifier does not audit. Each of those ten
was checked by hand against the subsystem that does own it; the results are in
"Covered elsewhere" below.

## Genuinely uncovered

### Infinite-mana / pump sinks

**Tyvar, the Pummeler** - `{1}{G}{G}`, Legendary Creature - Elf Warrior, 3/3.
Oracle text (`resolve_cards`):

> Tap another untapped creature you control: Tyvar gains indestructible until
> end of turn. Tap it.
>
> {3}{G}{G}: Creatures you control get +X/+X until end of turn, where X is the
> greatest power among creatures you control.

The only card in the list that classifies **silent**: nothing on it does
anything. Both abilities are activated, both reach
`create_continuous_effect_of_ability`, and that hands the clause to
`machines/layers.py`, which reads neither. `_layer_category` on the whole card
returns `None`, so not even a `LayerNotice` is recorded - it fails open, which
is worse than failing closed.

Two missing primitives, isolated by probing `parsed_layer_effects` clause by
clause:

- **Granting `indestructible` is not in the keyword-grant vocabulary.**
  `"This creature gains flying until end of turn."` parses;
  `"This creature gains indestructible until end of turn."` does not, and
  neither does the `Target creature gains ...` form. This is a vocabulary hole,
  not a shape hole - the surrounding grant syntax already works
  (CR 702.12/702.12a: indestructible is a static ability;
  CR 702.12b: such a permanent can't be destroyed).
- **A team pump whose magnitude is CR 107.3f's computed X.**
  `"Creatures you control get +2/+2 until end of turn."` parses;
  `"... get +X/+X until end of turn, where X is the greatest power among
  creatures you control."` does not. CR 107.3f is X defined by the ability's
  own text rather than announced on activation (CR 107.3a), so no `x_value`
  substitution can rescue it - the magnitude has to be computed from board
  state at resolution (CR 611.2a/611.2c).

This is the deck's payoff card, so the gap is load-bearing: the Devoted Druid
loop generates arbitrary mana and Tyvar is one of the two ways the list turns
that into a win.

### Protection / damage prevention

**Crystal Barricade** (sideboard) - `{1}{W}`, Artifact Creature - Wall, 0/4.
Oracle text:

> Defender (This creature can't attack.)
>
> You have hexproof. (You can't be the target of spells or abilities your
> opponents control.)
>
> Prevent all noncombat damage that would be dealt to other creatures you
> control.

Defender is executed. Neither of the other two lines is.

- **Hexproof on a *player* (CR 702.11c) is not modelled.** The engine has
  hexproof on a permanent (CR 702.11b) - `tests/scenarios/test_hexproof.py`
  says so in its own header - but nothing grants or checks it on a player, so
  the targeting layer never consults it.
- **A static, unbounded prevention shield is unparsed.**
  `parse_replacement_effects` returns this line with `kind=unparsed,
  parsed=False`, so it does fail closed. The prevention subsystem exists
  (CR 615.7 counting shields, CR 615.9 source recheck, CR 615.11 per-creature
  shields, CR 615.12 unpreventable damage), but its parser is anchored on
  "Prevent the next N ..." and "Prevent all [combat] damage ...". The missing
  primitive is `noncombat` as a damage-kind filter plus an affected set of
  "other creatures you control".

### Ability-granting / mana-conversion statics

**Agatha's Soul Cauldron** - `{2}`, Legendary Artifact. Oracle text:

> You may spend mana as though it were mana of any color to activate abilities
> of creatures you control.
>
> Creatures you control with +1/+1 counters on them have all activated
> abilities of all creature cards exiled with Agatha's Soul Cauldron.
>
> {T}: Exile target card from a graveyard. When a creature card is exiled this
> way, put a +1/+1 counter on target creature you control.

The `{T}` ability is handled (an explicit reflexive-trigger parser,
`_EXILE_TARGET_REFLEXIVE_CREATURE_RE`), which is why the card classifies
`handled` overall. Both statics are not:

- **"Spend mana as though it were mana of any color to activate abilities of
  creatures you control"** has no implementation. `machines/cost.py` models
  restricted mana in the other direction (Shang-Chi's and Delighted Halfling's
  "spend this mana only to ..."), but there is no *permission* widening of an
  existing pool's colour for a class of activations.
- **Granting "all activated abilities of all creature cards exiled with this"**
  has no implementation - grep for `all activated abilities` in `src/` returns
  nothing. This needs an ability-granting continuous effect whose granted set
  is read off another zone (the cards exiled with the Cauldron), which the
  layers engine has no primitive for.

In this deck the Cauldron is how Devoted Druid's untap ability gets onto a
creature that is not Devoted Druid, so this is a real combo line the engine
cannot play.

### Alternative costs

**Nature's Rhythm** - `{2}{G}{G}` Sorcery. Oracle text:

> Search your library for a creature card with mana value X or less, put it
> onto the battlefield, then shuffle.
>
> Harmonize {X}{G}{G}{G}{G} (You may cast this card from your graveyard for its
> harmonize cost by tapping X untapped creatures you control.)

The search half is handled. **Harmonize is not implemented at all** - grep for
`harmonize` across `machines/casting.py`, `machines/cost.py` and
`machines/abilities.py` returns nothing, and `sweep_pool --card` reports the
keyword as `IGNORED`. CR 702.180a makes harmonize three static abilities (one
functioning from the graveyard, two while the spell is on the stack) and
CR 702.180b puts the choice of which creatures to tap at CR 601.2b. The missing
primitive is a graveyard-castable alternative cost (CR 118.9/118.9b) whose
payment taps creatures rather than producing mana.

## Covered elsewhere - would have been false gaps

Every one of these carries rules text and has no `EFFECTS` row. All are
implemented, in a subsystem `classify_card` deliberately does not audit.

| card | line | where it lives |
|---|---|---|
| Vizier of Remedies | "If one or more -1/-1 counters would be put on a creature you control, that many minus one ..." | `machines/replacement.py` (`if_would_instead`, parses) |
| Collector Ouphe | "Activated abilities of artifacts can't be activated." | `models/game.py` activation gate |
| Delighted Halfling | "Add one mana of any color. Spend this mana only to cast a legendary spell, and that spell can't be countered." | `machines/cost.py` restricted mana + `machines/casting.py` |
| Shang-Chi, Master of Kung Fu | "Add two mana of any one color. Spend this mana only to activate abilities of creature sources." | `machines/cost.py`, `models/mana.py` |
| Overgrown Tomb, Temple Garden | "As this land enters, you may pay 2 life. If you don't, it enters tapped." | `machines/replacement.py` (`as_enters` + `enters_tapped`, both parse) |
| Forest, Dryad Arbor | the reminder-text mana ability | `machines/abilities.intrinsic_land_ability`, CR 305.6 |
| Birds of Paradise | "Flying" + "{T}: Add one mana of any color." | keyword table + mana-ability parser (CR 113.4, CR 605.3b: a mana ability never uses the stack, so it never reaches `effect_for`) |
| Leyline of Abundance | "If this card is in your opening hand, you may begin the game with it on the battlefield" | `machines/replacement.py` (CR 103.6a) |
| Summoner's Pact | "At the beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose the game." | `machines/effects._pay_or_lose_the_game` via `machines/delayed.py` |
| Fatal Push | the Revolt clause | `Game.revolt_active_for`, `tests/scenarios/test_fatal_push_revolt.py` |
| Kraul Harpooner | "Undergrowth - ... fights ..." | `_parse_undergrowth_pump_and_fight_clause`, `_fight` (CR 701.14a) |
| Badgermole Cub | "earthbend 1" | `tests/scenarios/test_earthbend.py` (CR 701.66a) |

The keyword-execution side report flags `Revolt`, `Undergrowth` and `Fight` as
`IGNORED`, but that report reads a keyword table, not behaviour: all three are
executed through the effect-text parsers above. Revolt and Undergrowth are
ability words anyway (CR 207.2c: no special rules meaning of their own), so a
keyword-table entry would be wrong. `Harmonize` is the one flag that is a real
gap.

## CR numbers cited here

Every one was verified with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: 103.6a is the only one taken from an existing
in-repo citation rather than looked up fresh, and is marked as such.

- CR 107.3a, 107.3f - X announced on activation vs X defined by the text.
- CR 113.4, CR 605.3b - mana abilities do not use the stack.
- CR 118.9, 118.9b - alternative costs.
- CR 207.2c, 207.2d - ability words and flavor words have no rules meaning.
- CR 305.6 - a land with a basic land type has the intrinsic mana ability.
- CR 611.2a, 611.2c - duration and affected set of a continuous effect from a
  resolving ability.
- CR 615.7, 615.9, 615.11, 615.12 - prevention shields.
- CR 701.14a - fight.
- CR 701.66a - earthbend N.
- CR 702.11b, 702.11c - hexproof on a permanent vs on a player.
- CR 702.12, 702.12a, 702.12b - indestructible.
- CR 702.180a, 702.180b - harmonize.
