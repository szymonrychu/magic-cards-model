# Belcher - effect-gap report

Deck: `magic-cards-model-api/decks/belcher.txt` - PrismaticPrism, 2026-08-27,
source deck `videre-58653611`. 0.8% of the current Modern metagame. All 25
distinct names verified `legal` in Modern with `resolve_cards(format="modern",
fields="legality")`.

Smoke test: `tests/scenarios/test_belcher_deck.py`.

Measurement: `uv run python scripts/survey_cards.py --deck
.../decks/belcher.txt`, plus a clause-by-clause probe of `effect_for` /
`activated_effect_for` / `parse_abilities` per printed face. `EFFECTS`
membership was not consulted - it is not a coverage signal. Raw `effect_for(...)
is None` was not treated as a gap for a land face or a permanent spell, where
`None` is the correct answer.

## What this deck is

Not a ritual deck. Mono-blue Charbelcher: **zero true lands**. All 24 mana
sources are the land back faces of seven modal double-faced cards, plus four
Lotus Bloom. That is the archetype - a library with almost no land card in it
makes Goblin Charbelcher's "reveal until you reveal a land card" reveal an
enormous pile of nonlands and deal that much damage.

So the archetype question is not "do the rituals add mana" (there are no
rituals). It is: **do the MDFC land backs add mana, does Lotus Bloom, and does
Charbelcher's activated ability read?**

## Headline: this deck cannot win

| Piece | Status |
|---|---|
| MDFC land backs add mana | **works** - all 7 parse a `ManaAbility` |
| Lotus Bloom's 3 mana of one colour | **works** - `any_color=True, any_color_count=3` |
| Suspend 3 (how Lotus Bloom is deployed) | **works** - `machines/casting.py` `MarkedExile.suspend` / `finish_suspend` |
| Goblin Charbelcher's activation | **SILENT** - resolves and does nothing, no damage |
| Whir of Invention (the tutor that finds it) | **SILENT**, and Improvise is an ignored keyword |
| Sea Gate Restoration's draw (the library-emptying half) | **SILENT** |

The mana engine works end to end. The kill does not. `test_belcher_deck.py`
pins this as a strict `xfail`: with a Charbelcher and a Lotus Bloom on the
battlefield and four nonlands over an Island, activating Charbelcher targeting
the opponent leaves them on 20 life instead of 16. The ability goes on the
stack, resolves, and does nothing (CR 119.2 / CR 120.3a: damage dealt to a
player by a source without infect causes that player to lose that much life -
none is dealt).

There is no backup plan in the list. The only creatures are Hydroelectric
Specimen (1/4) and, in the sideboard, Tamiyo (1/1 flyer). Combat damage is
modelled, so the deck could technically win by attacking for one over twenty
turns - it cannot win the way the archetype wins.

## Survey outcome

25 distinct names: 9 handled, 13 silent, 3 `no_rules_text`.

### Silent (13) - every one named

`silent` is the only category that is a bug: nothing happened and nothing was
recorded.

