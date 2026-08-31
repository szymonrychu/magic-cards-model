# Effect gaps: broodscale bloodchief (Modern)

The list is `decks/broodscale_bloodchief.txt` in `magic-cards-model-api` - pilot
unagieel, 2026-08-30, source deck `videre-58656378`. All 30 distinct cards
resolve Modern-legal through `resolve_cards(format="modern", fields="legality")`
and every one has a real Scryfall printing in `tests/fixtures/cards/`.

This file records **what the engine does not do yet**, per ability, so a
follow-up pass can batch the work. Nothing here was implemented:
`machines/effects.py` is deliberately untouched.

## How each row was decided

Not by grepping `EFFECTS` - that would over-report. For each card the real
dispatch path was walked:

- `parse_abilities(card)` to split the oracle text into abilities.
- a spell's effect through `effects.effect_for(name, text)`, which falls back to
  `parse_mixed_effect_for_spell` when there is no explicit row.
- a trigger through `effects.trigger_effect_for(name, event, text)`.
- an activated ability through `effects.activated_effect_for(name, index, text)`.
- a static through `layers.LAYER_EFFECTS` and `layers.parsed_layer_effects(...,
  static_only=True)`.

So "gap" below means the engine genuinely produces no effect, not merely that
there is no hand-written row.

Oracle text throughout is quoted verbatim from `resolve_cards`.

Every CR number in this file was looked up with `knowledge_search(type="rules")`
in the session that wrote it. The verified set is listed at the bottom.

## What already works

These need nothing:

- **Emrakul, the Promised End** - the cast trigger has a row, and its
  self-reduction ("costs {1} less to cast for each card type among cards in
  your graveyard") is `Game.cost_reduction_for`'s job, not a layer effect.
- **Malevolent Rumble** - explicit `EFFECTS` row.
- **Sowing Mycospawn** - both `CAST_SPELL` triggers reach the parser fallback.
- **Urza's Saga** - all three chapters parse.
- **Vexing Bauble**, **Haywire Mite**, **Springleaf Drum**, **Dismember**,
  **Nature's Claim**, **Boseiju, Who Endures** (both halves),
  **Devourer of Destiny**'s cast trigger, **Soul-Guide Lantern**'s enter trigger
  and its draw ability, **Basking Broodscale**'s `{1}{G}: Adapt 1`,
  **Shifting Woodland**'s delirium copy ability, **Sire of Seven Deaths** (all
  keywords), **Forest**.

---

## Counters and the combo itself

### Basking Broodscale

> Devoid (This card has no color.)
> {1}{G}: Adapt 1. (If this creature has no +1/+1 counters on it, put a +1/+1 counter on it.)
> Whenever one or more +1/+1 counters are put on this creature, you may create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}."

Gap: the counters-placed trigger. `parse_abilities` reads it as a
`TriggeredAbility` but with `event=None` - the engine has no trigger event for
"one or more counters are put on this permanent" (CR 122.6 covers counters put
on an object, and CR 122.7 is the related Nth-counter shape), so it never fires
at all. **Needed:** a trigger event fired when +1/+1 counters land on a
permanent, plus an optional token-creation effect (CR 111.1, 701.7a) that makes
the Eldrazi Spawn with its own `Sacrifice this token: Add {C}` mana ability.
This is the deck's engine - without it the archetype does nothing.

### Blade of the Bloodchief

> Whenever a creature dies, put a +1/+1 counter on equipped creature. If equipped creature is a Vampire, put two +1/+1 counters on it instead.
> Equip {1}

Gap: the dies trigger. The event is recognised (`dies`) but no effect is
produced. **Needed:** an effect that puts a +1/+1 counter on the permanent this
Equipment is attached to (CR 301.5a, 301.5f define "equipped creature"), doubled
to two when that creature is a Vampire. Equip itself is a CR 702.6a keyword and
is handled by `machines/keywords.py`.

---

## Tokens (modal half)

### Kozilek's Command

> Choose two —
> • Target player creates X 0/1 colorless Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}."
> • Target player scries X, then draws a card.
> • Exile target creature with mana value X or less.
> • Exile up to X target cards from graveyards.

Partial gap. `effect_for` dispatches to `resolve_modal_spell`, and after
`substitute_x` three of the four modes parse. **Mode 1 does not** - "Target
player creates N 0/1 colorless Eldrazi Spawn creature tokens with '...'" is not
a shape the token parser reads. **Needed:** a token-creation clause that makes N
tokens for a *targeted player* with an embedded quoted mana ability (CR 111.1,
111.2, 701.7a). Same token as Basking Broodscale and Glaring Fleshraker make, so
one token definition serves three cards.

