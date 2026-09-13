# Effect gaps: Modern uw control (1.0% of the metagame)

**List**: eclipse4343, uw control, tournament 2026-08-23, source deck
`videre-58651065`, pulled with
`statistics_decks(format="modern", archetype_name="uw control", date_from="2026-06-01", include_cards="full", limit=5)`.
Registered as 28 mainboard rows summing to 60 with no repeated row, and 7
sideboard rows summing to 15. Nothing was merged, nothing was repaired.

**Legality**: all 33 distinct names checked with
`resolve_cards(format="modern", fields="legality")` in two batches of 17 and
16. **Row count matched the names sent both times** (17 -> 17, 16 -> 16),
`not_found: []` in both, and every row came back `legal: true`. No
double-faced card is in this list, so trap 1 had nothing to drop here - the
count assertion was still made rather than trusting the empty `not_found`.

**Decklist**: `magic-cards-model-api/decks/uw_control.txt`.
**Smoke test**: `tests/scenarios/test_uw_control_deck.py`.

Every CR number below was looked up with `knowledge_search(type="rules")` in
the session that wrote this file. Nothing here is quoted from memory.

## How this was measured

`scripts/survey_cards.py --deck` - the production classifier
(`scripts/sweep_pool.classify_card`, the same dispatchers `models/game.py`
calls) - over all 33 distinct names. `EFFECTS` membership was not consulted:
it is not a coverage signal, and this deck would look empty by it.

Because `classify_card` reports the **best** outcome on a card, a second pass
re-ran the same dispatchers clause by clause and printed **every** outcome, so
a dead clause sitting behind a working one is visible. That pass is what
sections 3 and 4 are built from.

Headline counts, 33 cards:

| Bucket | Count |
|---|---|
| handled | 21 |
| silent | 6 |
| no_rules_text | 6 |
| notice | 0 |

Zero notices is itself worth saying: nothing in this deck fails closed. Where
the engine cannot read a line here, it does nothing and records nothing.

## 1. Silent cards, grouped by mechanic

Six cards where nothing on the card produced any effect at all.

### Counterspells with a filter on what they may counter

- **Spell Snare** - "Counter target spell with mana value 2."
  Missing primitive: **counter restricted by the target spell's mana value**.
  `machines/targeting.py` can already read "mana value N" as a target
  restriction on a permanent (`targeting.py:281`), but no counter effect
  consumes it, so the whole spell resolves and does nothing. CR 202.3 defines
  mana value; CR 701.6a defines countering. This confirms the sibling
  finding on Spell Snare independently.

Sibling agents also reported Spell Pierce and Stern Scolding silent for the
"unless its controller pays {N}" and colour/type-filtered variants. Neither
card is in this list, so this deck neither confirms nor contradicts them. The
one card here in that family that **does** work is Mystical Dispute
("Counter target spell unless its controller pays {3}." - handled), so the
"unless its controller pays" primitive exists; whatever is missing on Spell
Pierce is not that clause in general.

### Library selection that puts the rest back in a *random* order

- **Narset, Parter of Veils** - "−2: Look at the top four cards of your
  library. You may reveal a noncreature, nonland card from among them and put
  it into your hand. Put the rest on the bottom of your library in a random
  order."
- **Monumental Henge** - "{2}{W}{W}, {T}: Look at the top five cards of your
  library. You may reveal a historic card from among them and put it into
  your hand. Put the rest on the bottom of your library in a random order."

Both are exactly the four-clause "look at the top N, reveal one, rest to the
bottom" family that `machines/effects.py:12760`
(`_merge_look_top_reveal_to_hand_clauses`) already reads. The one thing that
stops them is the last clause: `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`
(`effects.py:12755`) matches only "**in any order**". "In a random order" is a
different phrase and falls off the end of the merge, so the whole run is
rejected and the ability is silent.

Missing primitive: **"put the rest on the bottom of your library in a random
order"** as an accepted tail of that family. This is a one-phrase gap
producing two dead cards, and it is the closest thing to free coverage in
this deck.

(Consult the Star Charts prints the same "random order" tail and is
nevertheless handled - it is read by a *different*, kicker-aware parser at
`effects.py:16105`, not by the family above. So the family really is the
thing that is narrow, not the phrase being unreadable everywhere.)

### Symmetrical wheel plus "end the turn"

- **Day's Undoing** - "Each player shuffles their hand and graveyard into
  their library, then draws seven cards. If it's your turn, end the turn."
  Missing primitives: the symmetrical **shuffle-hand-and-graveyard-in then
  draw seven**, and **"end the turn"** - `grep` finds no "end the turn"
  handling anywhere in `src/`. The second half is the harder one: it exiles
  everything from the stack, skips the rest of the turn's steps, and performs
  cleanup, which the turn machine has no entry point for.