| Card | The clause nothing reads |
|---|---|
| **Goblin Charbelcher** | `{3}, {T}: Reveal cards from the top of your library until you reveal a land card. This artifact deals damage equal to the number of nonland cards revealed this way to any target. If the revealed land card was a Mountain, this artifact deals double that damage instead. Put the revealed cards on the bottom of your library in any order.` The whole win condition. |
| **Whir of Invention** | `Search your library for an artifact card with mana value X or less, put it onto the battlefield, then shuffle.` The tutor for Charbelcher. Improvise ignored on top. |
| **Disrupting Shoal** | Both clauses. `Counter target spell if its mana value is X.` is silent, **and** the pitch cost `You may exile a blue card with mana value X from your hand rather than pay this spell's mana cost.` is found as a `PRINTED` `AlternativeCostOption` but `total_cost_for_phrase` returns `None`, so the option is marked unavailable. The X in the exile clause is what defeats it. A 4-of that is completely inert. |
| **Spell Snare** | `Counter target spell with mana value 2.` A conditional counter - plain `Counterspell` is handled, this shape is not. |
| **Stern Scolding** | `Counter target creature spell with power or toughness 2 or less.` Same shape family. |
| **Stock Up** | `Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom of your library in any order.` |
| **Into the Flood Maw** | `Return target creature an opponent controls to its owner's hand. If the gift was promised, instead return target nonland permanent an opponent controls to its owner's hand.` Gift also an ignored keyword. |
| **Tameshi, Reality Architect** | Both abilities. Trigger `Whenever one or more noncreature permanents are returned to hand, draw a card. This ability triggers only once each turn.` and activated `{X}{W}, Return a land you control to its owner's hand: Return target artifact or enchantment card with mana value X or less from your graveyard to the battlefield.` |
| **Sea Gate Restoration** | Spell face only: `Draw cards equal to the number of cards in your hand plus one. You have no maximum hand size for the rest of the game.` Its land back **does** tap for `{U}`. |
| **Suppression Ray** | Spell face only: `Tap all creatures target player controls. You may pay any amount of {E}. ...` Land back taps for `{W}` or `{U}`. |
| **Waterlogged Teachings** | Spell face only: `Search your library for an instant card or a card with flash, reveal it, put it into your hand, then shuffle.` Land back taps for `{U}` or `{B}`. |
| **Hydroelectric Specimen** | Trigger only: `When this creature enters, you may change the target of target instant or sorcery spell with a single target to this creature.` Land back taps for `{U}`. Flash is a keyword and is fine. |
| **Tamiyo, Inquisitive Student** (SB) | Both creature triggers and all three planeswalker loyalty abilities. Investigate also an ignored keyword. |

Note the shape of the last five: those cards are silent **on their spell face
only**. Their land face works. That is the difference between this deck and the
sibling archetype where four lands added no mana - the mana parser handles
"This land enters tapped. / {T}: Add {U}." and "As this land enters, you may pay
3 life. If you don't, it enters tapped. / {T}: Add {U}." without complaint here.

### `no_rules_text` (3) - the three-way audit

`no_rules_text` is **not** coverage: `has_rules_text` skips every static line on
a permanent. Each of the three was hand-audited.

| Card | Bucket | Detail |
|---|---|---|
| **Lotus Bloom** | **static modelled elsewhere** | `Suspend 3—{0}` is a keyword with a real execution path: `src/magic_cards_model/machines/casting.py`, `MarkedExile.suspend` / `finish_suspend` (`sweep_pool --card` names it). `{T}, Sacrifice this artifact: Add three mana of any one color.` is parsed by `machines/abilities.py` into `ManaAbility(any_color=True, any_color_count=3, costs_mana=False)`. Genuinely covered. |
| **Grafdigger's Cage** (SB) | **static unmodelled** | Both lines. `Creature cards in graveyards and libraries can't enter the battlefield.` and `Players can't cast spells from graveyards or libraries.` - zero hits for either phrase, or for the card name, anywhere in `src/magic_cards_model/`. The card does nothing. |
| **Unable to Scream** (SB) | **static unmodelled** | All three lines. `Enchant creature` is a keyword; `Enchanted creature loses all abilities and is a Toy artifact creature with base power and toughness 0/2 in addition to its other types.` is a layer 4/6/7b shape and `_layer_category` returns `None` for it - the layer engine has a `has base power and toughness N/N` regex and a Tishana's-Tidebinder-specific "loses all abilities", but neither reaches this Aura's combined sentence. `As long as enchanted creature is face down, it can't be turned face up.` is also unread. |

Genuinely empty: **0 of 3**. Only 1 of 3 is real coverage.

### Handled (9) - clause by clause

`classify_card` reports the **best** outcome per card, so a dead clause hides
behind a working one. Each handled card was probed per printed clause.

