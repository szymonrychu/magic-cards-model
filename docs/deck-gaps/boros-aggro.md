# Boros aggro - effect gaps

The list: Modern boros aggro, pilot **AeonLock**, tournament date **2026-08-30**,
source deck `videre-58656372`, pulled with `statistics_decks(format="modern",
archetype_name="boros aggro", date_from="2026-06-01", include_cards="full")`.
Registered at `magic-cards-model-api/decks/boros_aggro.txt` and mirrored in
`tests/scenarios/test_boros_aggro_deck.py`. All 35 distinct printings are Modern
legal (`resolve_cards(..., format="modern", fields="legality")`).

## How this was measured

`uv run python scripts/survey_cards.py --deck .../boros_aggro.txt` - the
production dispatchers (`effect_for`, `trigger_effect_for`,
`activated_effect_for`) called with the arguments `models/game.py` uses.

**Not** by `machines/effects.py` `EFFECTS` membership. **Zero** of the 35 cards
have an `EFFECTS` row, and 28 of them still resolve correctly, because
`effect_for` falls through to `parse_mixed_effect_for_spell` over the card's own
oracle text. Counting registry rows would have reported this deck as 0% covered.

## The split

| Category | Count |
| --- | --- |
| handled | 28 |
| notice (fails closed) | 0 |
| **silent** (resolves as nothing) | **1** |
| no rules text for this tool to judge | 6 |

Unreadable targeting phrases: 0. Ignored keyword occurrences: 2.

## Silent spells and abilities - the real gap

### Repeat-count branching on a triggered ability

**Belladonna Took** `{1}{W}` Legendary Creature - Halfling Citizen (2/2)

> Whenever a token you control enters, you gain 1 life if this is the first time
> this ability has resolved this turn. If it's the second time, draw a card. If
> it's the third time, put a +1/+1 counter on each creature you control.

`trigger_effect_for` returns nothing, so the trigger goes on the stack and
resolves having done nothing at all - **none** of the three branches fire. This
is the only card in the 60 + 15 that is silent, and it is the deck's payoff for
Ocelot Pride / Ajani / Voice of Victory / Ragavan token production, so the miss
is not cosmetic.

Missing primitive: **a per-turn resolution counter on one triggered ability,
with a branch selected by that count.** The engine has nothing that records "how
many times has *this* ability resolved this turn". The CR recognises the shape
in two neighbouring places - CR 603.7h (a delayed trigger that "triggers when the
ability that created it has resolved a certain number of times in a turn") and
CR 603.2h ("Do this only once each turn") - but neither is a general
first/second/third selector, and neither is implemented here. Landing it needs
the counter itself plus an ordinal-branch parser; the three payload clauses
(gain life, draw a card, put a +1/+1 counter on each creature you control) are
all primitives the engine already has.

## Permanents whose gaps live in the trigger / activated / static layers

`survey_cards.py` files a permanent's **static** line as `no_rules_text` by
design: those lines belong to `machines/replacement.py`,
`machines/casting_restrictions.py` or `models/game.py`, never to
`machines/effects.py`. **`no_rules_text` is therefore not evidence of coverage**,
so each of the six is resolved by hand below.

### Genuinely unmodelled

**Voice of Victory** `{1}{W}` Creature - Human Bard (1/3)

> Mobilize 2 (Whenever this creature attacks, create two tapped and attacking
> 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next
> end step.)
> Your opponents can't cast spells during your turn.

Mobilize 2 **is** modelled (`machines/keywords.py::_mobilize_ability`). The
second line is not. It is a static ability generating a continuous effect that
affects the rules of the game rather than any characteristic (CR 604.2,
CR 611.1) - the family `machines/casting_restrictions.py` owns - but that module
carries only five shapes: Teferi's sorcery-speed static, Ranger-Captain of Eos's
"opponents can't cast noncreature spells this turn", Orim's Chant's targeted
"can't cast spells this turn", Teferi's flash grant, and Ral's cost reduction.
There is no live-static blanket "your opponents can't cast spells", and nothing
anywhere reads the "during your turn" scoping as a restriction window (the one
hit for that phrase in the engine is a trigger-condition parser in
`machines/triggers.py`). In play the opponent will be allowed to hold up
interaction on your turn, which is the entire reason this card is in the deck.

Missing primitive: **a battlefield-scanned static that forbids all casting by
the source's opponents, active only during the source controller's turn.**

### Modelled elsewhere - checked, not assumed

- **Clarion Conqueror** - "Activated abilities of artifacts, creatures, and
  planeswalkers can't be activated." Read by `models/game.py`'s activation
  prohibition, which names Clarion Conqueror explicitly. Flying is executed.
- **Containment Priest** - "If a nontoken creature would enter and it wasn't
  cast, exile it instead." A replacement effect in
  `machines/replacement.py`, honoured by `Game`'s enter-the-battlefield path.
  Flash is executed.
- **Sacred Foundry** - "As this land enters, you may pay 2 life. If you don't,
  it enters tapped." `machines/replacement.py::_pay_life_or_tapped`.
- **Mountain**, **Plains** - pure mana abilities, nothing to model.

## Keywords with no execution path

Both are on sideboard cards, and both are parsed but never executed:

| Card | Keyword | CR |
| --- | --- | --- |
| The Legend of Roku // Avatar Roku | Firebending | CR 702.189a - "Whenever this creature attacks, add N {R}. Until end of combat, you don't lose this mana as steps and phases end." |
| Wear // Tear | Fuse | CR 702.102a - a static ability on a split card in hand, letting a player cast both halves from hand as one spell |

Firebending's absence costs Avatar Roku's attack ramp. Fuse's absence means Wear
// Tear can only ever be cast as one chosen half (CR 709.3), which is legal play
but not the whole card.

## Not gaps

No card in the deck produced a fail-closed notice, and
`machines/targeting.py` read every targeting phrase in the list.

---

CR numbers on this page were verified with `knowledge_search(type="rules")` in
the session that wrote it: 100.2a, 100.4a, 603.2h, 603.7h, 604.2, 611.1, 702.102a,
702.189a, 709.3.