### Symmetrical draw-then-discard

- **Geier Reach Sanitarium** - "{2}, {T}: Each player draws a card, then
  discards a card."
  Missing primitive: **"each player draws a card, then discards a card"** as
  one symmetric per-player sequence. No occurrence of that phrase anywhere in
  `src/`. Note the land's mana ability (`{T}: Add {C}`) *is* read - only the
  second, non-mana activated ability is dead.

### Animating a land

- **Hall of Storm Giants** - "{5}{U}: Until end of turn, this land becomes a
  7/7 blue Giant creature with ward {3}. It's still a land."
  Missing primitive: **"this land becomes an N/N creature ... it's still a
  land" as a one-turn continuous effect**. This wants CR 613.1d (layer 4,
  type-changing), CR 613.4b (layer 7b, setting base power/toughness) and CR
  613.1f (layer 6, adding the ward ability), created by the resolution of an
  activated ability (CR 611.2). Ward itself (CR 702.21a) would then need to
  trigger on the animated land. The manland's own "enters tapped" clause is
  read correctly (see section 2); only the activation is dead.

### Nothing on the card at all

- **Kaheera, the Orphanguard** - see section 2. It is bucketed
  `no_rules_text`, which is the interesting part.

## 2. `no_rules_text`, audited three ways

`sweep_pool.has_rules_text` returns False for six cards here. It skips static
lines on permanents, so this bucket is **not** coverage. Every one was
hand-audited against `machines/replacement.py` and `machines/layers.py`.

### Genuinely empty (nothing to model)

| Card | Why |
|---|---|
| **Plains** | Basic land. Only reminder text, "({T}: Add {W}.)". |
| **Island** | Basic land. Only reminder text, "({T}: Add {U}.)". |
| **Mystic Gate** | Two mana abilities and nothing else: "{T}: Add {C}." and "{W/U}, {T}: Add {W}{W}, {W}{U}, or {U}{U}." Both are read by `parse_mana_abilities`; a mana ability never uses the stack, so there is nothing for the effect dispatchers to own. |

### Static modelled elsewhere (named file and line)

| Card | Static line | Where it is modelled |
|---|---|---|
| **Hallowed Fountain** | "As this land enters, you may pay 2 life. If you don't, it enters tapped." | `machines/replacement.py` - parses as two effects, `AS_ENTERS` (optional, `_try_as_enters`, line 691) plus `ENTERS_TAPPED` with condition "you don't" (`_try_enters_tapped`, line 731); the shockland pair is named explicitly at `replacement.py:1886-1906` (`_PAY_LIFE_CHOICE`). CR 614.1c, CR 614.12, CR 614.12a. |
| **Watery Grave** | Same line. | Same, parsed identically. |

Both come back `parsed=True` on both halves, so these two are genuinely
covered - not merely quiet.

### Static unmodelled (a real gap hiding in this bucket)

| Card | Static line | State |
|---|---|---|
| **Kaheera, the Orphanguard** | "Each other creature you control that's a Cat, Elemental, Nightmare, Dinosaur, or Beast gets +1/+1 and has vigilance." | **Not modelled at all.** `LAYER_EFFECTS` has no row; `parsed_layer_effects` returns nothing; `looks_like_unparsed_layer_effect(static_only=True)` returns False, so it does not even register as a near-miss and produces no `LayerNotice`. A CR 611.3 / CR 613.4c anthem plus a CR 613.1f keyword grant, both silently absent. |
| **Kaheera, the Orphanguard** | "Companion - Each creature card in your starting deck is a Cat, Elemental, Nightmare, Dinosaur, or Beast card." | **Not modelled at all.** `grep -i companion` over `src/` finds nothing. CR 702.139a (the outside-the-game keyword), CR 103.2b (revealing it before the game), CR 116.2g (the {3} special action to put it in hand) are all absent, and `Companion` is one of the three ignored keywords below. Note this list's own creature suite is Solitude (Elemental) and Kaheera itself, so the deck really is companion-legal - the engine simply has no notion of it. |

So the honest split of the six is **3 genuinely empty, 2 modelled elsewhere,
1 (Kaheera) carrying two unmodelled statics**. Reading `no_rules_text` as
"clean" would have hidden both of Kaheera's lines.

## 3. Cards reporting `handled` with a dead clause behind it

`classify_card` returns the best outcome per card, so these all look fine in
the summary. Clause-by-clause, they are not.

### Supreme Verdict - `handled`

- "Destroy all creatures." - **handled**.
- "This spell can't be countered." - **dead**.
  `_CANT_BE_COUNTERED_LINE_RE` (`machines/effects.py:3271`) is applied at
  `effects.py:3576` purely to *strip* the line so the destroy clause parses.
  Nothing then enforces it: `grep` for `cant_be_countered` /
  `uncounterable` / `can_be_countered` over `src/` finds only a comment in
  `replacement.py:1973`. CR 113.6g says the ability functions on the stack;
  in this engine Counterspell would happily counter Supreme Verdict. This is
  the whole reason the card is in a deck that also plays Wrath of the Skies.

