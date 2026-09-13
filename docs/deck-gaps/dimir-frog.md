# Dimir frog - effect gaps

The deck: pilot **SizzleSkeleton**, tournament **2026-08-30**, source deck
**videre-58656338**. Registered list, 60 + 15, every
name a real Scryfall printing in `tests/fixtures/cards`. Decklist file lives at
`decks/dimir_frog.txt` in the api repo; the smoke test is
`tests/scenarios/test_dimir_frog_deck.py`. Roughly 1.6% of the Modern metagame.

## How this was measured

Not by `EFFECTS` membership - that over-reports badly, because `effect_for`,
`trigger_effect_for` and `activated_effect_for` all fall back to text parsers
and a card with no registry row of its own can still work end to end.

Every row below comes from running the production dispatchers per **ability**:
`parse_abilities(printing)` for the clause list, then the dispatcher
`models/game.py` would actually call for that clause shape, and the answer is a
gap only when the dispatcher returned `None`. That is exactly what
`scripts/survey_cards.py --deck` does at card level (`classify_card` reports the
*best* outcome anywhere on a card), so this file adds the per-clause
breakdown the card-level table hides.

Card-level totals for the 33 distinct names:

| category | count |
|---|---|
| handled | 21 |
| notice (fail-closed) | 0 |
| silent | 7 |
| no_rules_text | 5 |

Nothing here was implemented or registered - `machines/effects.py` was not
touched.

Rules cited below were looked up with `knowledge_search` in the session that
wrote this file: CR 100.2a, CR 100.4a, CR 111.10f, CR 305.7, CR 402.1,
CR 402.2, CR 606.3, CR 614.7, CR 700.2, CR 700.2a, CR 701.16a, CR 701.27a,
CR 701.47a, CR 702.44a, CR 702.49a, CR 702.56, CR 702.138a, CR 702.185a.
Revolt is the one thing here with no CR number: `knowledge_search` returned no
rules entry for it, so it is left uncited rather than guessed at.

---

## 1. Spell gaps - a nonpermanent spell's own resolution text returns `None`

### Countering with a mana-value bound

**Spell Snare** - `{U}` instant.
Oracle: "Counter target spell with mana value 2."
`effect_for("Spell Snare", ...)` is `None`. Countering itself is fine -
Counterspell, Force of Negation, Mystical Dispute and Consign to Memory are all
handled - so the missing primitive is narrow: **a counter effect whose legal
target is bounded by the target spell's mana value**. Probed directly, both
"mana value 2" and "mana value 2 or less" return `None`, so it is the numeric
bound, not the equality wording.

### A retrospective conditional about the object the spell just moved

**Cling to Dust** - `{B}` instant.
Oracle: "Exile target card from a graveyard. If it was a creature card, you gain
3 life. Otherwise, you draw a card." plus "Escape—{3}{B}, Exile five other cards
from your graveyard."
`effect_for` is `None` for the full text. Probed clause by clause, "Exile target
card from a graveyard." **alone is handled**; adding "If it was a creature card,
..." kills it. Missing primitive: **a condition that inspects the characteristics
of the object this same effect just moved to another zone, branching into two
different outcomes**. Escape (CR 702.138a) is separately unmodelled - see the
keyword section.

### A keyword line sitting under otherwise-readable resolution text

**Lórien Revealed** - `{4}{U}` sorcery.
Oracle: "Draw three cards." + "Islandcycling {1} (...)".
`effect_for` is `None` for the printed text, but `effect_for("Lórien Revealed",
"Draw three cards.")` **is handled**. The islandcycling line is what makes the
spell silent: the spell-level dispatcher is handed the whole oracle text and
does not separate a keyword-ability line from the spell's own resolution text.
Missing primitive: **strip keyword-ability lines before spell dispatch** (or the
same `_spell_faces`-style split `classify_card` already does for faces). Note
islandcycling itself *is* executed (`machines/keywords.py`) - this is purely the
dispatcher's text handling, and it is the cheapest fix in this file.

---

## 2. Permanent and trigger-layer gaps

Separate section deliberately: a permanent spell resolving means "it enters the
battlefield", so `effect_for` returning `None` on a creature or planeswalker is
not itself a defect. Everything below is a *triggered*, *activated* or *static*
clause that produced nothing.

### Orcish Bowmasters - `{1}{B}` creature, 2 copies

Oracle: "Flash. When this creature enters and whenever an opponent draws a card
except the first one they draw in each of their draw steps, this creature deals
1 damage to any target. Amass Orcs 1."

