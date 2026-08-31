# Jeskai aggro - effect-gap report

The deck: pilot **_Falcon_**, tournament date **2026-08-28**, source deck
`videre-58655057`, pulled with `statistics_decks(format="modern",
archetype_name="jeskai aggro", date_from="2026-06-01", include_cards="full")`.
1.0% of the current Modern metagame. The registered 75 lives at
`decks/jeskai_aggro.txt` in the API repo and again, as literal dicts, in
`tests/scenarios/test_jeskai_aggro_deck.py`.

**Legality.** `resolve_cards(names=[34 names], format="modern",
fields="legality")` returned **33 rows for 34 names sent**, with
`not_found: []`. The dropped row was the DFC, `Ajani, Nacatl Pariah`; re-sent
alone under its full `Ajani, Nacatl Pariah // Ajani, Nacatl Avenger` name it
came back legal. All 34 are Modern-legal.

**How this was measured.** `uv run python scripts/survey_cards.py --deck
decks/jeskai_aggro.txt` - the production classifier (`scripts/sweep_pool.
classify_card`), not `EFFECTS` membership, which is empty by design for most of
this pool. `classify_card` reports the *best* outcome per card, so every card
it called `handled` was then re-probed clause by clause through the same three
production dispatchers (`effect_for`, `trigger_effect_for`,
`activated_effect_for`) with `classify_card`'s own arguments, and every
`no_rules_text` card was hand-audited against `parse_replacement_effects`,
`executed_keywords` and a grep of the owning subsystem. Where a `None` from
`effect_for` is the *correct* answer - a land (played as a special action,
never cast), a permanent spell whose text is all triggers and statics, a mana
ability - it is not counted as a gap.

## Headline numbers

| bucket | count |
|---|---|
| handled | 24 |
| silent | 2 |
| no rules text | 8 |
| **total** | **34** |
| ignored-keyword occurrences | 2 (one of them a measurement artifact) |
| unreadable targeting phrases | 1 |

The two silent cards are both counterspells, and both are real gaps. The eight
`no_rules_text` cards split 2 / 4 / 2 (see below). Four `handled` cards carry a
dead clause behind a working one.

## Silent cards - nothing happens, nothing is recorded

### Counterspells with a qualifier the counter parsers refuse

`machines/effects.py` reads exactly three counter shapes:
`_COUNTER_TARGET_SPELL_RE` ("Counter target `<one qualifier word>` spell." with
a trailing `$`), `_COUNTER_UNLESS_PAYS_RE` ("Counter target spell unless its
controller pays {N}." - **no qualifier slot at all**), and
`_COUNTER_TARGET_ABILITY_OR_SPELL_RE` (the "ability or spell" compound). A
qualifier the first regex's word list does not contain, or any qualifier on the
second, falls straight through to `None`, with no notice.

| card | oracle text | why it is silent | missing primitive |
|---|---|---|---|
| **Spell Snare** | `Counter target spell with mana value 2.` | "with mana value 2" is a *numeric* restriction, not one of `_SPELL_QUALIFIER_WORD`'s type/colour words, and `_COUNTER_TARGET_SPELL_RE`'s trailing `$` refuses the tail rather than dropping it | a counter restricted by the target's mana value on the stack (CR 202.3e's real on-stack value, the same one the Chalice of the Void row already computes) |
| **Flusterstorm** | `Counter target instant or sorcery spell unless its controller pays {1}.` | `_COUNTER_UNLESS_PAYS_RE` matches only the bare "Counter target spell unless its controller pays {N}." - the "instant or sorcery" qualifier makes it miss, and nothing else reaches it | a qualifier slot on the counter-unless-pays shape (CR 118.12a) |

Both confirmed independently here; sibling agents reported the same two on other
decks. `Stern Scolding` and `Spell Pierce` are not in this 75.

Flusterstorm is the more interesting of the two, because it is **half alive**:
*storm* itself is executed (`machines/keywords.py`, CR 702.40a), so the spell
correctly puts N copies on the stack - and then every copy, and the original,
resolve doing nothing. A card that visibly works right up to the point where it
matters.