| Card | Clause | Verdict |
|---|---|---|
| Counterspell | `Counter target spell.` | handled |
| Preordain | `Scry 2, then draw a card.` | handled |
| **Consign to Memory** (SB) | `Counter target triggered ability or colorless spell.` | handled |
| | `Replicate {1}` | **DEAD** - ignored keyword. Every copy the deck would make is lost. |
| **Engineered Explosives** (SB) | `{2}, Sacrifice this artifact: Destroy each nonland permanent with mana value equal to the number of charge counters on this artifact.` | handled |
| | `Sunburst` | **DEAD** - ignored keyword. Without it the artifact enters with **zero** charge counters, so the activation only ever destroys mana-value-0 permanents. The "handled" verdict is real but the card is functionally inert - this is exactly the clause-hides-behind-clause case. |
| Force of Negation | `Counter target noncreature spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.` | handled |
| | `If it's not your turn, you may exile a blue card from your hand rather than pay this spell's mana cost.` | **modelled elsewhere** - `machines/casting.py` `use_pitch_cost` / `alternative_costs`; the offer resolves to a real cost and the `requires_not_your_turn` gate is honoured. Names this exact card in its docstring. |
| Mystical Dispute (SB) | `Counter target spell unless its controller pays {3}.` | handled |
| | `This spell costs {2} less to cast if it targets a blue spell.` | **modelled elsewhere** - `Game.cost_reduction_for` / `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE` in `models/game.py`. This is one of the only two shapes that method reads, and this card is one of them. |
| Beyeen Veil // Beyeen Coast | `Creatures your opponents control get -2/-0 until end of turn.` | handled |
| | `{T}: Add {U}.` | handled (mana ability) |
| | `This land enters tapped.` | replacement effect, `machines/replacement.py` subsystem - not an `effects.py` gap |
| Jwari Disruption // Jwari Ruins | `Counter target spell unless its controller pays {1}.` | handled |
| | `{T}: Add {U}.` | handled (mana ability) |
| Sink into Stupor // Soporific Springs | `Return target spell or nonland permanent an opponent controls to its owner's hand.` | handled |
| | `{T}: Add {U}.` | handled (mana ability) |
| | `As this land enters, you may pay 3 life. If you don't, it enters tapped.` | replacement effect subsystem |

Two dead clauses behind a `handled` verdict: **Consign to Memory's Replicate**
and **Engineered Explosives' Sunburst**. Both are ability-word-adjacent keywords
that do surface in the ignored-keyword column here; nothing in this deck hides a
dead clause that the ignored-keyword column would *not* have caught.

### Paragraph-fails-closed check

No card in this list has an "at the beginning of the next end step" rider or any
other delayed-trigger sentence (CR 603.7a), so the Goryo's Vengeance failure
mode does not apply here. Checked every printed face.

### Ignored keywords

| Keyword | Card |
|---|---|
| Improvise | Whir of Invention |
| Replicate | Consign to Memory (SB) |
| Sunburst | Engineered Explosives (SB) |
| Gift | Into the Flood Maw |
| Investigate | Tamiyo, Inquisitive Student (SB) |

Unreadable targeting phrases: **0**.

Suspend and Flash are the two keywords in the list that *do* have execution
paths.

## Archetype-specific checks asked for

- **Do the rituals add mana?** No rituals in the deck. The equivalent - Lotus
  Bloom and the seven MDFC land backs - all add mana correctly.
- **Is there tracking of spells cast this turn?** Yes:
  `Game.spells_cast_this_turn` (`models/game.py`), with a previous-turn
  snapshot. Not that this deck needs it.
- **Does an X-cost or library-count payoff read correctly?** No. Whir of
  Invention's `mana value X or less` search is silent; Disrupting Shoal's X-keyed
  pitch cost cannot be read; Sea Gate Restoration's hand-size-relative draw is
  silent; Tameshi's `{X}{W}` activation is silent. Every X-shaped and
  count-shaped payoff in the deck is dead.
- **Do cost-reduction shapes apply?** `Game.cost_reduction_for` still reads only
  two shapes. Mystical Dispute is one of them, so it works. Nothing else in the
  deck has a cost-reduction sentence.

## Blockers, plainly

The deck loads, shuffles, deals opening hands, plays its lands, and makes mana.
It cannot execute its win condition, cannot tutor for it, and cannot draw into
it. Nine of the thirteen silent cards are counterspells or card selection - this
list is 20 pieces of interaction plus a combo the engine cannot run.