The trigger dispatches to `None`. Two missing primitives:
- **a single triggered ability with two conditions (ETB *and* an opponent-draw
  watcher) carrying an exception clause** ("except the first one they draw in
  each of their draw steps");
- **amass** (CR 701.47a: create a 0/0 black Army token if you control none, then
  put N +1/+1 counters on an Army you control). Amass is also in the
  no-execution-path keyword list.

Flash is executed (`machines/casting.py` timing); the damage half is not reached
because the trigger never resolves into an effect.

### Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar - `{U}`, 2 copies

Front face:
- "Whenever Tamiyo attacks, investigate." - trigger dispatches to `None`.
  Missing primitive: **investigate** (CR 701.16a: create a Clue token; CR 111.10f
  defines the Clue token as a colorless Clue artifact token with "{2}, Sacrifice
  this token: Draw a card"). Token creation plus a granted activated ability.
- "When you draw your third card in a turn, exile Tamiyo, then return her to the
  battlefield transformed under her owner's control." - `machines/triggers.py`
  cannot read the condition at all (`event is None`), so it never fires in a real
  game. Two missing primitives: **a per-turn draw counter as a trigger condition**,
  and **transform** (CR 701.27a: turn the permanent over so its other face is up).

Back face (Tamiyo, Seasoned Scholar) - all three loyalty abilities (CR 606.3)
dispatch to `None`:
- "+2: Until your next turn, whenever a creature attacks you or a planeswalker
  you control, it gets -1/-0 until end of turn." - a delayed, duration-bounded
  attack-watching trigger.
- "−3: Return target instant or sorcery card from your graveyard to your hand.
  If it's a green card, add one mana of any color."
- "−7: Draw cards equal to half the number of cards in your library, rounded up.
  You get an emblem with 'You have no maximum hand size.'" - needs an **emblem**
  primitive and a computed magnitude.

Since the transform trigger never fires, the back face is unreachable in play
regardless.

### Kaito, Bane of Nightmares - `{2}{U}{B}` planeswalker, 1 copy

- Static: "During your turn, as long as Kaito has one or more loyalty counters
  on him, he's a 3/4 Ninja creature and has hexproof." - parsed as a static
  ability, no layer machine reads it. Missing primitive: **a conditional,
  turn-restricted type-and-P/T-setting continuous effect on a planeswalker**.
- "+1: You get an emblem with 'Ninjas you control get +1/+1.'" - `None`.
  **Emblem** primitive missing.
- "0: Surveil 2. Then draw a card for each opponent who lost life this turn." -
  `None`. Surveil alone is handled elsewhere (Undercity Sewers works); the
  missing piece is **a count of opponents who lost life this turn** as a draw
  magnitude.
- "−2: Tap target creature. Put two stun counters on it." - `None`. Missing
  primitive: **stun counters**.
- **Ninjutsu** (CR 702.49a) has no execution path - see keywords.

### Murktide Regent - `{5}{U}{U}` creature, 1 copy

- "This creature enters with a +1/+1 counter on it for each instant and sorcery
  card exiled with it." - static, unread. Missing primitive: **counters on entry
  counted from the cards exiled to pay delve for this same spell** (the
  "exiled with it" linkage).
- "Whenever an instant or sorcery card leaves your graveyard, put a +1/+1 counter
  on this creature." - `machines/triggers.py` cannot read the condition
  (`event is None`), so it never fires. Missing primitive: **a leaves-a-graveyard
  zone-change trigger**.

Delve itself is executed (`machines/keywords.py`), so the creature can be cast
cheaply; it just enters as a 0/0 and dies, since neither counter source works.

### Quantum Riddler - `{1}{U}{U}` creature, 4 copies

- ETB "draw a card" trigger: **handled**.
- "As long as you have one or fewer cards in hand, if you would draw one or more
  cards, you draw that many cards plus one instead." - static, unread. Missing
  primitive: **a conditional draw-replacement effect** (CR 614.7 and the
  replacement machinery generally); this is the card's whole point in the deck.
- Warp (CR 702.185a) *is* executed (`machines/casting.py`).

### Nihil Spellbomb - `{1}` artifact, sideboard

- "{T}, Sacrifice this artifact: Exile target player's graveyard." - **handled**.
- "When this artifact is put into a graveyard from the battlefield, you may pay
  {B}. If you do, draw a card." - trigger dispatches to `None`. Missing
  primitive: **an optional mana payment made during a triggered ability's
  resolution, gating a follow-on effect**.

### Engineered Explosives - `{X}` artifact, sideboard

- "{2}, Sacrifice this artifact: Destroy each nonland permanent with mana value
  equal to the number of charge counters on this artifact." - **handled**.
- But **sunburst** (CR 702.44a: enters with a charge counter for each color of
  mana spent to cast it) has no execution path, so the artifact always enters
  with zero counters and the handled ability always destroys mana value 0. The
  card is "handled" and still wrong in play - worth flagging as a false green.

### Harbinger of the Seas - `{1}{U}` creature, 3 copies in the board

Classified `no_rules_text` (see section 3) because its only ability is the static
"Nonbasic lands are Islands." (CR 305.7: setting a land's subtype to a basic land
type makes it lose its old types and abilities and gain the new mana ability).
No layer machine reads it, so the card does nothing at all. Missing primitive:
**a global land-subtype-setting continuous effect**.

### Confirmed working at the permanent layer

Recorded so the next survey does not re-litigate them: **Psychic Frog** (combat
damage trigger, both activated abilities, and the layer effect - all handled),
**Subtlety** (ETB trigger handled, evoke executed), **Undercity Sewers** (ETB
surveil handled), **Otawara, Soaring City** (mana ability plus the channel
activated ability, both handled), **Polluted Delta / Scalding Tarn / Verdant
Catacombs** (fetch activations handled), **Sink into Stupor // Soporific
Springs** (both faces handled).

---

## 3. `no_rules_text` - counted as NOT covered

Five names. `has_rules_text` is `False` for each, so `classify_card` never asked
a dispatcher about them.

| card | why it lands here |
|---|---|
| Island | basic land, genuinely nothing to model |
| Swamp | basic land, genuinely nothing to model |
| Darkslick Shores | its "enters tapped unless you control two or fewer other lands" is a `machines/replacement.py` line; `has_rules_text` skips a permanent's static line. Mana ability handled. |
| Watery Grave | same shape: "As this land enters, you may pay 2 life. If you don't, it enters tapped." Not an `effects.py` gap, but not audited by this tool either. |
| Harbinger of the Seas | **real gap.** Its only ability is the static "Nonbasic lands are Islands." (CR 305.7) and nothing reads it. See section 2. |

The two basics are fine. The two shocklands/fastlands belong to a subsystem this
survey does not audit and need a separate check. Harbinger of the Seas is a
genuine silent card hiding in this bucket - do not read `no_rules_text` as
"covered".

---

## 4. Keywords with no execution path

Measured with `executed_keywords` / `ignored_keywords`, seven occurrences across
the 33 names:

| keyword | on | CR | what is missing |
|---|---|---|---|
| Escape | Cling to Dust | 702.138a | casting a card from the graveyard for an alternative cost that exiles other graveyard cards |
| Amass | Orcish Bowmasters | 701.47a | Army token creation + counter placement |
| Investigate | Tamiyo, Inquisitive Student | 701.16a / 111.10f | Clue token creation |
| Ninjutsu | Kaito, Bane of Nightmares | 702.49a | activated ability from hand that returns an unblocked attacker and puts this onto the battlefield attacking |
| Sunburst | Engineered Explosives | 702.44a | counters on entry keyed to colors of mana spent |
| Replicate | Consign to Memory | 702.56 | copy the spell per replicate cost paid (the spell's counter half is handled) |
| Revolt | Fatal Push | not confirmed - `knowledge_search` returned no CR entry for revolt in this session | the "a permanent left the battlefield under your control this turn" check (the base destroy is handled) |

Keywords in this deck that **do** have an execution path, so they are not gaps:
Flying, Flash, Evoke, Delve, Warp, Channel, Cycling / Landcycling / Typecycling /
Islandcycling, Surveil, Transform-as-a-keyword.

---

## 5. Cross-check against the sibling dimir-control survey

An independent second measurement, not a repeat. Their findings against mine:

| their claim | my measurement | verdict |
|---|---|---|
| Spell Snare silent | `effect_for` is `None` | **confirmed** |
| Cling to Dust silent | `effect_for` is `None` | **confirmed** |
| Sink into Stupor silent | `[spell] handled` on the instant face, mana ability handled on the land face | **contradicted** |
| Stern Scolding silent | not in this list | not measured |
| Subtlety: no trigger row | ETB trigger dispatches to a real effect - **handled** | **contradicted** |
| Quantum Riddler: no trigger row | ETB draw trigger **handled**; the *static* draw-replacement is the real gap | **contradicted** (the gap is real, but it is static, not a trigger) |
| Orcish Bowmasters: no trigger row | trigger dispatches to `None` | **confirmed** |
| Harbinger of the Seas: no trigger/activated row | correct - it has neither; it is a static that nothing reads, filed under `no_rules_text` | **confirmed** (right conclusion, wrong layer) |
| Engineered Explosives: no activated row | activated ability **handled**; sunburst is what is broken | **contradicted** (the card is still wrong in play) |
| Tamiyo: no trigger/activated row | both triggers and all three loyalty abilities dispatch to `None` | **confirmed** |
| Kaito: no trigger/activated row | all three loyalty abilities dispatch to `None`; static unread | **confirmed** |
| escape unmodelled | `ignored_keywords` reports Escape | **confirmed** |
| ninjutsu unmodelled | `ignored_keywords` reports Ninjutsu | **confirmed** |
| warp unmodelled | `executed_keywords` maps warp to `machines/casting.py` | **contradicted** |
| evoke unmodelled | `executed_keywords` maps evoke to `machines/casting.py` | **contradicted** |
| channel unmodelled | Otawara's channel ability classifies **handled** | **contradicted** |

The pattern in the contradictions is the one the brief warned about: measuring
by registry membership calls a card dead when a text parser is quietly handling
it. Every "contradicted" row above is a card with no `EFFECTS` entry that works
anyway.
