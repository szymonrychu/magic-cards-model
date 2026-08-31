# Effect gaps: scepter chant

The deck: **pilot cgouldner, tournament date 2026-08-25, source deck
`videre-58652729`**, 60 mainboard + 15 sideboard, committed as
`magic-cards-model-api/decks/scepter_chant.txt`. Smoke test:
`tests/scenarios/test_scepter_chant_deck.py`.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file. Where a lookup failed, the text says so and cites
nothing rather than guessing.

## The headline: **the lock does not function**

The archetype is Isochron Scepter imprinting Orim's Chant and recasting a free
copy of it every turn. Of the three things that has to do, one works:

| Piece | Verdict |
|---|---|
| **Imprint** - "When this artifact enters, you may exile an instant card with mana value 2 or less from your hand." | **Works.** "Imprint" is an ability word with no rules meaning (CR 207.2c), so this is an ordinary enters-the-battlefield trigger. `trigger_effect_for("Isochron Scepter", ENTERS_THE_BATTLEFIELD, ...)` returns a real effect built by `_parse_imprint_clause`; the card is exiled with `ExileMarker.IMPRINTED` and `Game.card_imprinted_on` finds it. Asserted in `test_isochron_scepter_imprints_orims_chant_on_entry`. |
| **Casting a copy of a card from the artifact** - "{2}, {T}: You may copy the exiled card. If you do, you may cast the copy without paying its mana cost." | **Dead, and silent.** `activated_effect_for("Isochron Scepter", 0, ...)` returns `None`. `_prepare_effect_clauses` splits it into `["You may copy the exiled card", "If you do, you may cast the copy without paying its mana cost"]` and **neither** clause parses. No notice of any kind is recorded - every `_unreadable_*` probe (`_unreadable_cast_permission_clause`, `_unreadable_anaphoric_clause`, `_unreadable_delayed_clause`, `_unreadable_reflexive_clause`, `_unreadable_conditional_clause`, `_unreadable_imprint_quality`, `_unreadable_unbounded_hand_choice_clause`) returns `None` on this text. Activating the Scepter costs {2} and taps it and then does nothing at all. CR 707.12 (cast a copy of an object) and CR 112.1b (the copy is a spell) have no representation in the engine. |
| **The lock piece's own effect** - Orim's Chant, "Target player can't cast spells this turn." | **Works on its own.** `effect_for` returns a real effect via `create_targeted_cant_cast_restriction`, and `tests/scenarios/test_orims_chant.py` already covers both the unkicked and the kicked (CR 702.33a) halves. |

So: **cast by hand, Orim's Chant locks a turn correctly. Put on the Scepter, the
lock never fires again.** The deck is a pile of counterspells and removal in this
engine, not a prison. `test_the_scepter_recasts_the_imprinted_chant` is an
`xfail(strict=True)` marking exactly that line.

Note that this is a **silent** failure, not a fail-closed one. Nothing is
appended to `imprint_notices`, `unmodeled_trigger_effect_notices`, or any other
notice list. "Nothing was flagged" is not evidence here.

## Survey headline numbers, and why they mislead

`uv run python scripts/survey_cards.py --deck .../scepter_chant.txt` over the 36
distinct names reports **22 handled, 7 silent, 7 no_rules_text**. Both the
"handled" and the "no_rules_text" buckets are wrong in places, per the known
blind spots. What follows is the hand audit.

`EFFECTS` membership was not measured at all - it is not a coverage signal. Every
verdict below comes from calling `effect_for` / `trigger_effect_for` /
`activated_effect_for` per parsed ability, plus `parsed_layer_effects` /
`looks_like_unparsed_layer_effect` for static lines and
`parse_replacement_effects` / `parse_casting_rule_clause` /
`parse_mana_abilities` for the lines those subsystems own.

`effect_for(...) is None` was **not** treated as a gap for lands or permanent
spells, where `None` is correct: a land or an artifact does not have spell
resolution text.

## The `no_rules_text` three-way split

