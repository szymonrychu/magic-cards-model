# Effect gaps: pinnacle affinity

The list is `decks/pinnacle_affinity.txt` in `magic-cards-model-api` - pilot
**Shamplade**, tournament date **2026-08-29**, source deck `videre-58656063`.
Every card in it is Modern-legal as of this pass (`resolve_cards(...,
format="modern", fields="legality")`, 28 distinct names, 28 `legal`).

The verdicts below come from the production classifier, not from reading:

```sh
uv run python scripts/survey_cards.py --deck .../decks/pinnacle_affinity.txt
```

28 distinct cards surveyed: **15 handled, 6 silent, 7 no rules text**. A
*silent* card is the bug category - the engine produced no effect and recorded
no notice, so it resolves and does nothing.

Oracle text below is exactly what `resolve_cards` returned. Nothing here is
implemented - `machines/effects.py` is deliberately untouched by this pass.

---

## 1. Alternate ways to pay a cost (improvise)

CR 702.126a: "Improvise is a static ability that functions while the spell with
improvise is on the stack. 'Improvise' means 'For each generic mana in this
spell's total cost, you may tap an untapped artifact you control rather than pay
that mana.'" This is the archetype's whole engine, and it powers two of the six
silent cards.

### Metallic Rebuke - silent, ignored keyword `Improvise`

`{2}{U}` Instant

