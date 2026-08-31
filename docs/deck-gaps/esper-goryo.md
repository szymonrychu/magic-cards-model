# Esper Goryo - effect gaps

The list: **jussupinator, 2026-08-29, source deck `videre-58656080`**, pulled
with `statistics_decks(format="modern", archetype_name="esper goryo",
date_from="2026-06-01", include_cards="full")`. Mainboard 60, sideboard 15, 31
distinct names. All 31 names were sent to
`resolve_cards(format="modern", fields="legality")` and **31 rows came back**,
every one `legal`. The decklist lives at
`magic-cards-model-api/decks/esper_goryo.txt`; the smoke test is
`tests/scenarios/test_esper_goryo_deck.py`.

Measured with `uv run python scripts/survey_cards.py --deck
.../decks/esper_goryo.txt`, which calls the production dispatchers
(`effect_for`, `trigger_effect_for`, `activated_effect_for`) with the exact
arguments `models/game.py` uses. **Not** by `EFFECTS` membership: `effect_for`
falls back to `parse_mixed_effect_for_spell` over the card's own oracle text, so
registry membership measures nothing.

## The split

| Category | Count |
|---|---|
| handled | 21 |
| notice (recognised, fails closed) | 1 |
| **silent (resolves as nothing)** | **3** |
| no rules text | 6 |
| 31 |

Raw `effect_for(name, oracle_text) is None` over all 31 names is 21, but that
number is misleading on its own: for a land it is correct (a land is played as a
special action, CR 305.1, and never goes on the stack), and for a permanent
spell it is correct too (the spell resolves by entering the battlefield; its
work lives in the trigger and activated layers). The table above is the real
measure, because it asks every clause on the card, not just the top-level spell
dispatch.

`classify_card` reports a card's **best** outcome, so a card marked `handled`
can still have a dead clause. Those are broken out below.

---

## 1. Spell gaps - `machines/effects.py` registry work

### The archetype's centrepiece is dead

**Goryo's Vengeance** `{1}{B}` Instant - Arcane - **notice**, not handled.

> Return target legendary creature card from your graveyard to the battlefield.
> That creature gains haste. Exile it at the beginning of the next end step.
> Splice onto Arcane {2}{B}

`effect_for("Goryo's Vengeance", ...)` returns `delayed_notice_only`. That
records a `DelayedClauseNotice` and does nothing else - correct fail-closed
behaviour, but the practical result is that **Goryo's Vengeance reanimates
nothing**. The paragraph is one ability and resolves whole or fails closed, so
the third sentence - "Exile it at the beginning of the next end step", a delayed
triggered ability (CR 603.7a, created during the resolution of a spell; CR 610.2
for the one-shot effect that creates it; CR 603.7b for its once-only trigger) -
takes the first two sentences down with it.

**Missing primitive**: a delayed triggered ability the resolution of a spell can
create and hand to the turn structure, so that a reanimation clause and its
"exile it at the beginning of the next end step" rider are one effect. Until
that exists the whole archetype is inert: this is not a corner case, it is what
the deck does.

Sibling agents report Persist, Unearth and Archon of Cruelty are likewise
silent, so the shared Modern reanimator shell is dead across decks, not just
here.

### Genuinely silent spells

**Faithful Mending** `{W}{U}` Instant - **silent**.

> You gain 2 life, draw two cards, then discard two cards.
> Flashback {1}{W}{U}

`effect_for` returns `None`. The three-clause sequence gain-life / draw-N /
then discard-N is not read as one effect. Note that Flashback itself **is**
executed by the engine, so the card can be flashed back out of the graveyard and
will do nothing both times.

**Missing primitive**: a chained "gain N life, draw N, then discard N" spell
resolution (the "then" is ordering, not a separate ability).

**Spell Snare** `{U}` Instant, sideboard - **silent**.

> Counter target spell with mana value 2.

`effect_for` returns `None`. Countering itself is modelled - **Force of
Negation**, **Mystical Dispute** and **Consign to Memory** are all `handled` -
so the gap is narrow: the target predicate "spell with mana value 2" (CR 202.3)
is not readable, so no legal target is ever found and the counter (CR 701.6a)
never happens.

**Missing primitive**: a mana-value-equals-N restriction on a spell target.

---

## 2. Permanent gaps - trigger and activated layers, *not* registry work

These cards are permanents. Their gaps are in `machines/triggers.py` /
`trigger_effect_for`, not in the spell registry, and fixing `machines/effects.py`
would not touch them.

**Atraxa, Grand Unifier** `{3}{G}{W}{U}{B}` Legendary Creature - the whole card
is **silent**.

> Flying, vigilance, deathtouch, lifelink
> When Atraxa enters, reveal the top ten cards of your library. For each card
> type, you may put a card of that type from among the revealed cards into your
> hand. Put the rest on the bottom of your library in a random order.

Both the top-level dispatch and the enters-the-battlefield trigger come back
`None`. The four keywords are all executed, so a resolved Atraxa is a 7/7 flier
that draws nothing. Since Atraxa is the target Goryo's Vengeance wants to
reanimate, this and the Goryo gap compound: even if the reanimation worked, the
payoff would be blank.