`has_rules_text` skips every static line on a permanent, so this bucket is not
coverage. Seven cards landed in it; they are not the same thing.

**Genuinely empty (2)**

- **Island**, **Plains** - basic lands. No printed abilities at all;
  `parse_mana_abilities` supplies the intrinsic one and `parse_abilities`
  correctly returns `[]`.

**Static modelled elsewhere, named (4)**

- **Hallowed Fountain**, **Sacred Foundry**, **Steam Vents** - "As this land
  enters, you may pay 2 life. If you don't, it enters tapped."
  `machines/replacement.py` `parse_replacement_effects` reads it as two
  `ReplacementEffect`s (`ReplacementKind.AS_ENTERS` with `optional=True`, then
  `ReplacementKind.ENTERS_TAPPED` with `condition="you don't"`). Verified by
  calling it on the fixture. Mana comes from `parse_mana_abilities`.
- **Mystic Gate** - both lines are mana abilities and both parse:
  `{T}: Add {C}` and the filter `{W/U}, {T}: Add {W}{W}, {W}{U}, or {U}{U}`
  (`costs_mana=True`, three options). Nothing for `machines/effects.py` to own.

**Static unmodelled (1)**

- **Kaheera, the Orphanguard** - two separate holes on one card.
  1. `Companion - Each creature card in your starting deck is a Cat, Elemental,
     Nightmare, Dinosaur, or Beast card.` CR 702.139a makes companion a keyword
     ability that functions outside the game, and CR 103.2b is the reveal step.
     Nothing in the engine implements either; `Companion` is reported as an
     ignored keyword. The list is a companion list, so in this engine alice
     simply never gets the extra card.
  2. `Each other creature you control that's a Cat, Elemental, Nightmare,
     Dinosaur, or Beast gets +1/+1 and has vigilance.` **This is the
     Stormscale Scion shape and it fails silently open**: the name is not in
     `LAYER_EFFECTS`, `parsed_layer_effects` returns `None`, **and**
     `looks_like_unparsed_layer_effect(..., static_only=True)` returns `False`.
     No `LayerNotice`, no flag, nothing. The anthem simply does not exist. It
     matters little for this list (Solitude is the only mainboard creature and
     it is an Elemental, so the anthem would apply) but the detector's blind
     spot is real and is recorded here as such.

## Silent cards, clause by clause