### The Wandering Emperor - `handled`

- "−1: Create a 2/2 white Samurai creature token with vigilance." -
  **handled**.
- "−2: Exile target tapped creature. You gain 2 life." - **handled**.
- "+1: Put a +1/+1 counter on up to one target creature. It gains first
  strike until end of turn." - **dead** (silent). The "up to one target"
  form plus the anaphoric "It gains ..." tail is not read; the closest
  existing reader, `layers.py:2927`, handles "**Target** creature gets +1/+0
  and gains first strike until end of turn", a different shape.
- "As long as The Wandering Emperor entered this turn, you may activate her
  loyalty abilities any time you could cast an instant." - **dead**. No
  handling anywhere (`grep "loyalty abilities any time"` over `src/`: no
  hits). CR 606.3 / CR 306.5d set the default (main phase, empty stack, one
  per turn); this static is the exception to it, and the exception does not
  exist here. The card is played specifically for the flash-speed activation.

### Isochron Scepter - `handled`

- "Imprint - When this artifact enters, you may exile an instant card with
  mana value 2 or less from your hand." - **handled** (trigger).
- "{2}, {T}: You may copy the exiled card. If you do, you may cast the copy
  without paying its mana cost." - **handled**. The copy is cast through
  `Game.may_cast_during_resolution` (CR 707.12, CR 608.2g), which announces
  its targets and offers its kicker (CR 601.2b).

### High Noon - `handled`

- "{4}{R}, Sacrifice this enchantment: It deals 5 damage to any target." -
  **handled**. This is the mode nobody sideboards it for (the deck cannot
  even produce {R}).
- "Each player can't cast more than one spell each turn." - **dead**. The
  data it needs already exists - `Game.spells_cast_this_turn`
  (`models/game.py:970`) - but no static reads it as a casting restriction.
  Missing primitive: **a symmetric per-turn spell-count restriction**, CR
  101.2 ("can't" takes precedence over "may"). `machines/casting_restrictions.py`
  is the right home; it already carries Teferi's and Orim's Chant's
  restrictions.

### Prismatic Ending - `handled` (with an unread target restriction)

- "Converge - Exile target nonland permanent if its mana value is less than
  or equal to the number of colors of mana spent to cast this spell." - the
  **effect** is handled, by `_parse_converge_exile_by_colors_spent`
  (`effects.py:8520`, `_CONVERGE_EXILE_RE` at `effects.py:8727`).
- The **targeting** half is not: `survey_cards` reports "unreadable
  targeting" for this exact phrase, and `machines/targeting.py:1960` names it
  in its own comment. `profile_for_text` returns `understood=False`, so CR
  115 target legality is never checked for this spell. Choosing an illegal
  target would not be caught.
- `Converge` is also reported as an ignored keyword (see section 5). That is
  cosmetic - converge is an ability word with no rules meaning of its own
  (CR 207.2c) - but note that ability words never appear in the ignored
  column at all, so the column is not what caught the converge condition;
  the clause-by-clause pass is.

### Consult the Star Charts - `handled` (with an unparsed replacement echo)

- "Look at the top X cards of your library, where X is the number of lands
  you control. Put one of those cards into your hand. If this spell was
  kicked, put two of those cards into your hand instead. Put the rest on the
  bottom of your library in a random order." - **handled**, and the kicked
  branch really is read (`effects.py:16105`).
- `machines/replacement.py` separately reports the "If this spell was
  kicked, put two of those cards into your hand instead." sentence as
  `UNPARSED`. This one is a false alarm rather than a gap: the sentence is
  CR 702.33d kicker bookkeeping ("that spell has been kicked") inside the spell's own effect, not a CR 614
  replacement effect, and the effect parser that owns it does read it.
  Recorded here so the next audit does not chase it.

### Cards that report `handled` and really are clean, clause for clause

