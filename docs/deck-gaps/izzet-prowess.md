# Effect gaps: Modern izzet prowess

The list is `magic-cards-model-api/decks/izzet_prowess.txt` - pilot **ratabruta**,
tournament date **2026-08-30**, source deck id **videre-58656391**, 60 main / 15
side, 26 distinct names. Every name resolved `legal` in Modern (26 names sent,
26 rows returned, `not_found` empty). The four separate one-of `Mountain` rows
the source printed were consolidated to `3 Mountain`; no count changed.

Measured with the repo's own classifier, not by reading `machines/effects.py`:

```sh
uv run python scripts/survey_cards.py --deck ../magic-cards-model-api/decks/izzet_prowess.txt
```

## The split

| Category | Count |
|---|---|
| handled | 20 |
| silent | 3 |
| no_rules_text | 3 |
| ignored-keyword occurrences | 1 |
| unreadable targeting phrases | 0 |

**`no_rules_text` is not a synonym for covered**, and neither is `handled`:
`classify_card` takes the *best* outcome anywhere on a card (a card is only dead
if nothing on it does anything), and `has_rules_text` deliberately skips a
permanent's static line. Both blind spots bite this deck, so the per-clause
sections below matter more than the table.

## Silent - nothing happens and nothing is recorded (3 cards)

All three are sideboard cards, and two of the three want the same missing
primitive.

### Countering a spell (2 cards)

`701.6a`: "To counter a spell or ability means to cancel it, removing it from the
stack. It doesn't resolve and none of its effects occur. A countered spell is put
into its owner's graveyard."

| Card | Oracle text | Missing primitive |
|---|---|---|
| Spell Snare | "Counter target spell with mana value 2." | A counter effect whose target filter is a mana-value predicate (`202.3`). The engine has no counter-by-mana-value shape. |
| Spell Pierce | "Counter target noncreature spell unless its controller pays {2}." | A *conditional* counter - "unless its controller pays {N}" needs the spell's controller offered an optional cost payment during resolution, then the counter applied only if declined. Neither half exists. |

Note that Consign to Memory ("Counter target triggered ability or colorless
spell") classifies **handled**, so some counter shape does dispatch; these two
predicates are what it cannot read.

### Damage to a group of objects and players (1 card)

`120.1`: objects deal damage to battles, creatures, planeswalkers, and players.

| Card | Oracle text | Missing primitive |
|---|---|---|
| End the Festivities | "End the Festivities deals 1 damage to each opponent and each creature and planeswalker they control." | A one-shot damage effect over an *untargeted compound set* spanning both players and permanents in one clause. Single-target damage (Lightning Bolt, Lava Dart, Unholy Heat) is handled; "each opponent and each creature and planeswalker they control" is not. |

## No rules text - what the classifier declined to judge (3 cards)

| Card | Why it landed here | Actually covered? |
|---|---|---|
| Mountain | Only its intrinsic mana ability (`605.1a`), which never goes on the stack (`605.3b`) | Yes. |
| Monastery Swiftspear | Both its lines are keywords - haste and prowess - and `has_rules_text` skips keyword abilities | **Yes, and verified.** Both are in `executed_keywords`; `tests/scenarios/test_izzet_prowess_deck.py::test_a_bolt_from_this_list_pumps_a_swiftspear_from_this_list` casts this deck's own Lightning Bolt and asserts the pump (`702.108a`). Prowess is working end to end. |
| Steam Vents | Its only non-mana line is a *static* line on a *permanent*, which `has_rules_text` skips by design | Yes. "As this land enters, you may pay 2 life. If you don't, it enters tapped." is a `614.1c` / `614.12` replacement effect owned by `machines/replacement.py`, which has an explicit shockland parser, and `tests/scenarios/test_decisions_during_resolution.py` drives Steam Vents through it. |

So this deck's `no_rules_text` bucket is genuinely clean - but only because it
was checked card by card, not because the count said 3.

## Clauses on otherwise-handled cards with no execution path

These cards all count as **handled** in the table above. Each is handled on
*one* of its abilities and dead on another. This is where the real gap is.

### Static continuous effects nothing generates (`613.1f` layer 6, `613.4c` layer 7c)

| Card | Dead clause | Status |
|---|---|---|
| Dragon's Rage Channeler | "*Delirium* — As long as there are four or more card types among cards in your graveyard, this creature gets +2/+2, has flying, and attacks each combat if able." | No `LAYER_EFFECTS` row and no parsed shape matches; `effects_for` returns nothing and records no notice. The card's `handled` comes entirely from its other line, the cast trigger (surveil 1, `701.25a`). `docs/engine-coverage.md` already records this. |
| Cori-Steel Cutter | "Equipped creature gets +1/+1 and has trample and haste." | No Equipment's static bonus text generates a continuous effect for anything. Attaching works (`702.6a`, `301.5a`), the bonus does not. Its `handled` comes from the *Flurry* trigger only. `tests/scenarios/test_equip.py` and `test_flurry_ordinal_trigger.py` both say so in their docstrings. |

*Delirium* is an ability word with no rules meaning of its own (`207.2c`), so in
both cases the whole mechanic is that one sentence - there is nothing else to
fall back on. Unholy Heat's and Violent Urge's delirium clauses are the
counter-example and *are* modelled, so this is a per-card gap, not a delirium
gap.

### Ignored keywords - printed on the card, no code acts on them

| Card | Keyword | Note |
|---|---|---|
| Consign to Memory | Replicate {1} | `702.56a`: two abilities, a static one on the stack and a triggered one. Neither is modelled, so the spell always resolves as a single un-replicated copy. This is the survey's one ignored-keyword occurrence. |

Every other keyword in the deck has an execution path per `executed_keywords`:
prowess and haste (Monastery Swiftspear), flying / haste / plot (Slickshot
Show-Off, `702.170d`), equip (Cori-Steel Cutter, `702.6a`), flashback (Lava
Dart, `702.34a`). *Flurry* and *Delirium* are ability words (`207.2c`) and are
correctly not counted as keywords by the sweeper - which is exactly why the two
dead delirium/equipped-creature statics above do **not** show up in the
ignored-keyword column and have to be read out of the per-clause table instead.

## What this deck can already do

Handled and exercised: the mana base (fetchlands, Fiery Islet's draw, Thundering
Falls' enters-tapped plus surveil trigger, Steam Vents' shockland choice),
Lightning Bolt / Lava Dart / Unholy Heat damage including Unholy Heat's delirium
branch, Preordain and Expressive Iteration's selection, Mutagenic Growth and
Violent Urge's pumps including Violent Urge's delirium double strike, Mishra's
Bauble's activation, Tormod's Crypt's activation, Meltdown's X-destroy,
Cori-Steel Cutter's Flurry token, Dragon's Rage Channeler's surveil trigger,
Slickshot Show-Off's own noncreature-cast pump, and prowess.

## CR numbers cited here

All verified with `knowledge_search(type="rules")` in the session that wrote
this file: 120.1, 202.3, 207.2c, 301.5a, 605.1a, 605.3b, 613.1f, 613.4c, 614.1c,
614.12, 701.6a, 701.25a, 702.6a, 702.34a, 702.56a, 702.108a, 702.170d.