Seven cards report `silent`. All seven were split into the clauses
`_prepare_effect_clauses` produces and each clause dispatched separately, because
a paragraph fails closed as a unit (the Goryo's Vengeance shape): one dead clause
kills every working clause beside it.

- **Isochron Scepter** - covered above. Trigger works; activated ability
  completely silent. Two mainboard copies.
- **Spell Snare** (2 copies) - "Counter target spell with mana value 2." One
  clause, dispatches to `None`. Bare "Counter target spell." parses fine, so it
  is the **mana-value restriction** (CR 202.3) that is unreadable. The card does
  nothing on resolution.
- **Day's Undoing** (1 main, 1 side) - clauses:
  `["Each player shuffles their hand", "graveyard into their library",
  "draws seven cards", "If it's your turn, end the turn"]`. Only
  `"draws seven cards"` parses. The other three are `None`, so the whole
  paragraph fails closed and the card does nothing - including "end the turn",
  which the engine has no representation for at all.
- **Narset, Parter of Veils** (4 copies) - **both** lines dead.
  - Static: "Each opponent can't draw more than one card each turn."
    `parse_casting_rule_clause` does not read it (it is a draw restriction, not a
    casting one) and nothing else does. Drawing is CR 121.1; there is no
    per-turn draw cap anywhere. **This is the deck's second lock piece and it is
    inert.**
  - `−2`: clauses `["Look at the top four cards of your library",
    "You may reveal a noncreature, nonland card from among them",
    "put it into your hand",
    "Put the rest on the bottom of your library in a random order"]`.
    **Every one** dispatches to `None`. The loyalty ability does nothing.
- **Monumental Henge** (1 copy) - the mana ability `{T}: Add {W}` parses. The
  `{2}{W}{W}, {T}` ability splits the same four ways as Narset's `−2` and every
  clause is `None`. Its "enters tapped unless you control a Plains" line **is**
  modelled, by `machines/replacement.py` (`ENTERS_TAPPED` with
  `condition="unless you control a Plains"`), verified on the fixture.
- **Geier Reach Sanitarium** (1 copy) - `{T}: Add {C}` parses. The
  `{2}, {T}` ability splits to `["Each player draws a card", "discards a card"]`;
  the *second* parses and the *first* does not, so the paragraph fails closed and
  the ability does nothing. A clean paragraph-fails-closed case.
- **Ashiok, Dream Render** (sideboard, 1 copy) - `−1` splits to
  `["Target player mills four cards", "Then exile each opponent's graveyard"]`.
  The **first parses**, the second does not, so the whole ability is silent -
  the mill is lost along with the exile. Its static ("Spells and abilities your
  opponents control can't cause their controller to search their library") is
  also unmodelled; nothing in the engine gates a search by opponent effect.
- **Beza, the Bounding Spring** (sideboard, 1 copy) - one enters trigger with
  four "X if an opponent has more Y than you" clauses. **All four** are `None`.
  The creature enters as a vanilla 4/5 with no trigger at all.

## Clause-by-clause audit of the *handled* cards

`classify_card` reports the best outcome per card, so a dead clause hides behind
a working one. Each handled card's clauses were dispatched individually.

**Clean - every clause parses**

- **Counterspell** ("Counter target spell.")
- **Celestial Purge** ("Exile target black or red permanent.")
- **Consign to Memory** ("Counter target triggered ability or colorless spell.")
- **Orim's Chant** (its one effect line; kicker is CR 702.33a and is charged by
  `machines/casting.py`'s `ADDITIONAL_COST_KEYWORDS` path)
- **Consult the Star Charts** (the X-lands look, kicked and unkicked)
- **Wrath of the Skies**, **Galvanic Discharge** (both energy cards; `{E}` is
  modelled on `Player.energy` and both dispatch to real effects)
- **Solitude** - trigger handled, and `Evoke` is a real
  `keyword_cast_options` entry with `understood=True`
- **Prismatic Ending** - the exile clause parses; see the false-green note below
- **Hedge Maze**, **Meticulous Archive**, **Thundering Falls** - "This land
  enters tapped." via `machines/replacement.py`, "surveil 1" trigger handled
- **Arid Mesa**, **Flooded Strand**, **Scalding Tarn** - fetch ability handled
- **Rest in Peace** - trigger handled, and the replacement line
  ("If a card or token would be put into a graveyard from anywhere, exile it
  instead.") produces a real `CardReplacement` in `parsed_card_replacements`
- **Supreme Verdict** - "Destroy all creatures." parses (see false green below)
- **Mystical Dispute** - "Counter target spell unless its controller pays {3}."
  parses (see false green below)
- **Force of Negation** - the counter-and-exile line parses (see false green
  below)
- **High Noon** - the `{4}{R}` sacrifice ability parses (see false green below)

**Handled overall, but with a dead clause inside**

- **Teferi, Time Raveler** (3 copies) - `+1` handled
  (`create_sorcery_speed_flash_grant`), `−3` handled. The **static**
  ("Each opponent can cast spells only any time they could cast a sorcery.") is
  *not* dead: `parse_casting_rule_clause` misses it, but
  `machines/casting_restrictions.sorcery_speed_restriction_source` scans the
  battlefield for exactly this printed sentence on every call and
  `machines/casting.py` consults it. This one is fine - flagged only because the
  per-clause dispatch reads as silent and it is not.

## False greens - cards that will act *incorrectly*, not silently

These are the dangerous ones. Each classifies as `handled` and each will produce
wrong behaviour in a game.

1. **Supreme Verdict** (1 main, 1 side). "This spell can't be countered." is
   **stripped as preamble** by `_strip_non_effect_preamble`
   (`_CANT_BE_COUNTERED_LINE_RE`) so the rest of the card parses, and then
   nothing enforces it. There is no counterability quality anywhere -
   `models/card_state.py` has no such field, `machines/targeting.py` never
   checks one, and `machines/replacement.py`'s own docstring lists Cavern of
   Souls's "and that spell can't be countered" as an unwired consumer. Under
   CR 113.6g a "can't be countered" ability functions on the stack; here it does
   not, so **a Counterspell or Spell Snare will happily counter Supreme
   Verdict** (CR 701.6a). Wrong behaviour, and it favours the opponent in a
   mirror this deck expects to play.
2. **Prismatic Ending** (2 copies). The exile clause parses, but `Converge` is
   reported as an ignored keyword **and** the targeting sweep reports
   `[static] Converge — Exile target nonland permanent if its mana value is
   less than or equal to the number of colors of mana spent to cast this spell.`
   as an unreadable targeting phrase. The engine does not track how many colors
   of mana paid for the spell, so the mana-value bound is not enforced - the card
   will exile permanents it should be unable to touch. `knowledge_search` has no
   CR entry for *converge*, so no rule number is cited for it here.
3. **Consign to Memory** (3 sideboard). The counter clause parses;
   `Replicate` (CR 702.56a) is an ignored keyword with no execution path, so
   paying replicate produces no copies. The card counters exactly one thing no
   matter what is paid.
4. **Force of Negation** (1 copy). The counter-and-exile line parses, but the
   alternative-cost line ("If it's not your turn, you may exile a blue card from
   your hand rather than pay this spell's mana cost.") dispatches to `None` and
   `keyword_cast_options` returns `[]` for the card. The free mode does not
   exist, so the card is a three-mana counterspell only. This is a *missing
   ability* rather than a wrong action, but it classifies green and silently
   changes how the deck plays.
5. **Mystical Dispute** (3 sideboard). "Counter target spell unless its
   controller pays {3}." parses. "This spell costs {2} less to cast if it targets
   a blue spell." dispatches to `None` and the cost-reduction shapes in
   `machines/cost.py` are the "\<Color\>/\<Type\> spells you cast cost {N} less"
   family, not a self-referential conditional on the spell's own target. It is
   always a three-mana card here.
6. **High Noon** (2 sideboard). The `{4}{R}` sacrifice ability parses. The static
   ("Each player can't cast more than one spell each turn.") is unmodelled -
   `parse_casting_rule_clause` misses it and nothing else caps casts per turn,
   even though `Game.spells_cast_this_turn` already exists and would supply the
   count. The card looks handled and enforces nothing.

## Ignored keywords

Reported by the survey, three occurrences, plus one found by hand:

| Keyword | Card | Status |
|---|---|---|
| `Replicate` | Consign to Memory | No execution path. CR 702.56a. |
| `Converge` | Prismatic Ending | No execution path; `knowledge_search` has no CR entry for converge, so none is cited. |
| `Companion` | Kaheera, the Orphanguard | No execution path. CR 702.139a, CR 103.2b. |
| `Kicker` | Orim's Chant, Consult the Star Charts | **Executed** - `machines/casting.py`'s `ADDITIONAL_COST_KEYWORDS`, CR 702.33a. Listed for completeness, not as a gap. |

## Unreadable targeting

One phrase: Prismatic Ending's converge clause, above.

## What would have to be built for this deck to play

In rough order of how much of the archetype each unlocks:

1. Casting a copy of a card from an object (CR 707.12, CR 112.1b) - the Scepter's
   whole reason to exist.
2. A per-turn draw cap (Narset's static) and a per-turn cast cap (High Noon).
3. A counterability quality on a spell (CR 113.6g), for Supreme Verdict, and the
   colors-of-mana-spent tally for converge.
4. The "look at the top N, reveal one matching a quality, bottom the rest"
   family - it is dead on Narset's `−2` and on Monumental Henge alike.
5. `Companion` (CR 702.139a) and alternative pitch costs on Force of Negation.

**None of this is implemented here.** This document is a report; no engine code
and no entry in `machines/effects.py` was changed.
