# Effect gaps: Modern dimir control

Decklist: pilot **cntrlfreak_ttv**, tournament date **2026-08-25**, source deck
`videre-58652547`. Mainboard 60, sideboard 15, every card Modern-legal as
checked with `resolve_cards(format="modern", fields="legality")` in the session
that wrote this file. The list itself lives at
`magic-cards-model-api/decks/dimir_control.txt`.

All oracle text below is quoted as `resolve_cards` returned it, not from memory.

## How "gap" was measured

`machines/effects.py` has **no explicit `EFFECTS` row for any of the 32 distinct
cards in this list**, so an `EFFECTS`-membership test alone would report all 32
as missing and tell the follow-up pass nothing. `effect_for` falls back to the
text parsers (`_spell_effect_or_notice`, `resolve_modal_spell`), which already
read 11 of the spells correctly, so the useful signal is the narrower one:

> a card is a gap when `effect_for(name, oracle_text)` returns `None` - that is
> the case where the spell resolves and does nothing.

Measured that way against the current tree:

| bucket | count |
|---|---|
| spells the text parser already reads | 11 |
| spells that resolve as nothing (**real gaps**) | 5 |
| permanents whose abilities are unregistered | 7 |
| lands | 9 |

`TRIGGER_EFFECTS` and `ACTIVATED_EFFECTS` were also checked by prefix for every
permanent and land in the list: **zero rows** for any of them.

Already covered by the parser, for reference, so nobody re-does them:
Thoughtseize, Fatal Push, Sheoldred's Edict (modal), Drown in the Loch (modal),
Force of Negation, Counterspell, Consign to Memory, Mystical Dispute, Surgical
Extraction, Glistening Deluge, Psychic Frog (its static pump clause only - see
the permanents section, the rest of the card is still missing).

---

## Counterspells

### Spell Snare - `{U}` Instant

> Counter target spell with mana value 2.

Needs a counter effect whose targeting restriction filters the stack by the
target spell's mana value being exactly 2 (not "2 or less"). The generic
counter clause exists; what is missing is the mana-value predicate on the
target, so this should batch with Stern Scolding as one "counter target spell
matching a characteristic test" shape.

### Stern Scolding - `{U}` Instant

> Counter target creature spell with power or toughness 2 or less.

Same shape as Spell Snare but the predicate is a disjunction over two printed
characteristics of a *creature* spell - power **or** toughness 2 or less, either
one satisfying it. Needs the spell-side power/toughness of a creature card on
the stack to be readable by the targeting filter.

---

## Targeted removal

### Requiting Hex - `{B}` Instant

> As an additional cost to cast this spell, you may blight 1. (You may put a
> -1/-1 counter on a creature you control.)
> Destroy target creature with mana value 2 or less. If this spell's additional
> cost was paid, you gain 2 life.

Three separate pieces: an **optional** additional cost (blight 1, itself an
unmodelled keyword action putting a -1/-1 counter on a creature you control),
a destroy restricted by the target's mana value, and a resolution-time read of
whether that optional cost was actually paid to decide the 2 life. The
"was the additional cost paid" read is the same mechanism the repo already needs
for kicker-style conditionals, so check that path before building a new one.

---

## Bounce

### Sink into Stupor - `{1}{U}{U}` Instant (front face of an MDFC; back is Soporific Springs, a land)

> Return target spell or nonland permanent an opponent controls to its owner's
> hand. // As this land enters, you may pay 3 life. If you don't, it enters
> tapped.
> `{T}: Add {U}.`

The front face needs a return-to-hand whose target set is unusual: it is **a
spell on the stack or a nonland permanent**, and restricted to things an
opponent controls. Bouncing a spell off the stack is not the ordinary bounce
target type. The back face additionally needs the "pay 3 life or enter tapped"
as-enters replacement, which is the shockland-style choice the lands below also
want.

---

## Graveyard interaction

### Cling to Dust - `{B}` Instant

> Exile target card from a graveyard. If it was a creature card, you gain 3
> life. Otherwise, you draw a card.
> Escape - `{3}{B}`, Exile five other cards from your graveyard. (You may cast
> this card from your graveyard for its escape cost.)

Needs targeting a card in *any* graveyard, an exile, and then a branch on the
exiled card's type read after it has already moved (so the check must be against
the card's last-known information, not its new zone). Separately needs the
**escape** alternative cost - cast from graveyard, with an exile-five-cards
additional cost - which is a keyword the engine does not have at all.

---

## Permanents whose abilities are unregistered

None of these have a `TRIGGER_EFFECTS` or `ACTIVATED_EFFECTS` row, so they enter
the battlefield as vanilla bodies. Listed here because the deck is unplayable in
substance without them, even though they are not "spell resolves as nothing"
gaps in the `EFFECTS` sense.

### Subtlety - `{2}{U}{U}` Creature - Elemental Incarnation (3/3)

> Flash
> Flying
> When this creature enters, choose up to one target creature spell or
> planeswalker spell. Its owner puts it on their choice of the top or bottom of
> their library.
> Evoke - Exile a blue card from your hand.