## `no_rules_text` is not coverage - the three-way audit

`sweep_pool.has_rules_text` skips every static line on a permanent, so an
unmodelled static lands in `no_rules_text` looking clean. All eight, audited by
hand:

### Genuinely empty (2)

| card | why |
|---|---|
| **Mountain** | basic land, CR 305.6's intrinsic mana ability only |
| **Plains** | same |

### Static modelled elsewhere (4)

| card | line | who owns it |
|---|---|---|
| **Hallowed Fountain** | `As this land enters, you may pay 2 life. If you don't, it enters tapped.` | `machines/replacement.py` - `parse_replacement_effects` returns `ReplacementKind.AS_ENTERS` (`optional=True`, `replacement="you may pay 2 life"`) plus `ReplacementKind.ENTERS_TAPPED` (`condition="you don't"`); the shockland pair is called out at `replacement.py:1886-1889` and `replacement.py:2103` |
| **Sacred Foundry** | same line | same, verified by the same probe |
| **Steam Vents** | same line | same, verified by the same probe |
| **Arena of Glory** | `This land enters tapped unless you control a Mountain.` | `machines/replacement.py` - `ReplacementKind.ENTERS_TAPPED` with `condition="unless you control a Mountain"`. CR 614.1d is the rule for a bare "[This permanent] enters ..." line; the repo's own comment at `replacement.py:141` cites CR 614.1c, which is the neighbouring "As [this permanent] enters" / "enters with" form that the shocklands above use. **But see the exert rider below** - this card is only half owned |

### Static unmodelled (2)

| card | oracle text | what the engine does with it | missing primitive |
|---|---|---|---|
| **Grafdigger's Cage** (SB) | `Creature cards in graveyards and libraries can't enter the battlefield.` / `Players can't cast spells from graveyards or libraries.` | nothing at all. `parse_replacement_effects` returns `[]`; nothing in `machines/casting_restrictions.py` scans for it; grep for "can't enter the battlefield" finds only an unrelated token comment. The card is an inert {1} artifact | (a) a zone-scoped prohibition on entering the battlefield, and (b) a zone-scoped cast prohibition. `casting_restrictions.py` models restrictions keyed to *players* ("your opponents can't cast noncreature spells") and to timing; it has no shape for "from `<zone>`", which is what would also gate `keyword_cast_options`' flashback/warp/dredge grants |
| **Voice of Victory** | `Your opponents can't cast spells during your turn.` | nothing. Its *mobilize 2* half is executed (`machines/keywords.py`), which is why the card looks fine, but the static that makes it a Modern staple does not exist. `casting_restrictions.py` has exactly one blanket-prohibition shape, `_NONCREATURE_CAST_RESTRICTION_RE`, anchored to Ranger-Captain of Eos's literal sentence, plus Orim's Chant's targeted one; neither reads "during your turn" | a **live static** (re-read off the battlefield, CR 604.2 / 611.3a, the way `sorcery_speed_restriction_source` already does for Teferi) combining "your opponents", "can't cast spells" (all spells, not just noncreature) and a turn-ownership window |

The Voice of Victory gap is the single biggest one in this deck: three copies
maindeck of a card whose defining ability is absent.

## Clause-by-clause audit of cards reporting `handled`

`classify_card` returns the best outcome anywhere on a card, so a dead clause
hides behind a live one. Every `handled` card was re-probed per clause.

### Dead clauses hiding behind working ones (4 cards)

