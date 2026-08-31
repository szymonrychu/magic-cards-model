# Effect gaps: Modern 45c aggro

Decklist: **pilot Pleyboy, tournament date 2026-08-29, source deck
`videre-58655679`**, pulled with `statistics_decks(format="modern",
archetype_name="45c aggro", date_from="2026-06-01", include_cards="full")`.
Sixty mainboard, fifteen sideboard, every name legal in Modern per
`resolve_cards(format="modern", fields="legality")`. The list lives in the API
repo as `decks/45c_aggro.txt`; the smoke test is
`tests/scenarios/test_deck_45c_aggro.py`.

## How this was measured

Not by `EFFECTS` membership - that registry is deliberately near-empty and
over-reports wildly. Every row below comes from calling the **production
dispatchers** (`effect_for`, `trigger_effect_for`, `activated_effect_for`) per
parsed ability, with the same arguments `models/game.py` passes them, via
`scripts/survey_cards.py --deck` and `scripts/sweep_pool.classify_card`. Static
permanent text, which those dispatchers never own, was checked separately
against `machines/replacement.parse_replacement_effects`,
`machines/replacement.replacements_of` and `machines/layers` (`LAYER_EFFECTS`,
`parsed_layer_effects`, `looks_like_unparsed_layer_effect`), and the manabase
was checked by actually playing the lands in a scenario.

Headline from the classifier over the 31 distinct names:

| bucket | count |
|---|---|
| handled | 20 |
| silent | 1 |
| no rules text (per `has_rules_text`) | 10 |

The `no_rules_text` figure is **not** a coverage claim, and the hand audit below
splits it three ways.

## The manabase - checked, not assumed

Every land was played through the engine and tapped for mana. Result: **no land
in this deck is mute.** That is the opposite of the Eldrazi Temple / Cavern of
Souls class of failure, where a CR 106.6-style spend restriction or an as-enters
clause makes the parser refuse the whole ability.

| land | mana produced | enters-tapped clause | verdict |
|---|---|---|---|
| Mountain, Plains | `{R}` / `{W}` | none | correct (CR 305.6 intrinsic) |
| Blood Crypt, Steam Vents, Temple Garden | both printed colours | "As this land enters, you may pay 2 life. If you don't, it enters tapped." parses as `as_enters` + conditional `enters_tapped`; paying 2 life really does drop life to 18 and leave the land untapped | correct (CR 614.1c, CR 614.12a) |
| Indatha Triome | `{W}` / `{B}` / `{G}` | "This land enters tapped." applied - enters tapped | correct |
| Lush Portico, Thundering Falls | both printed colours | enters tapped, and the `surveil 1` ETB trigger is handled | correct |
| Arena of Glory | `{R}` from the plain ability, and the exert ability `{R}, {T}, Exert this land: Add {R}{R}` also parses | **"This land enters tapped unless you control a Mountain." is parsed with `condition="unless you control a Mountain"` and then ignored - the land enters untapped either way** | **defect, see below** |
| Arid Mesa, Flooded Strand, Wooded Foothills | none, correctly - they print no `{T}: Add` line | n/a | correct; the fetch activation itself is handled |

All five colours are reachable off the mainboard's lands, and the smoke test
asserts exactly that.

The one caveat is that this manabase is only *nominally* five-colour without
Leyline of the Guildpact. The deck plays 4 Leyline of the Guildpact to make
every land every basic land type, which is what turns 14 lands into a real
five-colour base and what powers domain. That leyline is inert (below), so the
engine's version of this deck is a WUBRG-on-paper deck whose colour fixing is
strictly what the lands print.

## Spell gaps (things that resolve and do nothing)

### Stubborn Denial - the only fully silent card

```
Counter target noncreature spell unless its controller pays {1}.
Ferocious - If you control a creature with power 4 or greater, counter that spell instead.
```

`effect_for("Stubborn Denial", ...)` returns `None`. Both clauses are silent:

