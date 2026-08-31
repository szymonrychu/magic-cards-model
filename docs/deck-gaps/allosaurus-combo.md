# Effect gaps: Modern allosaurus combo

The deck: **pilot E_Kaminuma, 2026-08-28**, source deck `videre-58654931`, sixty
and fifteen, written to `magic-cards-model-api/decks/allosaurus_combo.txt`.
Legality checked with `resolve_cards(format="modern", fields="legality")`: all
33 distinct names legal. Smoke test at
`tests/scenarios/test_allosaurus_combo_deck.py`.

Measured with `scripts/survey_cards.py --deck`, which runs the production
dispatchers (`effect_for`, `trigger_effect_for`, `activated_effect_for`) per
ability, not `EFFECTS` membership. Every verdict below that says "does nothing"
was then **played through the engine** and the board state checked, because the
per-ability read has known false positives (see the last section).

| bucket | count |
|---|---|
| handled | 16 |
| notice (fails closed) | 1 |
| **silent** | **12** |
| no rules text | 4 |

## Does the combo function? No.

The archetype's turn-one draw is: pitch-cast Allosaurus Rider for two green
cards (CR 118.9), then sacrifice it to Neoform or Eldritch Evolution and fetch
Griselbrand or Atraxa. Three of the four links work; the fourth is missing, and
it is the one that wins.

| link | state |
|---|---|
| Allosaurus Rider's CR 118.9 alternative cost - "exile two green cards from your hand rather than pay this spell's mana cost" | **works.** `machines/cost.py::alternative_cost_offers` reads the printed line, `Casting.use_alternative_cost` announces it, the two cards go to exile and the Rider resolves for no mana. |
| Allosaurus Rider's P/T - "each equal to 1 plus the number of lands you control" | **works.** A characteristic-defining ability in layer 7a (CR 613.4a, 208.2a); `game.power_of` returns 3 on two lands. |
| Summoner's Pact - {0} tutor plus "at the beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose the game" | **works, both halves.** CR 701.23 search, CR 701.24b shuffle, and a real CR 603.7 delayed triggered ability that ends the game (CR 104.3e, 104.5) when nothing pays it. |
| **Neoform / Eldritch Evolution - "search your library for a creature card with mana value ... put that card onto the battlefield, then shuffle"** | **silent.** The spell resolves, no search is offered, no decision is asked, the library is untouched, and the spell goes to the graveyard. Verified on a board with Griselbrand on top. |

So the deck can pitch a Rider onto an empty board on turn one and then has no
way to convert it. Every fatty in the list (Griselbrand, Atraxa, Ureni, Ghalta,
Xenagos) is reachable only through Neoform, Eldritch Evolution, or a hard cast,
and **each of those fatties' own payoff text is also silent** (below). The
archetype is dead end to end, not merely missing its last step.

One further gap on the same path, not counted as silent: Neoform's and Eldritch
Evolution's printed **additional** cost, "as an additional cost to cast this
spell, sacrifice a creature" (CR 118.8a), is readable by
`machines/cost.py::additional_cost_phrases` but is not applied automatically at
announcement - `Casting.add_additional_cost` has to be called by hand. In the
probe above Neoform was cast and resolved **without sacrificing anything**.

## Silent spells (nonpermanent resolution text with no effect)

