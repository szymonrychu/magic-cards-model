# Effect gaps: grixis reanimator

The deck is `decks/grixis_reanimator.txt` in the companion API repo - pilot
innaig88, 2026-08-30, source `videre-58656361`. The canonical archetype name in
the statistics data is `reanimator`; this list is grixis (Blood Crypt, Steam
Vents, Watery Grave). All 31 distinct cards resolve `legal` in modern.

## How "gap" was measured

`machines/effects.py` no longer keys everything by name: `effect_for` falls back
to `parse_mixed_effect_for_spell` over the card's own oracle text, so a card
with no `EFFECTS` row can still resolve correctly. **No card in this deck has an
explicit `EFFECTS` row.** The gap that matters is therefore
`effect_for(name, oracle_text) is None` - the spell resolves and does nothing.

Measured by calling `effect_for` directly against the fixture oracle text.
Oracle text below is verbatim from `resolve_cards`.

Summary:

- 10 of 31 cards resolve today through the text parser.
- 8 spells are genuine dead-on-resolution gaps.
- 13 are lands/permanents: they are never "resolved" as a spell effect, so their
  gap is in the ability layers (`machines/abilities.py` and the trigger system),
  not in `effects.py`. Listed last, separately, so the follow-up pass does not
  mistake them for registry work.

Do not treat this file as a work order for `machines/effects.py` alone - several
of the entries below need trigger or replacement-effect plumbing first.

---

## Already covered (no action)

These parse today via `effect_for`, no row needed:

Consign to Memory, Emperor of Bones, Faithless Looting, Fatal Push, Mystical
Dispute, Psychic Frog, Pyroclasm, Surgical Extraction, Thought Scour,
Thoughtseize.

Note two of those are partial: Emperor of Bones and Psychic Frog parse a
*clause*, but their activated and triggered abilities are separate machinery -
see the permanents section.

---

## Gap group 1: reanimation from the graveyard

The core of the deck. Both are targeted "return a creature card from your
graveyard to the battlefield" with a rider, and neither parses.

### Persist - `{1}{B}` Sorcery

> Return target nonlegendary creature card from your graveyard to the
> battlefield with a -1/-1 counter on it.

Needs: a graveyard-targeting return-to-battlefield effect, restricted to
nonlegendary creature cards in the controller's own graveyard, that puts the
permanent onto the battlefield under the caster's control with one -1/-1 counter
already on it (the counter is part of the same event, not a follow-up).

### Unearth - `{B}` Sorcery

> Return target creature card with mana value 3 or less from your graveyard to
> the battlefield.
> Cycling {2} ({2}, Discard this card: Draw a card.)

Needs: the same return-to-battlefield effect with a mana-value-3-or-less filter
on the target instead. Separately needs cycling as an alternative activated
ability from hand - check whether the cycling keyword is already handled before
scripting it here.

---

## Gap group 2: enters-the-battlefield / attack triggers on the reanimation targets

### Archon of Cruelty - `{6}{B}{B}` Creature - Archon

> Flying
> Whenever this creature enters or attacks, target opponent sacrifices a
> creature or planeswalker of their choice, discards a card, and loses 3 life.
> You draw a card and gain 3 life.

Needs: a single triggered ability with two trigger conditions (enters, attacks)
firing one composite effect - opponent-chooses sacrifice of a creature or
planeswalker, then that opponent discards one card, then loses 3 life, then the
controller draws one and gains 3. This is the payoff the whole deck exists to
cheat into play; without it, reanimating the Archon does nothing at all. It is
one paragraph, so it must resolve whole or fail closed.

### Abhorrent Oculus - `{2}{U}` Creature - Eye

> As an additional cost to cast this spell, exile six cards from your graveyard.
> Flying
> At the beginning of each opponent's upkeep, manifest dread. (Look at the top
> two cards of your library. Put one onto the battlefield face down as a 2/2
> creature and the other into your graveyard. Turn it face up any time for its
> mana cost if it's a creature card.)