> Improvise (Your artifacts can help cast this spell. Each artifact you tap
> after you're done activating mana abilities pays for {1}.)
> Counter target spell unless its controller pays {3}.

Needs: the counter-unless-pays effect (the engine already has this shape - see
`_counter_unless_pays_effect`, which Mystical Dispute reaches), plus improvise
as a cost-payment option in `machines/cost.py` so tapping artifacts covers the
`{2}`. The silence is the effect half; the keyword report is the cost half.

### Kappa Cannoneer - silent, ignored keyword `Improvise`

`{5}{U}` Artifact Creature - Turtle Warrior, 4/4

> Improvise (Your artifacts can help cast this spell. Each artifact you tap
> after you're done activating mana abilities pays for {1}.)
> Ward {4}
> Whenever this creature or another artifact you control enters, put a +1/+1
> counter on this creature. It can't be blocked this turn.

Needs: a self-or-other-artifact ETB trigger that puts a +1/+1 counter on the
source and grants it unblockable until end of turn - two instructions in one
paragraph, so it has to resolve whole or fail closed. Ward {4} is CR 702.21a
("counter that spell or ability unless that player pays [cost]") and is a
separate triggered ability. Improvise as above.

---

## 2. Artifact-entering triggers

### Pinnacle Emissary - silent

`{1}{U}{R}` Artifact Creature - Robot, 3/3

> Whenever you cast an artifact spell, create a 1/1 colorless Drone artifact
> creature token with flying and "This token can block only creatures with
> flying."
> Warp {U/R} (You may cast this card from your hand for its warp cost. Exile
> this creature at the beginning of the next end step, then you may cast it
> from exile on a later turn.)

Needs: a cast-an-artifact-spell trigger creating a token whose own text box
carries a granted ability and a blocking restriction. Warp is CR 702.185a - two
static abilities functioning while the card is on the stack, one creating a
delayed triggered ability - and is not in the deck's critical path for a smoke
test but is a real alternative cost the engine does not model.

Note the sibling that already works: **Weapons Manufacturing** classifies as
handled, so the nontoken-artifact-enters trigger shape exists. Pinnacle
Emissary's trigger is on *casting*, not entering, which is why it falls through.

---

## 3. Sacrifice and regeneration

### Welding Jar - silent, ignored keyword `Regenerate`

`{0}` Artifact

> Sacrifice this artifact: Regenerate target artifact.

Needs: regeneration as a destruction-replacement effect. CR 614.8 and CR 701.19a:
a resolving spell or ability that regenerates a permanent creates a replacement
effect protecting it the next time it would be destroyed this turn, tapping it
and removing it from combat instead. The sacrifice-as-cost half already works
elsewhere in the deck (Claws of Gix, Tormod's Crypt, Mishra's Bauble all
classify as handled), so the missing piece is specifically the regeneration
shield.

---

## 4. Conditional damage (metalcraft)

### Galvanic Blast - silent

`{R}` Instant

> Galvanic Blast deals 2 damage to any target.
> Metalcraft - Galvanic Blast deals 4 damage instead if you control three or
> more artifacts.

Needs: a magnitude that is chosen at resolution by a board-state count. Metalcraft
is an ability word (CR 207.2c: ability words "have no special rules meaning and
are not represented in the game rules") - the actual work is the second sentence's
"deals 4 damage instead if you control three or more artifacts", a conditional
replacement of the first clause's amount, not a second damage event.

### Whipflare - silent

`{1}{R}` Sorcery

> Whipflare deals 2 damage to each nonartifact creature.

Needs: an untargeted sweep that deals damage to each creature matching a
*negated* type predicate ("nonartifact"). The plain "deals N damage to each
creature" shape is not enough on its own; the filter is the gap.

---

## 5. Cards the classifier reports as `no rules text` but that are not vanilla

These are not in the silent count, so they are not bugs by the sweeper's own
metric, but three of them do have real static text the engine is not reading.
Recorded here so the follow-up pass does not mistake the clean count for
completeness. (The other four - Island, Shivan Reef, Spirebluff Canal, Steam
Vents - are lands whose mana abilities `machines/abilities.py` parses, so those
really are nothing to do.)

- **Mox Opal** `{0}` Legendary Artifact - "Metalcraft - {T}: Add one mana of
  any color. Activate only if you control three or more artifacts." The mana
  ability itself parses; the *activation restriction* (the metalcraft gate) is
  the part with no execution path, so the engine would let it tap for mana on
  turn one.
- **Pithing Needle** `{1}` Artifact - "As this artifact enters, choose a card
  name. / Activated abilities of sources with the chosen name can't be activated
  unless they're mana abilities." Needs an as-enters choice stored on the
  permanent plus a static activation restriction keyed to it.
- **Damping Sphere** `{2}` Artifact - "If a land is tapped for two or more mana,
  it produces {C} instead of any other type and amount. / Each spell a player
  casts costs {1} more to cast for each other spell that player has cast this
  turn." Two statics: a mana-production replacement and a controller-relative
  cost increase.

---

## 6. Keywords reported as ignored on otherwise-handled cards

The classifier calls these cards handled because their non-keyword text produces
a real effect, but the keyword itself has no execution path.

| Card | Keyword | CR | What is missing |
| --- | --- | --- | --- |
| Emry, Lurker of the Loch | Affinity | 702.41a | "This spell costs {1} less to cast for each artifact you control." Emry's ETB mill and her graveyard-cast activated ability both work; the cost reduction does not. |
| Engineered Explosives | Sunburst | 702.44a | Enters with a charge counter for each color of mana spent to cast it. The `{2}, Sacrifice` half already destroys each nonland permanent with matching mana value, so without sunburst it always fires at zero counters. |
| Consign to Memory | Replicate | 702.56 | Copy the spell for each time the replicate cost was paid. The counter-a-triggered-ability-or-colorless-spell half is handled. |
| Kappa Cannoneer, Metallic Rebuke | Improvise | 702.126a | See section 1. |
| Welding Jar | Regenerate | 701.19a / 614.8 | See section 3. |

---

## Summary

| Category | Count | Cards |
| --- | --- | --- |
| Silent (resolves and does nothing) | 6 | Galvanic Blast, Kappa Cannoneer, Metallic Rebuke, Pinnacle Emissary, Welding Jar, Whipflare |
| Handled but with an ignored keyword | 4 | Consign to Memory (Replicate), Emry (Affinity), Engineered Explosives (Sunburst), plus the two improvise cards already counted as silent |
| Static text read as "no rules text" | 3 | Damping Sphere, Mox Opal, Pithing Needle |
| Genuinely complete | 15 | Blood Moon, Claws of Gix, Emry (ETB + activated), Engineered Explosives (activated), Experimental Synthesizer, Fiery Islet, Mishra's Bauble, Mystical Dispute, Shadowspear, Sink into Stupor // Soporific Springs, Skateboard, Tormod's Crypt, Urza's Saga, Weapons Manufacturing, Consign to Memory (counter half) |

The deck loads, shuffles, and starts a game correctly today
(`tests/scenarios/test_pinnacle_affinity_deck.py`). What it cannot yet do is
play out: improvise makes the curve, and without it plus the Pinnacle Emissary
and Kappa Cannoneer triggers the deck has no clock.