Needs an ETB trigger that targets a *spell on the stack*, removes it, and gives
its **owner** (not the trigger's controller) a top-or-bottom choice - a decision
made by a player who is not the one resolving. Also needs evoke with a
non-mana exile cost.

### Quantum Riddler - `{3}{U}{U}` Creature - Sphinx (4/6)

> Flying
> When this creature enters, draw a card.
> As long as you have one or fewer cards in hand, if you would draw one or more
> cards, you draw that many cards plus one instead.
> Warp `{1}{U}`

ETB draw is easy. The static clause is a **draw replacement effect** gated on a
hand-size condition, which must apply to its own ETB draw correctly. Warp is a
third unmodelled alternative-cost keyword.

### Orcish Bowmasters - `{1}{B}` Creature - Orc Archer (1/1)

> Flash
> When this creature enters and whenever an opponent draws a card except the
> first one they draw in each of their draw steps, this creature deals 1 damage
> to any target. Then amass Orcs 1.

One ability with **two trigger conditions in a single paragraph** (an ETB and a
draw trigger), the draw trigger carrying a per-turn exception tied to the draw
step's turn-based draw. Then amass, another unmodelled keyword action. Note the
paragraph-atomic rule: this is one ability and must resolve whole.

### Harbinger of the Seas - `{1}{U}{U}` Creature - Merfolk Wizard (2/2)

> Nonbasic lands are Islands.

A pure layer effect - type-changing applied to every nonbasic land on the
battlefield, which also strips their printed abilities and gives them
`{T}: Add {U}`. This is a `LAYER_EFFECTS` job, not an `EFFECTS` one, and it
interacts with this deck's own manabase.

### Engineered Explosives - `{X}` Artifact

> Sunburst (This artifact enters with a charge counter on it for each color of
> mana spent to cast it.)
> `{2}`, Sacrifice this artifact: Destroy each nonland permanent with mana value
> equal to the number of charge counters on this artifact.

Needs sunburst, which counts the **colors of mana actually spent** to cast the
spell - the engine must record which mana paid for a spell, not just that it was
paid. Then an activated ability doing a mass destroy whose threshold is read off
the permanent's own counters at resolution.

### Tamiyo, Inquisitive Student - `{U}` Legendary Creature - Moonfolk Wizard (0/3) // Legendary Planeswalker - Tamiyo

> Flying
> Whenever Tamiyo attacks, investigate. (Create a Clue token. It's an artifact
> with "{2}, Sacrifice this token: Draw a card.")
> When you draw your third card in a turn, exile Tamiyo, then return her to the
> battlefield transformed under her owner's control.
> ---
> +2: Until your next turn, whenever a creature attacks you or a planeswalker
> you control, it gets -1/-0 until end of turn.
> -3: Return target instant or sorcery card from your graveyard to your hand.
> If it's a green card, add one mana of any color.
> -7: Draw cards equal to half the number of cards in your library, rounded up.
> You get an emblem with "You have no maximum hand size."

Needs investigate (Clue token with its own activated ability), a **count-based
trigger** on the third card drawn in a turn, and a transforming exile-and-return
that flips a creature into a planeswalker. Then three loyalty abilities, the +2
of which creates a delayed/floating trigger with a duration.

### Kaito, Bane of Nightmares - `{2}{U}{B}` Legendary Planeswalker - Kaito

> Ninjutsu `{1}{U}{B}` (`{1}{U}{B}`, Return an unblocked attacker you control to
> hand: Put this card onto the battlefield from your hand tapped and attacking.)
> During your turn, as long as Kaito has one or more loyalty counters on him,
> he's a 3/4 Ninja creature and has hexproof.
> +1: You get an emblem with "Ninjas you control get +1/+1."
> 0: Surveil 2. Then draw a card for each opponent who lost life this turn.
> -2: Tap target creature. Put two stun counters on it.

Needs ninjutsu (a special action putting a card onto the battlefield tapped and
attacking, from hand, outside the normal casting path), a conditional
self-animating layer effect gated on both the turn and its own loyalty, an
emblem, a draw counted off "opponents who lost life this turn" (needs per-turn
life-loss tracking), and stun counters.

---

## Lands

Nine distinct lands, none with any registry row. They are grouped here because
they share three shapes rather than needing nine separate builds:

- **Fetchlands** - Flooded Strand, Polluted Delta, Marsh Flats: an activated
  ability with a pay-1-life and sacrifice cost that searches for a land with a
  given basic type and puts it onto the battlefield tapped, then shuffles. The
  repo already has fetching coverage; confirm before building.
- **Shocklands / surveil lands / fastlands** - Watery Grave, Undercity Sewers,
  Darkslick Shores: as-enters replacement effects (pay 2 life or enter tapped;
  enter tapped and surveil 1; enters untapped only if you control two or fewer
  other lands). Same as-enters mechanism Soporific Springs wants.
- **Otawara, Soaring City** - a legendary land with **channel**, a discard-from-
  hand activated ability that bounces a nonland permanent. Channel is its own
  unmodelled keyword.

Basic Island and Swamp need nothing.