**Missing primitive**: reveal-top-N, then a per-card-type optional selection out
of the revealed set (CR 205.2a / 300.1 enumerate the card types), with the
remainder going to the bottom in random order.

**Nihil Spellbomb** `{1}` Artifact, sideboard - card is `handled`, but **one
clause is silent**.

- `{T}, Sacrifice this artifact: Exile target player's graveyard.` - handled.
- `When this artifact is put into a graveyard from the battlefield, you may pay
  {B}. If you do, draw a card.` - **silent**. This is a leaves-the-battlefield
  ability (CR 603.6c, and CR 603.10a for its look-back timing).

**Missing primitive**: an optional mana payment inside a triggered ability's
resolution, gating a follow-on effect ("you may pay {B}. If you do, ...").

---

## 3. `no_rules_text` - what is actually behind it

`no_rules_text` is **not** a synonym for covered. Six cards land there. Three of
them are genuinely nothing; three are lands whose real text is owned by another
subsystem, and that subsystem was checked rather than assumed.

- **Island, Plains, Swamp** - basic lands, intrinsic mana ability only. A mana
  ability does not go on the stack (CR 605.3b), so no dispatcher is ever asked
  about one. Nothing to model.
- **Watery Grave, Godless Shrine, Hallowed Fountain** - each reads
  "As this land enters, you may pay 2 life. If you don't, it enters tapped."
  This is a replacement effect (CR 614.1c), and the choice is made before the
  land enters (CR 614.12a). **Verified covered**:
  `parse_replacement_effects` returns `as_enters` + `enters_tapped` for all
  three, and `unparsed_effects` is empty for all three. This is not a Mox Opal
  case.

### Statics excluded from the audit - one is a real gap

`has_rules_text` deliberately skips a permanent's static lines, since they
belong to subsystems this survey does not audit. Two such lines in this deck
were checked by hand:

- **Teferi, Time Raveler** - "Each opponent can cast spells only any time they
  could cast a sorcery." **Covered**, by
  `machines/casting_restrictions.py` (which matches this exact sentence).
- **Quantum Riddler** - "As long as you have one or fewer cards in hand, if you
  would draw one or more cards, you draw that many cards plus one instead."
  **Gap.** `parse_replacement_effects` returns this line with kind `unparsed`
  and it shows up in `unparsed_effects`. The card classifies as `handled` purely
  on its "When this creature enters, draw a card." trigger, so its actual
  standout ability - the conditional draw replacement - is silently absent.
  Missing primitive: a hand-size-conditioned draw-replacement effect - an
  "instead" replacement effect (CR 614.1a).

---

## 4. Keywords with no execution path

Three keyword/ability-word occurrences in this deck have nothing acting on them:

| Card | Keyword | Note |
|---|---|---|
| Consign to Memory | **Replicate** | CR 702.56a - a static ability on the stack plus a triggered ability that copies the spell. Not executed; the spell resolves as a single copy. |
| Goryo's Vengeance | **Splice** | CR 702.47a - reveal from hand as you cast an Arcane spell, add this card's text to it. Not executed. Moot for now, since the card's own text is already dead. |
| Prismatic Ending | **Converge** | An ability word (CR 207.2c: ability words have no rules meaning), so nothing is *supposed* to execute the word - but the clause it introduces is the problem, below. |

Everything else in the deck has a path: Flashback, Rebound, Evoke, Flash, Warp,
Flying, Lifelink, Deathtouch, Vigilance all report as executed.

## 5. Unreadable targeting

One phrase `machines/targeting.py` could not read:

- **Prismatic Ending** - "Converge - Exile target nonland permanent if its mana
  value is less than or equal to the number of colors of mana spent to cast this
  spell." The card classifies `handled` at X=0 and X=3, but the colors-spent
  bound on the target is not read, so the restriction is not enforced.

---

## Summary of what would have to be built

1. Delayed triggered abilities created by a resolving spell (CR 603.7a, 610.2) -
   unblocks Goryo's Vengeance and the wider reanimator shell. **Highest value.**
2. Reveal-N-then-select-one-per-card-type (Atraxa).
3. Mana-value-equals-N target restriction (Spell Snare).
4. Gain-life / draw-N / then discard-N chained resolution (Faithful Mending).
5. Optional mana payment inside a triggered ability (Nihil Spellbomb).
6. Hand-size-conditioned draw replacement (Quantum Riddler).
7. Replicate (CR 702.56a) and Splice (CR 702.47a) execution.
8. Converge's colors-spent bound in targeting (Prismatic Ending).

Nothing here was implemented; `machines/effects.py` was not edited.

### CR numbers cited, all verified this session with `knowledge_search`

100.2a, 100.4a, 103.3, 103.5, 202.3, 205.2a, 207.2c, 300.1, 305.1, 603.6c,
603.7a, 603.7b, 603.10a, 605.3b, 610.2, 614.1a, 614.1c, 614.12a, 701.6a,
702.47a, 702.56a.
