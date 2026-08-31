# Effect gaps: Modern instant reanimator

The list is pepeteam's "instant reanimator", played 2026-08-29 (source deck
videre-58655435), pulled with `statistics_decks(format="modern",
archetype_name="instant reanimator", date_from="2026-06-01",
include_cards="full")`. All 34 distinct cards verified Modern-legal with
`resolve_cards(format="modern", fields="legality")`. The list itself lives at
`tests/scenarios/test_instant_reanimator_deck.py` and in the API repo at
`decks/instant_reanimator.txt`.

Every oracle text below is as `resolve_cards` returned it. Every CR number
below was looked up with `knowledge_search(type="rules")` in the session that
wrote this file: CR 100.2a, CR 100.4a, CR 103.3, CR 103.5, CR 121.6a, CR 121.7,
CR 401.1, CR 402.1, CR 614.11b, CR 701.6a, CR 701.17a.

## How "gap" was measured

`machines/effects.py` is deliberately minimal: `EFFECTS` is an explicit table,
but `effect_for` falls back to `parse_mixed_effect_for_spell` on the card's own
oracle text, and `trigger_effect_for` / `activated_effect_for` fall back to
`_ability_effect_or_notice` the same way. So "no `EFFECTS` row" is *not* the
same as "does nothing" any more - almost none of these cards has a row, and
most of them still resolve correctly through the text parsers.

What is listed here is the stricter and more useful thing: each card's printed
abilities were parsed with `machines/abilities.parse_abilities` and each one
put through the dispatcher it would actually reach at resolution
(`effect_for`, `trigger_effect_for`, `activated_effect_for`). A gap is an
ability where that came back `None` - the ability resolves and does nothing.

**Nothing in `machines/effects.py` was edited.** This file is the input to a
later pass.

## Summary

7 gaps across 6 cards, out of 34 distinct cards on the list.

| Card | Ability | Kind |
|---|---|---|
| Atraxa, Grand Unifier | enters-the-battlefield trigger | reveal / card selection |
| Fallaji Archaeologist | enters-the-battlefield trigger | self-mill + card selection |
| Faithful Mending | the spell | draw / discard |
| Spell Snare | the spell | counter with a condition |
| Quantum Riddler | static draw-replacement | replacement effect |
| Breeding Pool, Godless Shrine, Hallowed Fountain, Watery Grave | "as this land enters, you may pay 2 life" | see note below |

The 28 remaining cards all produce an effect through the existing registries or
text parsers, including Goryo's Vengeance, Ephemerate, Solitude, Psychic Frog,
Griselbrand's activated ability, every fetchland, every surveil land, Thoughtseize,
Force of Negation, Consign to Memory, Mystical Dispute, Surgical Extraction,
Prismatic Ending, March of Otherworldly Light, Otherworldly Gaze,
Wrath of the Skies, Clarion Conqueror and Teferi, Time Raveler.

---

## Reanimation

No gap. The archetype's engine card already reads.

**Goryo's Vengeance** - `Instant - Arcane`

> Return target legendary creature card from your graveyard to the battlefield.
> That creature gains haste. Exile it at the beginning of the next end step.
> Splice onto Arcane {2}{B} (As you cast an Arcane spell, you may reveal this
> card from your hand and pay its splice cost. If you do, add this card's
> effects to that spell.)