Checked and found with no dead clause: Counterspell, Mystical Dispute (the
"costs {2} less if it targets a blue spell" static is read at
`models/game.py:234` and `machines/targeting.py:1018`), Consign to Memory
(counter clause handled; only `Replicate` is ignored), Orim's Chant (both
halves, including "if this spell was kicked, creatures can't attack this
turn" at `effects.py:4987`), Solitude (ETB handled, evoke read by
`machines/casting.keyword_cast_options`, flash and lifelink read by the
timing and combat machines), Teferi, Time Raveler (both loyalty abilities
handled, and the "each opponent can cast spells only any time they could
cast a sorcery" static is modelled at
`machines/casting_restrictions.py:222` and `machines/casting.py:747`), Rest
in Peace (ETB handled, and the graveyard-exile static is executed through
`_compile_graveyard_exile` at `machines/replacement.py:1415` rather than a
registry row), Wrath of the Skies (handled at both probed X values), March of
Otherworldly Light (effect handled, and its additional cost is read by
`machines/cost.py:1623`), Supreme Verdict's destroy half, Arid Mesa, Flooded
Strand and Scalding Tarn (fetch activations handled), Thundering Falls and
Meticulous Archive (surveil trigger handled, "this land enters tapped" parsed
as `ENTERS_TAPPED`), Tune the Narrative, Isochron Scepter's imprint trigger.

## 4. Replacement effects on lands, confirmed working

Not a gap, recorded because it is where trap 2 would otherwise bite again -
all of these are static lines on permanents:

| Card | Line | Parsed as |
|---|---|---|
| Hallowed Fountain, Watery Grave | "As this land enters, you may pay 2 life. If you don't, it enters tapped." | `AS_ENTERS` (optional) + `ENTERS_TAPPED` (condition "you don't") |
| Monumental Henge | "This land enters tapped unless you control a Plains." | `ENTERS_TAPPED` (condition "unless you control a Plains") |
| Hall of Storm Giants | "If you control two or more other lands, this land enters tapped." | `ENTERS_TAPPED` (condition "you control two or more other lands") |
| Thundering Falls, Meticulous Archive | "This land enters tapped." | `ENTERS_TAPPED` |
| Rest in Peace | "If a card or token would be put into a graveyard from anywhere, exile it instead." | `IF_WOULD_INSTEAD`, executed via `_compile_graveyard_exile` |

CR 614.1c for the "as ... enters" / "enters tapped" family, CR 614.12 and
CR 614.12a for choices made before the permanent enters.

## 5. Keywords with no execution path

Three occurrences across three cards:

| Keyword | Card | Consequence |
|---|---|---|
| `Converge` | Prismatic Ending | Cosmetic. Converge is an ability word (CR 207.2c) with no rules meaning; the condition it labels *is* executed. |
| `Replicate` | Consign to Memory | **Real.** CR 702.56a: a static ability letting you pay an additional cost as you cast, plus a triggered ability that copies the spell that many times. Neither exists, so the four sideboard copies can only ever counter one thing. |
| `Companion` | Kaheera, the Orphanguard | **Real.** CR 702.139a, CR 103.2b, CR 116.2g - see section 2. |

Ability words never reach this column at all (`sweep_pool.ABILITY_WORDS`
filters them), so this table can never be the thing that finds a dead
ability-word clause. That is what section 3 is for.

## 6. Unreadable targeting text

One phrase, on one card:

- Prismatic Ending: "Converge - Exile target nonland permanent if its mana
  value is less than or equal to the number of colors of mana spent to cast
  this spell." `machines/targeting.py` returns `understood=False`, so CR 115.1
  legality is not checked for this spell at all.

## 7. What to build first, if anyone is picking

Ordered by dead cards per unit of work, not by importance:

1. Accept "put the rest on the bottom of your library in **a random order**"
   in `_merge_look_top_reveal_to_hand_clauses`. One phrase, two silent cards
   (Narset, Monumental Henge), four copies of one of them.
2. Counter-with-a-mana-value-filter (Spell Snare, two copies here, and the
   same primitive several siblings are blocked on).
3. Enforce "this spell can't be countered" (CR 113.6g) - the data is already
   stripped out of the text, it just goes nowhere.
4. A symmetric per-turn spell-count restriction for High Noon, on top of
   `Game.spells_cast_this_turn`, in `machines/casting_restrictions.py`.
5. Isochron Scepter's copy-the-imprinted-card activation (CR 112.1b).
6. The Wandering Emperor's instant-speed-loyalty static (the exception to
   CR 606.3) and its +1.
7. Land animation with a layer 4 + 7b + 6 continuous effect for Hall of
   Storm Giants.
8. Replicate (CR 702.56a) and Companion (CR 702.139a / 116.2g) as keywords.
9. "End the turn" and the symmetric wheel, for Day's Undoing - the largest
   piece of work here and only one copy in the list.

Nothing in this document was implemented. `machines/effects.py` was not
edited.

## CR numbers verified for this document

All looked up with `knowledge_search(type="rules")` in this session:
100.2a, 100.4a, 101.2, 103.2a, 103.2b, 103.3, 103.5, 112.1b, 113.6g,
116.2g, 202.3, 207.2c, 306.5d, 400.11a, 606.3, 611.2,
611.3, 613.1d, 613.1f, 613.4b, 613.4c, 614.1c, 614.12, 614.12a, 701.6a,
702.21a, 702.56a, 702.139a.