---

## Library selection

### Ancient Stirrings

> Look at the top five cards of your library. You may reveal a colorless card from among them and put it into your hand. Then put the rest on the bottom of your library in any order.

Gap: the whole spell. `effect_for` returns nothing - the existing
select-from-the-top family does not read this shape (look at five, optional
reveal restricted **by colour identity being colorless**, remainder to the
*bottom* rather than the graveyard). **Needed:** a select-from-the-top effect
with a colorless-only filter on what may be taken and a bottom-of-library
remainder.

---

## Mana abilities with a rider or a spend restriction

These are all `{T}: Add ...` abilities whose *second* sentence the mana-ability
parser refuses, so the ability produces no mana at all. CR 106.6 is the rule for
mana that carries a restriction on how it may be spent; CR 605.1a is what keeps
these abilities mana abilities in the first place.

### Eldrazi Temple

> {T}: Add {C}.
> {T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi.

Gap: the second ability. The plain `{T}: Add {C}` works. **Needed:** two
colorless mana carrying a CR 106.6 spend restriction keyed on "colorless Eldrazi
spell or ability of a colorless Eldrazi". Four copies in the deck; this is the
deck's actual acceleration, so the deck cannot cast Emrakul on curve without it.

### Ugin's Labyrinth

> Imprint — When this land enters, you may exile a colorless card with mana value 7 or greater from your hand.
> {T}: Add {C}. If a card is exiled with this land, add {C}{C} instead.
> {T}: Return the exiled card to its owner's hand.

Gap: the middle ability. The imprint trigger and the return ability both work.
**Needed:** a conditional mana ability that reads whether this permanent has an
imprinted (exiled-with) card and adds `{C}{C}` if so, `{C}` otherwise.

### Cavern of Souls

> As this land enters, choose a creature type.
> {T}: Add {C}.
> {T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type, and that spell can't be countered.

Gap: the any-colour ability, and the entry choice. **Needed:** (a) an
as-enters replacement (CR 614.1c) recording a chosen creature type on the
permanent, (b) one mana of any colour carrying a CR 106.6 restriction to
creature spells of that type, and (c) the uncounterable rider on the spell that
mana pays for.

### Gemstone Caverns

> If this card is in your opening hand and you're not the starting player, you may begin the game with Gemstone Caverns on the battlefield with a luck counter on it. If you do, exile a card from your hand.
> {T}: Add {C}. If Gemstone Caverns has a luck counter on it, instead add one mana of any color.

Two gaps. The static is a CR 103.6 / 103.6a opening-hand action - the engine has
no hook for "begin the game with this on the battlefield" at all. The mana
ability is the same conditional shape as Ugin's Labyrinth, keyed on a luck
counter instead. **Needed:** an opening-hand action step between the mulligan
(CR 103.5) and the first turn, plus the counter-conditional mana ability.

---

## Graveyard hate and sacrifice

### Soul-Guide Lantern

> When this artifact enters, exile target card from a graveyard.
> {T}, Sacrifice this artifact: Exile each opponent's graveyard.
> {1}, {T}, Sacrifice this artifact: Draw a card.

Gap: the middle ability only. **Needed:** an effect exiling every card in each
opponent's graveyard (CR 406.2 for exiling). The mass, untargeted,
per-opponent-graveyard shape is what the parser is missing; the enters trigger's
single-target version already parses.

---

## Static abilities: cost setting and taxing

### Trinisphere

> As long as this artifact is untapped, each spell that would cost less than three mana to cast costs three mana to cast.

Gap. `cost_modifier_effect` *does* read this sentence, but there is no
`LAYER_EFFECTS` row and `parsed_layer_effects` does not build one, so the
untapped-condition and the cost floor are not wired into CR 601.2f's total-cost
calculation from the battlefield. **Needed:** the cost modifier applied
conditionally on the source being untapped.

### Disruptor Flute

> Flash
> As this artifact enters, choose a card name.
> Spells with the chosen name cost {3} more to cast.
> Activated abilities of sources with the chosen name can't be activated unless they're mana abilities.

Gap, all three non-keyword lines. `cost_modifier_effect` returns nothing and
`looks_like_unparsed_cost_modifier` flags it - the shape is chosen-name-relative,
which nothing reads. **Needed:** (a) an as-enters name choice (CR 614.1c),
(b) a CR 601.2f cost increase filtered on that name, (c) an activation
prohibition (CR 602.5) exempting mana abilities (CR 605.1a). Flash is a keyword
and is handled.

### Pithing Needle

> As this artifact enters, choose a card name.
> Activated abilities of sources with the chosen name can't be activated unless they're mana abilities.

Gap. The same name choice and the same CR 602.5 / 605.1a activation
prohibition as Disruptor Flute's third line - one mechanism serves both.

---

## Static abilities: zone and cast prohibitions

### Grafdigger's Cage

> Creature cards in graveyards and libraries can't enter the battlefield.
> Players can't cast spells from graveyards or libraries.

Gap, both lines. **Needed:** (a) a battlefield-entry prohibition filtered by
card type and origin zone, and (b) a casting prohibition by origin zone
(CR 113.6f is the related "functions everywhere" rule for zone-restricting
abilities). Note the CR 111.5 interaction: a token that could not enter is not
created - the same prohibition machinery is what would make that fall out.

### Soulless Jailer

> Permanent cards in graveyards can't enter the battlefield.
> Players can't cast noncreature spells from graveyards or exile.

Gap, both lines. Same two mechanisms as Grafdigger's Cage, with a
permanent-card filter and a noncreature filter, and exile added as an origin
zone.

---

## Static abilities: type changing and enters-tapped

### Yavimaya, Cradle of Growth

> Each land is a Forest in addition to its other land types.

Gap. A CR 613.1d layer 4 type-adding effect over every land on the battlefield.
**Needed:** an in-addition-to land subtype grant applied board-wide (the
in-addition-to variant already exists for single permanents; the board-wide
selector is what is missing).

### Shifting Woodland

> This land enters tapped unless you control a Forest.
> {T}: Add {G}.
> Delirium — {2}{G}{G}: This land becomes a copy of target permanent card in your graveyard until end of turn. Activate only if there are four or more card types among cards in your graveyard.

Gap: the first line only - both abilities work. **Needed:** a CR 614.1c /
614.12 enters-tapped replacement gated on a board condition ("unless you control
a Forest"). Note this interacts with the Yavimaya gap above: with Yavimaya out,
every land is a Forest, so Shifting Woodland enters untapped.

### Devourer of Destiny

> You may reveal this card from your opening hand. If you do, at the beginning of your first upkeep, look at the top four cards of your library. You may put one of those cards back on top of your library. Exile the rest.
> When you cast this spell, exile target permanent that's one or more colors.

Gap: the opening-hand reveal only - the cast trigger works. This is CR 103.6b's
reveal-from-opening-hand action, which the engine has no hook for, plus the
delayed first-upkeep trigger it sets up. Same missing opening-hand step as
Gemstone Caverns, so the two batch together.

---

## Summary

19 gaps across 15 cards. By mechanic:

| Mechanic | Cards |
|---|---|
| counters trigger + token creation | Basking Broodscale, Blade of the Bloodchief, Kozilek's Command (mode 1) |
| library selection | Ancient Stirrings |
| mana with a spend restriction or a rider | Eldrazi Temple, Ugin's Labyrinth, Cavern of Souls, Gemstone Caverns |
| mass graveyard exile | Soul-Guide Lantern |
| cost setting / taxing statics | Trinisphere, Disruptor Flute |
| activation prohibition by chosen name | Disruptor Flute, Pithing Needle |
| zone / cast prohibitions | Grafdigger's Cage, Soulless Jailer |
| type-changing static | Yavimaya, Cradle of Growth |
| conditional enters-tapped | Shifting Woodland |
| opening-hand actions (CR 103.6) | Gemstone Caverns, Devourer of Destiny |

Two cross-cutting subsystems would close most of it: an **opening-hand action
step** (CR 103.6, 103.6a, 103.6b) and a **chosen-name/chosen-type as-enters
choice** with prohibition and cost-tax consumers.

## CR numbers verified in this session

100.2a, 100.4a, 100.5, 103.2a, 103.3, 103.4, 103.5, 103.6, 103.6a, 103.6b,
106.6, 111.1, 111.2, 111.5, 113.6f, 122.6, 122.7, 301.5a, 301.5f, 402.1, 406.2,
601.2f, 602.5, 605.1a, 613.1d, 614.1c, 614.12, 701.7a, 702.6a.