`effect_for` returns an effect. The sacrifice-at-end-of-turn rider ("Exile it
at the beginning of the next end step") is a delayed trigger and
`machines/delayed.py` is on the path, so this is noted as covered rather than
as a gap; if a scenario proves the exile does not fire, that becomes a gap
entry here.

**Ephemerate**, **Solitude** - both read. Ephemerate's rebound and Solitude's
evoke are keyword machinery, not effect rows.

## Discard / self-mill / card selection

**Atraxa, Grand Unifier** - `Legendary Creature - Phyrexian Angel`

> Flying, vigilance, deathtouch, lifelink
> When Atraxa enters, reveal the top ten cards of your library. For each card
> type, you may put a card of that type from among the revealed cards into your
> hand. Put the rest on the bottom of your library in a random order. (Artifact,
> battle, creature, enchantment, instant, land, planeswalker, and sorcery are
> card types.)

Gap: the enters-the-battlefield trigger. Needs to reveal the top ten from the
library, then run one optional choice **per card type** over the revealed set
(a card may be chosen for only one type it has), move each chosen card to hand,
and put the remainder on the bottom of the library in a random order - a
randomized bottom-of-library placement, not an ordered one.

**Fallaji Archaeologist** - `Creature - Human Scout`

> When this creature enters, mill three cards. You may put a noncreature,
> nonland card from among the cards milled this way into your hand. If you
> don't, put a +1/+1 counter on this creature. (To mill a card, put the top card
> of your library into your graveyard.)

Gap: the enters-the-battlefield trigger. Needs CR 701.17a's mill of three, then
a *linked* optional choice restricted to the cards milled this way and to
noncreature nonland cards, with an else-branch that puts a +1/+1 counter on the
source. The linkage matters: the choice is over the three cards this ability
milled, not over the graveyard.

**Faithful Mending** - `Instant`

> You gain 2 life, draw two cards, then discard two cards.
> Flashback {1}{W}{U} (You may cast this card from your graveyard for its
> flashback cost. Then exile it.)

Gap: the spell. Three clauses in printed order - gain 2 life, draw two, then
discard two - as one sequence; the discard is a chosen discard by the caster,
and it happens after the draws, so the drawn cards are legal discards. Flashback
is separate machinery and is not part of this gap.

## Counterspells

**Spell Snare** - `Instant`

> Counter target spell with mana value 2.

Gap: the spell. The counter itself is CR 701.6a and already exists elsewhere in
the registry; what is missing is the shape - a counter whose *target
restriction* is a mana-value equality on the targeted spell. The targeting
predicate has to reject a spell of any other mana value at announcement, not
just fizzle at resolution.

## Replacement effects

**Quantum Riddler** - `Creature - Sphinx`

> Flying
> When this creature enters, draw a card.
> As long as you have one or fewer cards in hand, if you would draw one or more
> cards, you draw that many cards plus one instead.
> Warp {1}{U}

Gap: the third line only - the enters trigger already reads. This is a
conditional draw-replacement (CR 121.7, CR 614.11b): while its controller has
one or fewer cards in hand, a draw of N is replaced by a draw of N+1. It has to
be applied at the moment the draw would happen, re-checking the hand-size
condition each time, and it is self-limiting because the replaced draw usually
takes the hand above one card.

## Lands

**Breeding Pool**, **Godless Shrine**, **Hallowed Fountain**, **Watery Grave**

> ({T}: Add {W} or {B}.) [colors vary per land]
> As this land enters, you may pay 2 life. If you don't, it enters tapped.

`parse_abilities` returns this as a `StaticAbility` and there is no
`machines/effects.py` entry for it, but `models/game.py` handles shockland
entry as a replacement effect on the way in (see `game.py` around the
fetched-at-1-life comment), which is the correct place for it - it is an
"as this enters" replacement, not a resolving effect. Listed here for the
follow-up pass to confirm with a scenario rather than to implement in
`effects.py`; if the scenario shows the choice is never offered, the fix
belongs in the replacement path, not the effect registry.

The three surveil lands (Meticulous Archive, Shadowy Backstreet, Undercity
Sewers) and all three fetchlands (Flooded Strand, Marsh Flats, Polluted Delta)
read correctly today - no gap.

## Protection / interaction - no gaps

Force of Negation, Consign to Memory, Mystical Dispute, Surgical Extraction,
Prismatic Ending, March of Otherworldly Light, Otherworldly Gaze, Thoughtseize,
Wrath of the Skies, Clarion Conqueror's "activated abilities ... can't be
activated" static, and Teferi, Time Raveler's sorcery-speed static and both
loyalty abilities all produce an effect through the existing path.
