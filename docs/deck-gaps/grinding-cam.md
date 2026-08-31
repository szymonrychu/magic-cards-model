# Effect gaps: Modern "grinding cam"

The deck is `magic-cards-model-api/decks/grinding_cam.txt` - pilot **AgentP**,
tournament date **2026-08-29**, source deck `videre-58656072`. 60 mainboard, 15
sideboard, 26 distinct printings, all Modern-legal.

Every verdict below was produced by running the **real dispatchers**
(`effect_for`, `trigger_effect_for`, `activated_effect_for`) and, where the
answer mattered, by playing the card through a real `Scenario`. Registry
membership in `machines/effects.py` was never consulted - it does not measure
anything (see `scripts/sweep_pool.py`'s own docstring).

Every CR number in this file was looked up with `knowledge_search` while writing
it. Nothing here changes any code; this is a report.

## Headline

`scripts/survey_cards.py --deck` reports **16 handled, 4 silent, 6
no_rules_text**. That summary is wrong in both directions, and the corrections
matter more than the counts:

- **3 cards do the wrong thing rather than nothing** (Mox Amber, Mox Opal via
  auto-tap, Key to the Side-Door). Two of the three are hiding inside
  `no_rules_text`.
- **2 more cards are silent while reporting `handled`** (Loki, God of Mischief;
  Grinding Station's untap trigger), because `classify_card` reports the best
  outcome per card and asks the effect dispatcher without asking whether the
  trigger ever fires.
- **1 card is a trailing/leading-keyword-line casualty** (Metallic Rebuke), and
  the fix is one regex.

## 1. The false greens - cards that behave *incorrectly*

These are worse than silence. A silent card is a missing feature; these produce
a game state the rules do not allow.

### Mox Amber - produces mana it should not have (surveyed `no_rules_text`)

> `{T}: Add one mana of any color among legendary creatures and planeswalkers you
> control.`

With an empty board except the Mox itself:

```
why_cannot_activate -> None
activate(colour=BLUE)  -> pool floating {U: 1}
mana_from(amber, C) for C in WUBRGC -> every colour accepted, colorless included
auto_pay for Spell Snare off a legend-less Mox Amber -> CAST SUCCEEDED
```

The real card adds nothing at all in that board state, and never adds `{C}`.
`parse_mana_abilities` reads `Add one mana of any color` and discards the
`among legendary creatures and planeswalkers you control` qualifier entirely.
This deck plays 4 Mox Amber and its only legends are Emry, Tamiyo, Loki, Mox
Amber itself, Minamo, Otawara and Urza's Saga - so in the engine every Mox Amber
is a turn-one unconditional lotus. There is no grep hit for "Mox Amber" anywhere
in `src/`.

CR 605.2 is explicit that a mana ability stays a mana ability even when the game
state does not let it produce mana - the engine is not entitled to skip the
check.

### Mox Opal - the auto-tap path bypasses metalcraft (surveyed `no_rules_text`)

> `Metalcraft - {T}: Add one mana of any color. Activate only if you control
> three or more artifacts.`

The **explicit** activation path is correct:

```
why_cannot_activate -> "Mox Opal's activation restriction is not met (CR 602.5b)"
activate(...)       -> ValueError, same message
```

`models/game.py:_ACTIVATE_ONLY_IF_CONTROL` / `_activation_condition_holds` reads
metalcraft properly. But the **cost-payment** path does not consult it:

```
Scenario: alice battlefield=[Mox Opal], hand=[Spell Snare]
cast_onto_stack("Spell Snare", auto=True) -> CAST SUCCEEDED
```

`CostPayment.auto_tap` (`machines/cost.py:2429`) filters candidates by
`free_tap_mana_abilities` - "any cost beyond `{T}`" - and never asks
`why_cannot_activate`. CR 602.5 says a player cannot *begin* to activate a
prohibited ability, and CR 605.3b's "resolves immediately" does not exempt it
from CR 602.5b. So the one card whose restriction the engine already models
correctly is defeated by the convenience path the API takes by default.

This is the more dangerous of the two Moxen bugs precisely because the naive
check (`why_cannot_activate`) passes.

### Key to the Side-Door - the discard cost's name restriction is not enforced

> `{1}, {T}, Discard a legendary card with the same name as a legendary permanent
> you control: Draw two cards.`

```
alice battlefield: Key to the Side-Door, Island, Mox Amber   (no Emry in play)
alice discards: Emry, Lurker of the Loch
-> ALLOWED, two cards drawn
```

The cost parser reads "discard a legendary card" and drops `with the same name as
a legendary permanent you control`. In this deck that turns a narrow,
build-around cost into "discard any legendary card, draw two" - Emry, Tamiyo,
Loki, Minamo, Otawara and Mox Amber are all legendary, so the restriction is
never binding in the engine. 4 copies maindeck.

## 2. Silent cards that report `handled` (`classify_card`'s best-outcome rule)

`classify_card` takes the best outcome anywhere on a card (its docstring cites
CR 608.2n), so a working clause hides a dead one. Audited clause by clause:

### Loki, God of Mischief - never triggers at all

> `Whenever a player or permanent becomes the target of an ability you control,
> draw a card. This ability triggers only once each turn.`

`parse_abilities` gives `event=TriggerEvent.BECOMES_TARGET`, `effect='draw a
card'`, and `trigger_effect_for` returns a real draw effect - so the card
surveys as **handled**. It never fires:

```
alice: Loki + 2x Tormod's Crypt; activate both crypts targeting bob
stack after each activation: ["Tormod's Crypt's activated ability"]
alice hand after both: 0 cards drawn
```

Two independent reasons, both in the engine:

1. `machines/casting.py:2264` is the **only** place a `BECOMES_TARGET` event is
   emitted, and it fires from `Casting` (a spell's announcement) for permanents
   only. An **activated ability** choosing targets emits nothing. Loki's whole
   text is about abilities.
2. `machines/triggers.py:1101` matches `BECOMES_TARGET` only in the
   *self-referential* form: `if not mine or event.subject_id != source.id:
   return False`. Its own comment says so - it was written for ward
   (**CR 702.21a**: "Whenever *this permanent* becomes the target..."). Loki is a
   third-party observer, and a third-party observer can never match.

So the "triggers only once each turn" limiter (**CR 602.5b**-style restriction
text) is moot - there is nothing to limit. 4 copies maindeck; this is the deck's
card-advantage engine.

### Grinding Station - the untap trigger resolves and does nothing

> `Whenever an artifact enters, you may untap this artifact.`

The trigger **does** fire and **does** go on the stack, then resolves inert:

```
Grinding Station tapped, alice casts Tormod's Crypt
stack: ["Grinding Station's triggered ability"]
Grinding Station tapped afterwards: True
```

`trigger_effect_for(name, ENTERS_THE_BATTLEFIELD, 'you may untap this artifact.')`
returns `None`. The `{T}, Sacrifice an artifact: Target player mills three cards.`
half is genuinely handled, which is why the card surveys green. The mill loop
this deck is named for (Grinding Station + a free artifact + Emry recursion)
therefore cannot run - the Station taps once and stays tapped.

### Sewer-veillance Cam - half of one trigger condition is dropped

> `When this artifact enters **or leaves** the battlefield, you may tap or untap
> target creature.`

`parse_abilities` yields a single `TriggeredAbility` with
`event=TriggerEvent.ENTERS_THE_BATTLEFIELD`. The `or leaves the battlefield`
disjunct is silently discarded:

```
alice battlefield: Sewer-veillance Cam; game.destroy(cam)
stack afterwards: []
```

Enters works; leaves does nothing. 4 copies maindeck, and the deck sacrifices
the Cam to Grinding Station on purpose, so the dropped half is the half the deck
actually uses.

### Emry, Lurker of the Loch - one of two abilities is dead

- `When Emry enters, mill four cards.` -> **handled**.
- `{T}: Choose target artifact card in your graveyard. You may cast that card
  this turn.` -> `activated_effect_for` returns `None`. **Silent.** The
  cast-permission grant is the whole point of the card in this list.

### Soul-Guide Lantern - one of three abilities is dead

- ETB `exile target card from a graveyard` -> handled.
- `{1}, {T}, Sacrifice this artifact: Draw a card.` -> handled.
- `{T}, Sacrifice this artifact: Exile each opponent's graveyard.` ->
  `activated_effect_for` returns `None`. **Silent** (the "each opponent's
  graveyard" plural form, as against Tormod's Crypt's "target player's
  graveyard", which is handled).

### Key to the Side-Door - one of two abilities is dead

- `{2}, {T}: Target creature can't be blocked this turn.` -> **silent**.
- `{1}, {T}, Discard ...: Draw two cards.` -> handled, but see the false green
  above.

### Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar - every clause dead

Surveyed `silent`, and the per-clause probe confirms nothing at all works:

| clause | verdict |
|---|---|
| `Whenever Tamiyo attacks, investigate.` | event parsed (`ATTACKS`), effect `None` - and `Investigate` is an ignored keyword |
| `When you draw your third card in a turn, exile Tamiyo, then return her transformed...` | `event is None` - the condition is unreadable, so it never triggers |
| `+2:` attack-tax delayed grant | `None` |
| `-3:` graveyard regrowth | `None` |
| `-7:` draw half your library + emblem | `None` |
| `Flying` | executed (`machines/combat.py`) |

4 copies maindeck. The transform trigger is the one that matters and it is the
one whose condition cannot even be read.

## 3. The keyword-line casualty - Metallic Rebuke

This is the Lorien Revealed bug, in its **leading**-line form, and it is the
cheapest fix in this file.

```
effect_for("Metallic Rebuke",
           "Improvise (...)\nCounter target spell unless its controller pays {3}.")
  -> None
effect_for("Metallic Rebuke",
           "Counter target spell unless its controller pays {3}.")
  -> effect          # parses perfectly on its own
```

Played through the engine, Metallic Rebuke resolves and the countered spell stays
on the stack:

```
alice casts Emry; bob responds with Metallic Rebuke targeting it
Emry zone after Metallic Rebuke resolves: STACK        (CR 701.6a: should be GRAVEYARD)
```

**Why:** `machines/effects.py:_strip_non_effect_preamble` strips keyword lines
from a per-keyword **whitelist** of regexes - `_CONVOKE_LINE_RE`, `_DELVE_LINE_RE`,
`_CREW_LINE_RE`, `_CASCADE_LINE_RE`, `_KICKER_LINE_RE`, `_REPLICATE_LINE_RE`,
`_CYCLING_LINE_RE`, `_FLASHBACK_LINE_RE`, `_STORM_LINE_RE`, and the rest. There
is **no `_IMPROVISE_LINE_RE`**. The reminder text's internal periods are then read
as clause boundaries by `_CLAUSE_SEPARATOR`, and `_parse_mixed_clauses`'
fail-closed-per-clause rule takes the real sentence down with them - exactly the
failure mode that docstring already describes for the keywords that *are* on the
list.

The contrast is the proof: **Consign to Memory** has the identical shape
(`Replicate {1} (...)` then `Counter target triggered ability or colorless
spell.`) and works, because `_REPLICATE_LINE_RE` exists.

Improvise is **CR 702.126a** - "a static ability that functions while the spell
with improvise is on the stack" - and **CR 702.126b** confirms it "isn't an
additional or alternative cost", i.e. it is never a CR 608.2c resolution
instruction. It belongs on the strip list on exactly the reasoning already
written for convoke and delve.

4 copies maindeck.

## 4. Genuinely silent, no keyword-line involved

- **Spell Snare** - `Counter target spell with mana value 2.` The *targeting* is
  read correctly (`illegal target: target spell needs mana value 2, and Emry,
  Lurker of the Loch does not have it`), but resolution does nothing: a legal
  mana-value-2 target stays on the stack. Sideboard, 1 copy.
- **Strix Serenade** - `Counter target artifact, creature, or planeswalker spell.
  Its controller creates a 2/2 blue Bird creature token with flying.` Neither
  half runs; the target survives and no Bird appears. The bare first sentence
  alone also returns `None`, so this is not a two-clause-split casualty - the
  counter clause itself is unread. Sideboard, 1 copy.

## 5. The `no_rules_text` three-way audit

`has_rules_text` skips every static line on a permanent by design, so this
column is **not** coverage. All six, hand-audited:

| card | verdict | where |
|---|---|---|
| **Island** | genuinely empty | reminder-text mana ability only, `parse_mana_abilities` |
| **Mox Opal** | **static modelled, but bypassed** | `models/game.py:341` `_ACTIVATE_ONLY_IF_CONTROL`, `game.py:6218` `_activation_condition_holds` - correct for explicit activation, **defeated by `machines/cost.py:2429` `auto_tap`**. See section 1. |
| **Mox Amber** | **silent, and wrong** | no engine reference anywhere. See section 1. |
| **Pithing Needle** | static modelled elsewhere | `machines/replacement.py:1964` reads "Activated abilities of sources with the chosen name can't be activated unless they're mana abilities"; `models/game.py:411` `_ACTIVATED_ABILITY_LOCK` and `game.py:428` handle the chosen-name antecedent; `models/card_state.py:359` stores the choice |
| **Torpor Orb** | **static unmodelled - silent** | `Creatures entering don't cause abilities to trigger.` No hit anywhere in `src/`. `_layer_category` -> `None`. A real replacement effect (it would switch off Emry's own ETB mill in a mirror) that does nothing. Sideboard, 2 copies. |
| **Harbinger of the Seas** | **static unmodelled - silent** | `Nonbasic lands are Islands.` `machines/layers.py:2472` `_blood_moon` implements exactly this shape - but `LAYER_EFFECTS` keys it by the literal card name `"Blood Moon"` (`layers.py:3007`), and there is no `Harbinger of the Seas` row. `parsed_layer_effects` does not read the sentence either, so `_layer_category` is `None` - not even a `LayerNotice`. Sideboard, 2 copies. |

Two silent cards found here that the survey summary counted as "nothing to
classify": **Torpor Orb** and **Harbinger of the Seas**. Plus the two Moxen,
which are worse than silent.

## 6. Ignored keywords

Four occurrences, four distinct keywords, none with any execution path:

| keyword | card(s) | copies | consequence |
|---|---|---|---|
| **Affinity** (for artifacts) | Emry, Lurker of the Loch | 4 | Emry always costs the full `{2}{U}`. In a deck with 4 Mox Opal, 4 Mox Amber, 4 Mishra's Bauble, 4 Key to the Side-Door and 4 Sewer-veillance Cam, this is the difference between a turn-one and a turn-three Emry. |
| **Improvise** | Metallic Rebuke | 4 | no artifact ever pays for it - on top of the resolution failure in section 3 |
| **Investigate** | Tamiyo, Inquisitive Student | 4 | no Clue token; moot, the trigger's effect is `None` anyway |
| **Replicate** | Consign to Memory | 4 (SB) | no copies; the base counter *does* work |

No grep hit in `src/magic_cards_model` for `affinity`, `replicate`, `investigate`
or `improvise`.

**Ability words never appear in this column** (**CR 207.2c**: an ability word has
no rules meaning), so *Metalcraft* on Mox Opal and *Channel* on Otawara are
correctly absent from it - and their absence says nothing about whether the
abilities beneath them work. Mox Opal's does not (section 1); Otawara's does
(section 7).

## 7. What genuinely works

Confirmed by the dispatchers, not assumed:

- **Urza's Saga** - all three chapters handled, and each has real machinery
  behind it: chapter I's granted mana ability (`card_state.py:718`,
  `cost.py:2397`), chapter II's granted token-maker (`triggers.py:1896`,
  `game.py:6008`) including the Construct token's own "gets +1/+1 for each
  artifact you control" CDA (`layers.py:1124`, `layers.py:1340`), and chapter
  III's "artifact card with mana cost {0} or {1}" search (`effects.py:2388`,
  `effects.py:2559`). The deck's best card is the deck's best-covered card.
- **Otawara, Soaring City** - channel handled, **and the cost reduction is real**:
  with two legendary creatures out, `activation_cost` returns `{1}{U}, Discard
  this card` off a printed `{3}{U}`. Not a false green.
- **Sink into Stupor // Soporific Springs** - the instant face's bounce is
  handled through `_spell_faces`' modal-DFC path, and the land face's "you may
  pay 3 life, else it enters tapped" is `machines/replacement.py:2103`.
- **Force of Negation** - both the counter-then-exile redirect
  (`game.py:4585`, `effects.py:9048`) and the CR 118.9 pitch alternative cost
  (`cost.py:1628`/`1658`, `casting.py:840`/`1341`/`1591`) are modelled, with
  scenario coverage in `test_counterspells.py` and `test_alternative_costs.py`.
  It returns `[]` from `keyword_cast_options` because the pitch cost is not a
  keyword cast option - that is correct, not a gap.
- **Consign to Memory**, **Dismember**, **Aether Spellbomb** (both abilities),
  **Tormod's Crypt**, **Mishra's Bauble**, **Minamo**, **Emry's ETB mill**,
  **Sewer-veillance Cam's ETB half and draw-two**, **Grinding Station's mill
  activation**, **Soul-Guide Lantern's ETB and draw**.

## 8. Paragraph-fails-closed / delayed-trigger riders

**CR 603.7c** delayed triggered abilities: the deck has exactly one rider,
**Mishra's Bauble**'s `Draw a card at the beginning of the next turn's upkeep.`
It is **not** a casualty - the activated dispatcher handles the whole ability:

```
ACT[0] "{T}, Sacrifice this artifact: Look at the top card of target player's
        library. Draw a card at the beginning of the next turn's upkeep."
  -> handled
```

The `delayed_notice_only` the probe shows for Mishra's Bauble is on the
**spell-level** dispatch, which is irrelevant: Bauble is an artifact, and
`effect_for` returning anything at all for a permanent spell is never consulted
by `Game`. No Goryo's-Vengeance-shaped failure in this list.

## 9. Targeting

`scripts/survey_cards.py` reports **0 unreadable targeting phrases** across all
26 cards. Spot-confirmed the hard one: Spell Snare's `target spell with mana
value 2` is enforced at announcement even though its resolution is silent.

## Priority order, if any of this is implemented later

1. **Mox Amber's colour restriction** and **`auto_tap` consulting
   `why_cannot_activate`** - 8 maindeck cards producing illegal mana is the
   single largest correctness hole, and it makes every other result in this deck
   untrustworthy.
2. **`_IMPROVISE_LINE_RE` in `_strip_non_effect_preamble`** - one regex, follows
   an existing pattern exactly, fixes 4 maindeck counterspells.
3. **`BECOMES_TARGET` emitted for activated/triggered abilities, and matched in
   the non-self-referential form** - unlocks Loki, the deck's engine.
4. **Grinding Station's untap trigger** and **Emry's cast-permission ability** -
   the deck's namesake loop.
5. **Key to the Side-Door's discard-cost name restriction.**
6. Torpor Orb, Harbinger of the Seas, Tamiyo's transform trigger, Sewer-veillance
   Cam's leaves half, Spell Snare, Strix Serenade.

## CR numbers cited, all verified with `knowledge_search` in the session that
wrote this file

100.2a, 100.4a, 103.5, 103.8a, 207.2c, 402.1, 602.5, 602.5b, 603.7c, 605.2,
605.3b, 608.2n, 701.6a, 702.21a, 702.126a, 702.126b.

`knowledge_search` returned nothing for a "grinding cam" archetype rules entry,
which is expected - it is a metagame name, not a rules term.