| card | oracle text | missing primitive |
|---|---|---|
| Neoform `{G}{U}` | "Search your library for a creature card with mana value equal to 1 plus the sacrificed creature's mana value, put that card onto the battlefield with an additional +1/+1 counter on it, then shuffle." | search-by-computed-mana-value into play (CR 701.23, 701.24b); no way to read back the sacrificed creature's mana value from the additional cost |
| Eldritch Evolution `{1}{G}{G}` | "Search your library for a creature card with mana value X or less, where X is 2 plus the sacrificed creature's mana value. Put that card onto the battlefield, then shuffle. Exile Eldritch Evolution." | same search primitive, plus "exile this spell instead of putting it in the graveyard" as a resolution clause |
| Planar Genesis `{G}{U}` | "Look at the top four cards of your library. You may put a land card from among them onto the battlefield tapped. If you don't, put a card from among them into your hand. Put the rest on the bottom of your library in a random order." | look-at-top-N with an **either/or** branch (a land into play tapped, else any card to hand); the existing top-N family handles reveal-and-take, not this two-way choice |
| Veil of Summer `{G}` | "Draw a card if an opponent has cast a blue or black spell this turn. Spells you control can't be countered this turn. You and permanents you control gain hexproof from blue and from black until end of turn." | a conditional draw keyed on an opponent's cast history this turn; a "can't be countered" continuous effect over spells you control; granting CR 702.11d hexproof-from-[quality] to a **player and their permanents** at once |
| Bridgeworks Battle `{2}{G}` (front face of an MDFC) | "Target creature you control gets +2/+2 until end of turn. It fights up to one target creature you don't control." | **fight** (CR 701.14a) - no execution path anywhere; also the pump-then-fight sequencing on two separate targets |
| Into the Flood Maw `{U}` (sideboard) | "Gift a tapped Fish ... Return target creature an opponent controls to its owner's hand. If the gift was promised, instead return target nonland permanent an opponent controls to its owner's hand." | **gift** (CR 702.174a/b/k) - the promise is never offered, so neither the token nor the gift-conditional second mode exists |

## Silent permanents, triggers and layers

Kept separate from the spells above: these are abilities on the battlefield, not
resolution text.

| card | ability | missing primitive |
|---|---|---|
| Ghalta, Stampede Tyrant | "When Ghalta enters, put any number of creature cards from your hand onto the battlefield." | put-any-number-of-cards-from-hand-into-play. Probed: Griselbrand and Endurance stayed in hand, no decision asked. |
| Atraxa, Grand Unifier | "When Atraxa enters, reveal the top ten cards of your library. For each card type, you may put a card of that type from among the revealed cards into your hand. Put the rest on the bottom of your library in a random order." | reveal-N-then-take-one-per-**card type**; the per-type loop has no primitive. Probed: hand empty, library untouched. |
| Ureni, the Song Unending | "When Ureni enters, it deals X damage divided as you choose among any number of target creatures and/or planeswalkers your opponents control, where X is the number of lands you control." | X read from a board count on a **triggered** ability, and divided damage. Probed: targets *were* asked for (targeting parses), then 0 damage was dealt - the division is the known CR 601.2d gap already tracked in `tests/scenarios/test_damage_division.py`. |
| Xenagos, God of Revels | "At the beginning of combat on your turn, another target creature you control gains haste and gets +X/+X until end of turn, where X is that creature's power." | X read from the **target's own** power; also the static "as long as your devotion to red and green is less than seven, Xenagos isn't a creature" (CR 700.5) is a type-changing layer effect with no parser. |
| Thundertrap Trainer (sideboard) | "When this creature enters, look at the top four cards of your library. You may reveal a noncreature, nonland card from among them and put it into your hand. Put the rest on the bottom of your library in a random order." | look-at-top-N with a **negated compound** card-type filter ("noncreature, nonland") |
| Abhorrent Oculus (sideboard) | "At the beginning of each opponent's upkeep, manifest dread." | **manifest dread** (CR 701.62a) and **manifest** (CR 701.40a) - no execution path; a face-down 2/2 from the top of the library does not exist |

## Keywords with no execution path

Six occurrences across five keywords, from `sweep_pool.ignored_keywords`:

| keyword | on | CR |
|---|---|---|
| Fight | Bridgeworks Battle | 701.14a |
| Replicate | Consign to Memory | 702.56a (the card itself is otherwise handled - the counter half works, the copies do not) |
| Offspring | Thundertrap Trainer | 702.175a |
| Gift | Into the Flood Maw | 702.174a |
| Manifest / Manifest dread | Abhorrent Oculus | 701.40a / 701.62a |

