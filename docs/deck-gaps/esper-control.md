# Effect gaps: Esper control (Modern, ~2.0% of the metagame)

The list surveyed here is a registered tournament decklist - pilot `yriel`,
tournament date 2026-08-30, source deck `videre-58656301` - pulled with
`statistics_decks(format="modern", archetype_name="esper control")`. All 33
distinct names came back `legal` from
`resolve_cards(format="modern", fields="legality")`. The list lives at
`magic-cards-model-api/decks/esper_control.txt` and is mirrored in
`tests/scenarios/test_esper_control_deck.py`.

Measured with the engine's own classifier, not by reading `machines/effects.py`:

```sh
uv run python scripts/survey_cards.py \
  --deck ../magic-cards-model-api/decks/esper_control.txt --json
```

`scripts/survey_cards.py` runs `scripts/sweep_pool.classify_card` over the
decklist, so every verdict below is the production dispatcher's, not a reading
of the registry.

## The split

| Bucket | Distinct cards |
|---|---|
| `handled` | 21 |
| `silent` | 5 |
| `no_rules_text` | 7 |

33 distinct names across mainboard and sideboard.

## Silent - the engine does nothing and records nothing

These are the real gaps. Each is a card the classifier recognised as having
rules text and then produced no effect for.

| Card | Copies | What is not happening |
|---|---|---|
| Inquisition of Kozilek | 2 main | "Target player reveals their hand. You choose a nonland card from it with mana value 3 or less. That player discards that card." Targeted reveal-and-choose discard with a mana-value filter is unread; the spell resolves and no card is discarded. |
| Ketramose, the New Dawn | 4 main | "Whenever one or more cards are put into exile from graveyards and/or the battlefield during your turn, you draw a card and lose 1 life." The exile-from-multiple-zones trigger condition is unread. Its other lines are covered below under ignored keywords. |
| Orcish Bowmasters | 2 main | "When this creature enters and whenever an opponent draws a card except the first one they draw in each of their draw steps, this creature deals 1 damage to any target. Then amass Orcs 1." Neither half of the compound trigger fires, and the amass rider is separately unmodelled. |
| Spell Snare | 1 main, 1 side | "Counter target spell with mana value 2." The counter itself is a shape the engine knows; the mana-value-2 restriction on the target is not read, so the spell is filed silent rather than countering. |
| Takenuma, Abandoned Mire | 1 main | "Channel - {3}{B}, Discard this card: Mill three cards, then return a creature or planeswalker card from your graveyard to your hand. This ability costs {1} less to activate for each legendary creature you control." The channel ability is not executed. Note the sibling land Otawara, Soaring City *is* handled, so the gap is the mill-then-return body, not channel as such. |

Everything else on the list classified `handled`, including the fetchlands, the
surveil lands, Solitude's exile trigger, White Orchid Phantom, Quantum Riddler,
Relic of Progenitus, Prismatic Ending, Psychic Frog, Thoughtseize, Ephemerate,
No More Lies, Mystical Dispute, Wrath of the Skies, Consign to Memory, Fatal
Push, and Teferi, Time Raveler's +1.

## `no_rules_text` is NOT a completeness claim

`scripts/sweep_pool.has_rules_text` deliberately skips **every static line on a
permanent** (static abilities: CR 113.3, CR 113.3d, CR 604.1). A permanent whose
only text is static therefore lands in `no_rules_text` regardless of whether any
machine actually reads that text. Do not read this bucket as covered.

The seven, split by whether the skipped text is genuinely modelled elsewhere:

**Genuinely nothing to model (3)** - Island, Plains, Swamp. Their only line is
the reminder-text mana ability.

**Real static text, modelled elsewhere (3)** - Godless Shrine, Hallowed
Fountain, Watery Grave. "As this land enters, you may pay 2 life. If you don't,
it enters tapped." is read by `machines/replacement.py`, which carries an
explicit shockland path. Covered, but not by anything the classifier counted.

**Real static text, UNMODELLED (1)** - **Grafdigger's Cage** (1 sideboard).
"Creature cards in graveyards and libraries can't enter the battlefield. Players
can't cast spells from graveyards or libraries." Neither sentence is read
anywhere in `src/magic_cards_model/machines/` - grepping the whole package for
either prohibition returns nothing. The Cage currently sits on the battlefield
doing nothing at all, and the classifier reports it as `no_rules_text`, so a
follow-up pass reading the bucket count would miss it entirely. This is the same
shape of artifact a sibling agent found with Mox Opal's metalcraft restriction.
`tests/scenarios/test_esper_control_deck.py` carries a `strict` xfail pinning
this gap.

## Ignored keywords on otherwise-handled cards

Reported by `sweep_pool.ignored_keywords` - the card's main effect works, these
riders do not.

| Card | Keyword | Effect of the gap |
|---|---|---|
| Consign to Memory | Replicate | The counter resolves; the copies-for-each-replicate-payment never happen. |
| Fatal Push | Revolt | Destroys within its base mana-value bound only; the revolt upgrade is not applied. |
| Prismatic Ending | Converge | See targeting gap below - the mana-value bound derived from colors spent is not computed. |
| Orcish Bowmasters | Amass | Rider on an already-silent card, so nothing of the card fires today. |

Ketramose, the New Dawn's printed keywords (menace, lifelink, indestructible)
were not flagged as ignored, but its restriction line "Ketramose can't attack or
block unless there are seven or more cards in exile" is a static ability that
`has_rules_text` skips on a permanent - it was not surveyed and is not known to
be modelled.

## Targeting text the parser could not read

`sweep_pool.targeting_gaps` reported exactly one:

- **Prismatic Ending** - `[static] Converge - Exile target nonland permanent if
  its mana value is less than or equal to the number of colors of mana spent to
  cast this spell.` `machines/targeting.py` cannot express "mana value bounded by
  colors spent", so the target legality check is looser than the card.

## Not done here, deliberately

Nothing in `src/magic_cards_model/machines/` was edited for this survey, and in
particular `machines/effects.py` was not touched - several agents were working
in parallel and that file is the conflict point. This document is a measurement,
not a fix.

CR numbers cited above were verified with `knowledge_search(type="rules")` in
the session that wrote this file: 100.2a, 100.4a, 103.3, 103.4, 103.5, 113.3,
113.3d, 401.1, 604.1.
