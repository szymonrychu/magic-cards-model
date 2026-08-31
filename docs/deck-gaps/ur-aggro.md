# Effect gaps: Modern UR aggro

The list is `decks/ur_aggro.txt` in `magic-cards-model-api` - pilot **duanceyao**,
tournament date **2026-08-29**, source deck `videre-58654130`. Every card in it
resolved `legal` for modern via `resolve_cards(fields="legality")`.

Every distinct card in the mainboard and sideboard (27 names) was put through the
real dispatchers rather than eyeballed against the registry:

- spells: `effects.effect_for(name, oracle_text)`
- activated abilities: `effects.activated_effect_for(name, index, ability.effect)`
- triggered abilities: `effects.trigger_effect_for(name, ability.event, ability.effect)`

with the abilities themselves split by `machines/abilities.parse_abilities`. A
card counts as covered when that call returns an effect - `EFFECTS` rows are now
the minority case, since `effect_for` falls back to `parse_mixed_effect_for_spell`
on the card's own printed text, so most of this deck already works with no row.

**Result: 2 of the 27 names have no effect and would resolve as silence.**
Both are sideboard cards; the whole mainboard is covered.

Nothing here is implemented - `machines/effects.py` was deliberately not edited.

## Counterspells with a "unless its controller pays" rider

### Spell Pierce

`{U}` Instant.

> Counter target noncreature spell unless its controller pays {2}.

`effect_for` returns `None`. Plain "Counter target ..." is already read (Consign to
Memory parses without a row), so what is missing is specifically the **unless-tax
rider**: on resolution, offer the countered spell's controller the chance to pay a
fixed cost, and counter the spell only if they decline or cannot pay. That needs a
mid-resolution payment decision from a player who is not the ability's controller,
and the noncreature-spell restriction on the target on top.

Grouped as its own mechanic because the rider - not the counter - is the new
primitive, and the same shape recurs across the format (Mana Leak, Miscalculation).

## Mass destruction scaled by X

### Meltdown

`{X}{R}` Sorcery.

> Destroy each artifact with mana value X or less.

`effect_for` returns `None`, with and without X substituted. Needed: a
non-targeted sweeper that reads CR 107.3a's announced X off `Game.cast_record`
(`effect_for` already threads `x_value` through for exactly this) and destroys
every permanent matching a card-type-plus-mana-value predicate, across all
players. Wrath of the Skies' `_parse_x_energy_pay_destroy_by_mana_value` is the
nearest existing shape and is probably where this generalises from.

## Covered - recorded so the follow-up pass does not re-check them

| Card | How it is covered |
| --- | --- |
| Lightning Bolt | parsed from text (damage to any target) |
| Lava Dart | `EFFECTS` row |
| Unholy Heat | `EFFECTS` row (delirium damage) |
| Monstrous Rage | `EFFECTS` row |
| Assault Strobe, Mutagenic Growth | parsed (continuous effect from a resolving spell) |
| Preordain, Expressive Iteration | parsed (card selection) |
| Surgical Extraction | parsed (dedicated whole-text clause) |
| Consign to Memory | parsed (counter target triggered ability or colorless spell) |
| Heritage Reclamation, Pick Your Poison | parsed as modal (`resolve_modal_spell`) |
| Monastery Swiftspear, Slickshot Show-Off, Cori-Steel Cutter, Dragon's Rage Channeler | cast triggers all resolve via `trigger_effect_for`'s parser fallback |
| Mishra's Bauble | activated ability parsed |
| Bloodstained Mire, Wooded Foothills, Scalding Tarn | fetch ability parsed (`parse_search_and_put_effect` fallback) |
| Fiery Islet | draw ability parsed; its mana ability belongs to `machines/abilities.py`, not here |
| Steam Vents, Stomping Ground, Thundering Falls, Mountain | mana and enters-tapped are not `effects.py`'s business; Thundering Falls' surveil trigger parses |

Keyword abilities this deck leans on are outside this report's scope, because
they do not go through the card-name registries at all: prowess and equip resolve
through `machines/keywords.keyword_effect_for`, flashback (Lava Dart) and plot
(Slickshot Show-Off) are cast options in `machines/casting.py`, and replicate
(Consign to Memory) is an additional cost whose printed line `effect_for` strips
before parsing the card's real text (`_REPLICATE_LINE_RE`). Dragon's Rage
Channeler's delirium is a layers effect (`LAYER_EFFECTS`), likewise outside it.
Whether each of those is fully modelled is `docs/engine-coverage.md`'s question,
not this file's.