Keywords in the deck that **do** have an execution path: Delve (CR 702.66a, via
`machines/objects_as_costs.py`), Trample (CR 702.19b, `machines/combat.py`),
Reach, Flash, Flying, Vigilance, Deathtouch, Lifelink, Indestructible,
Forestcycling, Evoke (CR 702.74a, `machines/casting.py`), Channel, Protection
(CR 702.16a, enforced in `models/game.py`).

## The `no_rules_text` bucket, hand-audited

Four cards landed there. `sweep_pool.has_rules_text` skips every static line on
a permanent, so this bucket is **not** a coverage claim. Split three ways:

**Genuinely empty** - nothing to model.

- **Forest**, **Island**. Basic lands; their mana ability is intrinsic to the
  basic land type (CR 305.6) and the payment path taps them.

**Static text modelled elsewhere** - a real mechanism, owned by another machine.

- **Breeding Pool** - "As this land enters, you may pay 2 life. If you don't,
  it enters tapped." A CR 614.1c / 614.12 replacement effect, implemented in
  `machines/replacement.py` (`_PAY_LIFE_CHOICE` plus its "if you don't" half).
- **Hooting Mandrills** - Delve and Trample, both keywords with real execution
  paths (CR 702.66a in `machines/objects_as_costs.py`, CR 702.19b in
  `machines/combat.py`). Nothing else is printed on it.

**Static text that is unmodelled** - none in this deck.

Two land faces on modal double-faced cards in the list carry the same shockland
replacement and are covered the same way: **Tanglespan Bridgeworks** (back of
Bridgeworks Battle) and **Garden of Freyalise** (back of Disciple of Freyalise),
both "As this land enters, you may pay 3 life. If you don't, it enters tapped."
Their *front* faces are judged separately above.

## Cards that work

Handled, verified by the dispatchers and not disputed here: Allosaurus Rider
(alternative cost plus CDA), Summoner's Pact, Pact of Negation, Preordain,
Consign to Memory (the counter, not the replicate), Mystical Dispute, Endurance
(the graveyard-to-library ETB), Generous Ent, Disciple of Freyalise, Griselbrand
("Pay 7 life: Draw seven cards"), Boseiju Who Endures (channel), Hedge Maze
(enters tapped, surveil 1), Misty Rainforest, Scalding Tarn, Wooded Foothills,
Elesh Norn Grand Cenobite (both anthem layers).

Nature's Claim is the single **notice**: the engine recognises the text and
fails closed rather than guessing, which is correct behaviour, not a gap.

## False positives in the per-ability read

Worth recording, because measuring per ability over-reports in one specific
shape. `parse_abilities` yields the Pact cycle's second paragraph - "At the
beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose the game" -
as a card-level triggered ability, and `trigger_effect_for` has no row for it,
so it reads as **silent** on both Summoner's Pact and Pact of Negation. It is
not. That paragraph is part of the *spell's* resolution, which creates a CR
603.7 delayed trigger via `machines/effects.py::_parse_delayed_pay_or_lose_
clauses`, and the game really does end for a player who cannot pay. Verified by
playing it. Neither card is counted as a gap above.

The same applies to Allosaurus Rider's own first line: the CR 118.9 alternative
cost reads as a silent spell-level clause because `effect_for` does not own it -
`machines/cost.py` does, and it works.

## CR numbers cited here

Every one looked up with `knowledge_search(type="rules")` in the session that
wrote this file: 100.2a, 100.4a, 103.2a, 103.3, 103.5, 104.3e, 104.5, 118.8a,
118.9, 118.9b, 118.9c, 208.2a, 305.6, 401.1, 601.2d, 603.7, 603.7a, 610.2,
613.4a, 700.5, 701.14a, 701.23, 701.24b, 701.40a, 701.62a, 702.11d, 702.16a,
702.19b, 702.56a, 702.66a, 702.74a, 702.174a, 702.174b, 702.174k, 702.175a,
614.1c, 614.12.