| card | live clause (why it reads `handled`) | dead clause | missing primitive |
|---|---|---|---|
| **Thraben Charm** | mode 2, `Destroy target enchantment.`, is the *only* readable mode - `_modal_category` returns `handled` if **any** mode parses | mode 1 `Thraben Charm deals damage equal to twice the number of creatures you control to target creature.` and mode 3 `Exile any number of target players' graveyards.` both return `None` from `parse_mode_effect`. Choosing either leaves a `ModeNotice` and does nothing | (a) a *doubled* count expression as damage magnitude ("twice the number of creatures you control"); (b) an unbounded plural player target ("any number of target players' graveyards") |
| **Quantum Riddler** | `When this creature enters, draw a card.` - a clean ETB trigger | `As long as you have one or fewer cards in hand, if you would draw one or more cards, you draw that many cards plus one instead.` parses to `ReplacementKind.UNPARSED` - recognised as a replacement effect, then dropped | a conditional draw-replacement (CR 614): a hand-size condition gating a "draw N, draw N+1 instead" substitution. `replacement.py` reads only Dredge-shaped and draw-step-scoped draw replacements |
| **Obsidian Charmaw** (SB) | `When this creature enters, destroy target nonbasic land an opponent controls.` | `This spell costs {1} less to cast for each land your opponents control that could produce {C}.` `Game.cost_reduction_for` matches exactly two regexes - `_COSTS_LESS_PER_CARD_TYPE` (Emrakul's graveyard card types) and `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE` (Mystical Dispute). Neither fits; the dragon is always cast at full {3}{R}{R} | a CR 601.2f self-reduction counting a *board* quantity ("for each land your opponents control that could produce {C}"), which also needs "could produce `<mana symbol>`" as a queryable property of a land |
| **Arena of Glory** | `This land enters tapped unless you control a Mountain.` (replacement) and `{T}: Add {R}.` (mana ability) | `{R}, {T}, Exert this land: Add {R}{R}. **If that mana is spent on a creature spell, it gains haste until end of turn.**` The rider is recognised by `_SPEND_EFFECT_ON_SPELL` in `machines/abilities.py:206` specifically so it does **not** make `why_cannot_activate` refuse the whole ability - the mana is minted and the haste grant is silently dropped | CR 106.6's "additional effect that affects the spell the mana is spent on" - mana that carries a rider to its point of spend. Already a documented gap ("mana spend restrictions" row in `docs/engine-coverage.md`) |

### Clauses checked and found genuinely live

Worth recording, because each was a plausible candidate for a hidden dead
clause and is not one:

- **Ocelot Pride** - both sentences of the end-step trigger run, including the
  city's-blessing token-copy half; *ascend* is a real per-player designation
  (`Player.has_citys_blessing`). `docs/engine-coverage.md` records that this
  card used to half-execute and no longer does.
- **Guide of Souls** - both triggers. The second is CR 603.12's reflexive
  ("you may pay {E}{E}{E}. When you do, ...") and is wired through
  `_parse_reflexive_pay_energy_clause`; the flying counter is a real keyword
  counter and the Angel type change is a layer-4 effect.
- **Ajani, Nacatl Pariah // Ajani, Nacatl Avenger** - both front-face triggers
  and all three back-face loyalty abilities dispatch to real effects, including
  the `0`'s nested reflexive trigger.
- **Dalkovan Encampment** - see the delayed-trigger section below.
- **Solitude**, **Starfield Shepherd**, **Ragavan** - ETB / combat-damage
  triggers all live; the `silent` reading on their top-level *spell* dispatch is
  the correct answer for a permanent spell, not a gap.
- **Prismatic Ending** (SB) - `_parse_converge_exile_by_colors_spent` really
  does read the colours-spent ceiling. Its *targeting* is the problem, below.

## Paragraph-fails-closed casualties: none

An ability paragraph resolves whole or fails closed, so a card whose last
sentence is an unbuildable delayed triggered ability (CR 603.7a) can have its
*first* sentence silently never execute either - the Goryo's Vengeance shape.
Every card in this 75 carrying an "at the beginning of the next end step" rider
was checked:

| card | the rider | verdict |
|---|---|---|
| **Dalkovan Encampment** | `{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking. Sacrifice them at the beginning of the next end step.` | **alive, whole.** `_parse_attack_this_turn_create_tapped_attacking_tokens` (`effects.py:10523`) builds the outer delayed trigger (CR 603.7a) *and* a per-token `DELAYED_EFFECTS["sacrifice"]` trigger for the end step. CR 603.7b's "this turn" duration is bounded by `expires_end_of_turn` |
| **Voice of Victory** | mobilize 2's reminder text carries the same "Sacrifice them at the beginning of the next end step" | **alive.** Mobilize is written out by `machines/keywords.py:327-337` and executed there; the sacrifice is not parsed off reminder text (CR 207.2a) at all |
| **Ragavan, Nimble Pilferer** | dash's reminder text, "returned ... at the beginning of the next end step" | **alive.** Dash is a `keyword_cast_options` cast mode; `tests/scenarios/test_dash.py` covers the delayed return |
| **Starfield Shepherd**, **Quantum Riddler** | warp's reminder text, "Exile this creature at the beginning of the next end step" | **alive.** Warp is a `keyword_cast_options` cast mode; `machines/delayed.py:287` is its exile |

No card in this deck is dead from a fails-closed paragraph.

## Ignored keywords

`ignored_keywords` reports two occurrences across the 75. One is real:

| keyword | card | status |
|---|---|---|
| **Replicate** (CR 702.56a) | Consign to Memory (SB) | **real gap.** Nothing in `machines/casting.py` charges the additional cost, and nothing copies the spell per payment. The counter half of the card works; the replicate half does not exist. Already on `docs/engine-coverage.md`'s ignored-keyword list |
| **Converge** | Prismatic Ending (SB) | **measurement artifact, not a gap.** `knowledge_search(type="rules")` returns no numbered CR rule for converge - it is an ability word, and CR 207.2c says ability words "have no special rules meaning". `sweep_pool.ABILITY_WORDS` lists delirium, ferocious, metalcraft, landfall, flurry, channel, ascend and imprint but **not converge**, so the sweeper counts it as an unexecuted keyword. The card's converge clause is in fact fully read (`_parse_converge_exile_by_colors_spent`). Adding "converge" to `ABILITY_WORDS` would fix the count |

## Unreadable targeting

One phrase, on **Prismatic Ending**:
`Converge — Exile target nonland permanent if its mana value is less than or
equal to the number of colors of mana spent to cast this spell.`
`profile_for_text` returns `understood=False` with zero requirements, so CR 115
target legality is **not checked at all** on announcement - the effect resolves
correctly, but the engine will let the spell be announced at an illegal target
(a land, or nothing) and only fizzle later. The blocker is the ability-word
prefix plus the trailing `if <condition>` clause; `machines/targeting.py` reads
neither, so it declines the whole phrase rather than reading the
"target nonland permanent" noun in the middle.

## What to build first, if this deck is the priority

1. **Voice of Victory's static** - three maindeck copies, and the card's whole
   point. Needs a live-static cast prohibition in
   `machines/casting_restrictions.py` keyed to "your opponents" plus a
   turn-ownership window.
2. **Quantum Riddler's draw replacement** - four maindeck copies; the card is
   otherwise just a 5-mana 3/4 flier that cantrips.
3. **Thraben Charm's two dead modes** - two maindeck copies, and the two dead
   modes are the ones actually chosen against creature decks.
4. **Spell Snare / Flusterstorm** - four sideboard cards that resolve doing
   literally nothing; the Flusterstorm case is worse because storm makes it
   look like it is working.
5. **Grafdigger's Cage, Obsidian Charmaw's cost reduction, Consign to Memory's
   replicate, Arena of Glory's haste rider** - sideboard and marginal.

Nothing in this report was implemented; `machines/effects.py` is untouched.

## CR numbers used here

Every one verified with `knowledge_search(type="rules")` in the session that
wrote this file: **100.2a**, **100.4a**, **103.3**, **103.5**, **106.6**,
**118.12a**, **202.3e**, **207.2a**, **207.2c**, **305.6**, **401.1**,
**601.2f**, **603.7a**, **603.7b**, **603.12**, **604.2**, **605.1a**,
**611.3a**, **614.1c**, **614.1d**, **702.40a**, **702.56a**.
`knowledge_search` returned **no numbered rule for converge**, which is itself
the finding recorded above - it is an ability word under CR 207.2c.