Needs three things: an additional cast cost that exiles six cards from the
caster's own graveyard (a cost, so it is paid at announcement and is not
optional); an upkeep trigger that fires on *each opponent's* upkeep rather than
the controller's; and `manifest dread` itself - look at the top two, one goes to
the battlefield face down as a 2/2, the other to the graveyard, with the
face-down permanent turnable face up for its mana cost if it is a creature card.
Face-down permanents are the largest missing piece here.

---

## Gap group 3: discard

### Inquisition of Kozilek - `{B}` Sorcery

> Target player reveals their hand. You choose a nonland card from it with mana
> value 3 or less. That player discards that card.

Needs: reveal-hand, then a *caster* choice constrained to nonland cards of mana
value 3 or less, then a targeted discard of that specific card. Thoughtseize
already parses, so this is the same shape plus the mana-value filter and minus
the life loss - the parser gap is likely just the "with mana value 3 or less"
qualifier on the chosen card.

---

## Gap group 4: counterspells

### Spell Pierce - `{U}` Instant

> Counter target noncreature spell unless its controller pays {2}.

Needs: the existing counter-unless-pays effect (Mystical Dispute already parses
one) narrowed to a noncreature-spell target restriction. Likely a small
extension of the same clause parser rather than new machinery.

---

## Gap group 5: mass removal keyed to X

### Meltdown - `{X}{R}` Sorcery

> Destroy each artifact with mana value X or less.

Needs: a non-targeted mass destroy over artifacts filtered by mana value against
the announced X. `effect_for` already accepts an `x_value` and re-tries the
substituted text, so this may be within reach of the existing mass-destroy
parser once "each artifact with mana value N or less" is a recognised group.

---

## Gap group 6: sacrifice-rider artifacts (sideboard)

### Nihil Spellbomb - `{1}` Artifact

> {T}, Sacrifice this artifact: Exile target player's graveyard.
> When this artifact is put into a graveyard from the battlefield, you may pay
> {B}. If you do, draw a card.

Needs: an activated ability whose cost includes sacrificing itself, with an
exile-a-whole-graveyard effect; plus a dies-trigger with an optional mana
payment gating a draw.

### Vexing Bauble - `{1}` Artifact

> Whenever a player casts a spell, if no mana was spent to cast it, counter that
> spell.
> {1}, {T}, Sacrifice this artifact: Draw a card.

Needs: a cast-trigger with an intervening-if condition on *how the spell was
paid for* (no mana spent) - the engine has to record mana actually spent during
payment for this to be answerable - plus the self-sacrifice draw ability.

### Damping Sphere - `{2}` Artifact

> If a land is tapped for two or more mana, it produces {C} instead of any other
> type and amount.
> Each spell a player casts costs {1} more to cast for each other spell that
> player has cast this turn.

Needs: two static effects - a replacement effect over mana production from
lands, and a global cost increase computed from a per-player per-turn spell
count. Neither is a resolution effect; both belong in the continuous-effects and
cost-calculation layers.

---

## Permanents: not `effects.py` work

These 13 never resolve as spell effects. Their gaps are mana abilities,
enters-tapped replacement effects, activated abilities, and triggers.

| Card | What is missing |
|---|---|
| Island, Swamp | Nothing - basic mana abilities parse. |
| Blood Crypt, Steam Vents, Watery Grave | "As this land enters, you may pay 2 life. If you don't, it enters tapped." - an as-enters replacement effect with an optional life payment. |
| Raucous Theater, Thundering Falls, Undercity Sewers | Enters tapped, plus an enters-trigger that surveils 1. |
| Bloodstained Mire, Polluted Delta, Scalding Tarn | Activated ability costing {T}, 1 life and self-sacrifice, searching the library for a typed land, putting it onto the battlefield, then shuffling. |
| Psychic Frog | Combat-damage-to-player-or-planeswalker draw trigger; a discard-cost activated ability adding a +1/+1 counter; an exile-three-from-graveyard cost granting flying until end of turn. |
| Emperor of Bones | Beginning-of-combat exile-from-a-graveyard trigger; adapt 2; and a trigger on +1/+1 counters being put on it that returns a card exiled with it with a finality counter, haste, and a delayed sacrifice at the next end step. |

Psychic Frog and Emperor of Bones show up as "parses" above only because one
clause of their text is readable; their ability set is not modelled.