- **Missing primitive: conditional counter ("counter target spell unless its
  controller pays {N}").** This is not the plain "counter target spell" shape;
  it needs a counter effect that first offers the spell's controller a payment
  and only counters on refusal.
- **Missing primitive: an ability-word-gated upgrade to an already-resolving
  effect.** Ferocious is an ability word with no rules meaning (CR 207.2c), so
  the work is the second sentence replacing the first's outcome, which no
  dispatcher reads.

Every other spell in the list resolves to a real effect. Phelia's attack trigger
is handled, and only its *spell* dispatch records a `DelayedClauseNotice` -
fail-closed, not silent.

## Permanent, trigger, and layer gaps

These are static or continuous-effect gaps. They never reach
`machines/effects.py` at all, which is exactly why the classifier's
`no_rules_text` bucket hides them.

### Leyline of the Guildpact - all three lines inert (4 copies, mainboard)

```
If this card is in your opening hand, you may begin the game with it on the battlefield.
Each nonland permanent you control is all colors.
Lands you control are every basic land type in addition to their other types.
```

- **Missing primitive: CR 103.6a's opening-hand battlefield start.**
  `machines/replacement.py` states outright that opening-hand effects are not
  claimed ("has neither 'would' nor a prevention word and is not claimed"), and
  `models/match.py` says CR 103.6's actions "are a separate sequence ... and are
  not modelled". So the free turn-zero leyline cannot happen at all.
- **Missing primitive: a layer-5 (CR 613.1e) "each nonland permanent you control
  is all colors" continuous effect.** `parsed_layer_effects` returns `None`.
- **Missing primitive: a layer-4 (CR 613.1d) grant of every basic land type to
  your lands.** The *identical printed sentence* already exists in
  `machines/layers.LAYER_EFFECTS`, but only as a name-keyed row for **Dryad of
  the Ilysian Grove** - `parsed_layer_effects` does not read the shape off
  oracle text, so the Leyline gets nothing. This is the highest-value gap in the
  deck: it is the whole colour-fixing and domain engine, and it is one text
  parser away from an implementation that already exists.

`looks_like_unparsed_layer_effect` also returns `False` for all three, so
nothing even records a `LayerNotice` - the card is silently, invisibly dead.

### Scion of Draco - both lines inert (4 copies, mainboard)

```
Domain - This spell costs {2} less to cast for each basic land type among lands you control.
Flying
Each creature you control has vigilance if it's white, hexproof if it's blue, lifelink if it's
black, first strike if it's red, and trample if it's green.
```

- **Missing primitive: a domain-scaled cost reduction (CR 601.2f).** Measured:
  with five basic land types on the battlefield, `Casting.total_cost` for Scion
  of Draco is still its printed `{12}` (it should be free), and Leyline
  Binding's is still `{5}{W}` (it should be `{W}`). Flying is handled.
- **Missing primitive: a layer-6 (CR 613.1f) *conditional per-object* keyword
  grant - "has X if it's [colour]".** Anthem-shaped unconditional grants parse;
  a grant whose applicability is decided per affected creature from that
  creature's own colour does not. Note this compounds with the Leyline: in the
  real deck, the Leyline makes every creature all colours so the Scion grants
  all five keywords to everything.

### Territorial Kavu - the domain CDA is inert (4 copies, mainboard)

```
Domain - Territorial Kavu's power and toughness are each equal to the number of basic land
types among lands you control.
```

- **Missing primitive: a characteristic-defining ability (CR 604.3) that sets
  P/T from a board count.** `parsed_layer_effects` returns `None`, so the Kavu
  has no power at all and cannot deal combat damage. Its *attack trigger* (the
  modal discard/draw or graveyard-exile) is fully handled - the creature works
  except that it is sizeless.

### Arena of Glory - the conditional enters-tapped is ignored (2 copies)

```
This land enters tapped unless you control a Mountain.
```

`parse_replacement_effects` returns `kind=enters_tapped` with
`condition="unless you control a Mountain"`, but playing it with an empty
battlefield still puts it in untapped.

- **Missing primitive: evaluating an `unless [board condition]` guard on an
  `enters_tapped` replacement (CR 614.1c).** The unconditional form works
  (Indatha Triome, Lush Portico, Thundering Falls all enter tapped), and the
  shockland's `if you don't` condition works, so this is a specific hole in
  condition evaluation rather than a missing mechanism. It errs in the
  controller's favour, which is why no other test caught it.

### High Noon - the static half is inert (1 copy, sideboard)

```
Each player can't cast more than one spell each turn.
```

Its `{4}{R}, Sacrifice this enchantment: 5 damage` activation is handled.

- **Missing primitive: a per-turn spell-count cast restriction.** Verified by
  casting two Lightning Bolts in one turn with High Noon on the battlefield:
  `why_cannot_cast_now` returns `None` for the second.

### Quantum Riddler - the draw replacement fails closed (4 copies, mainboard)

```
As long as you have one or fewer cards in hand, if you would draw one or more cards, you draw
that many cards plus one instead.
```

`parse_replacement_effects` returns `kind=unparsed` for it. That is a **notice,
not a silent gap** - the engine recognised the shape and refused rather than
guessing, which is the correct fail-closed behaviour. The ETB draw and flying
both work.

- **Missing primitive: a conditional draw-modifying replacement effect gated on
  hand size.** Worth listing because the card is a 4-of and this line is half of
  why it is played.

### Statics that ARE modelled (so, not gaps)

- **Rest in Peace** - "If a card or token would be put into a graveyard from
  anywhere, exile it instead" is read generically by
  `_compile_graveyard_exile`; `replacements_of` returns a live
  `CardReplacement`.
- **Containment Priest** - "If a nontoken creature would enter and it wasn't
  cast, exile it instead" is read generically by `_compile_enters_uncast_exile`;
  `replacements_of` returns a live `CardReplacement`.
- **Shocklands** (Blood Crypt, Steam Vents, Temple Garden) - the whole CR 614.1c
  as-enters choice runs, verified by playing them.
- **Plain enters-tapped** (Indatha Triome, Lush Portico, Thundering Falls) -
  applied.
- **Leyline Binding** - the cost reduction is not modelled (same domain gap as
  Scion of Draco), but flash and the exile-until-leaves ETB trigger both are, so
  the card is functional at full price.
- **Teferi, Time Raveler**'s static, "Each opponent can cast spells only any
  time they could cast a sorcery", is modelled -
  `machines/casting_restrictions.sorcery_speed_restriction_source` returns
  Teferi for the opponent and `None` for its controller, re-scanned live off the
  battlefield per CR 604.2. Both loyalty abilities are handled too, so the
  planeswalker is fully covered.

## The `no_rules_text` audit, three ways

`sweep_pool.has_rules_text` skips **every** static line on a permanent, so this
bucket mixes genuinely empty cards with cards carrying real, wholly unmodelled
text. All ten, hand-audited:

### Genuinely empty (2)

| card | why |
|---|---|
| Mountain | reminder text only; its mana ability is CR 305.6 intrinsic |
| Plains | same |

### Static text modelled elsewhere (5)

| card | the text | who owns it |
|---|---|---|
| Blood Crypt | as-enters pay 2 life / else enters tapped | `machines/replacement.py` (CR 614.1c, CR 614.12a) |
| Steam Vents | same | same |
| Temple Garden | same | same |
| Indatha Triome | "This land enters tapped." + Cycling {3} | `machines/replacement.py` (`ENTERS_TAPPED`) + `machines/keywords.py` (cycling) |
| Containment Priest | "If a nontoken creature would enter and it wasn't cast, exile it instead." | `machines/replacement.py` (`_compile_enters_uncast_exile`) |

### Static text that is unmodelled (3)

| card | the text | missing primitive |
|---|---|---|
| Arena of Glory | "This land enters tapped unless you control a Mountain." | `unless [board condition]` guard on an `enters_tapped` replacement - parsed, then dropped |
| Leyline of the Guildpact | all three lines | CR 103.6a opening-hand battlefield start; layer-5 "is all colors"; layer-4 "every basic land type" |
| Scion of Draco | domain cost reduction; conditional per-object keyword grant | CR 601.2f domain-scaled reduction; layer-6 "has X if it's [colour]" |

Arena of Glory and Leyline of the Guildpact are exactly the Mox Opal / Grafdigger's
Cage shape the audit exists to catch: they land in `no_rules_text`, look clean,
and are not.

## Keywords with no execution path

| keyword | on | CR |
|---|---|---|
| Replicate | Consign to Memory (2 main, 2 side) | CR 702.56a - "a static ability that functions while the spell with replicate is on the stack" plus a triggered copy ability. Nothing charges the optional `{1}` or makes the copies. |
| Fuse | Wear // Tear (1 side) | CR 702.102a - casting both halves of a split card from hand as one spell. Each half casts fine alone; the fused cast has no path. |
| Domain | Scion of Draco, Territorial Kavu, Leyline Binding | An ability word (CR 207.2c), so nothing is *owed* for the word itself - but all three of its uses here (cost reduction x2, CDA P/T) are unmodelled, as above. |

Everything else in the deck has an execution path: Flying and Exert
(`machines/combat.py` / `machines/keywords.py`), Flash
(`machines/casting.py` timing), Cycling (`machines/keywords.py`), Dash and Warp
(`machines/casting.py` cast options), Surveil and Treasure (action word and
token type - no code owed).

Targeting: `targeting_gaps` reports **zero** unreadable phrases across all 31
cards.

## Nothing was implemented

Per the assignment, no engine code was changed and `machines/effects.py` was not
touched. The three highest-value gaps, in order, are: the Leyline's layer-4
land-type grant (a text parser away from an existing implementation), the
domain-scaled cost reduction, and Stubborn Denial's conditional counter.

## CR numbers

Every number in this document was verified with
`knowledge_search(type="rules")` in the session that wrote it: 100.2a, 100.4a,
103.2a, 103.3, 103.4, 103.5, 103.6, 103.6a, 113.4, 116.2a, 118.7a, 207.2c,
305.1, 305.6, 401.1, 601.2f, 604.2, 604.3, 605.1a, 605.3b, 611.3a, 613.1d,
613.1e, 613.1f, 614.1c, 614.12a, 702.56a, 702.102a.

CR 106.6 is named in the assignment brief as the spend-restriction rule behind
the Eldrazi Temple class of failure; it was **not** looked up here because no
card in this deck carries a spend restriction, so no claim is made about it.
