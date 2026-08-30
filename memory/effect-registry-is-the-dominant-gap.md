---
name: effect-registry-is-the-dominant-gap
description: Most cards resolve and do nothing because effects are keyed by card name - the measured survey, the per-deck dead-card counts, and the ranked order of work
metadata:
  type: project
---

A full-pool survey (2026-08-29, ~324 fixtures) established that the dominant
defect in this engine is not any individual rule but that **`machines/effects.py`
keys what a card does by CARD NAME**: 22 spell entries, 25 trigger entries and 6
activated entries for the whole pool. A card with no entry resolves, leaves the
stack, and changes nothing - silently, with no log or warning.

**Dead mainboard copies per deck** (of 60; lands' mana abilities excluded):
blink 43, living_end 37, creatures_toolbox 35, boros_energy 27, eldrazi_ramp 27,
urzatron 25. Aggregate: 63/85 instants+sorceries, 77/103 parsed triggers and
67/83 non-mana activated abilities have no effect.

**Ranked order of work** (cards unlocked per unit of effort):
1. Single-clause player effects - gain/lose N life, get {E}, draw N, mill/
   surveil/scry N. ~60 cards, every primitive already exists.
2. Targeted single-object verbs - destroy/exile/return-to-hand/deal N damage to
   target, tap/untap, +1/+1 counter on target. ~70 cards; targeting machinery
   exists.
3. Token creation parsed from text (`a 1/1 white Cat creature token`). 22 cards;
   `models/token.py` exists, the parsing is the work.
4. Multi-clause splitting on `.`/`and`/`then` - cheap, and multiplies 1-3.

**Traps that look easy and are not:** `you may` / `If you do,` (~47 clauses) need
a decision interface - the engine has nobody to ask; `create a token that's a
copy of` needs copiable values (CR 707); divided effects are chosen at
announcement, not resolution; `destroy all` needs simultaneous SBA handling;
modal spells need a per-mode effect key, a registry redesign.

**Not effect work, but blocks play anyway:** 11 triggers never fire because the
CONDITION is unparsed; and alternative-cost keywords (Cascade, Cycling, Evoke,
Rebound) are cost-machine work. **Living End is blocked on cost machinery, so it
is the wrong deck to prove anything on. boros_energy is the cheapest deck to make
playable** - 27 dead copies across 9 cards, 8 of which the first waves cover.

**Energy is not a missing primitive:** `Counter.ENERGY` and `Player.energy`
already exist and nothing writes them.

**There are THREE name-keyed registries, not one** (2026-08-29): `effects.py`'s
EFFECTS/TRIGGER_EFFECTS/ACTIVATED_EFFECTS, `layers.LAYER_EFFECTS`, and
`replacement.REPLACEMENTS`. The owner's instruction to parse abilities from
oracle text covers all three. The worst shape is in the replacement registry:
DDR#830 showed Mindskinner and Furnace of Rath **parse into real
`ReplacementKind` values** and still do nothing, because they have no row - the
parse is computed and thrown away.

**A name-keyed row masks the parser defect underneath it.** Every conversion
wave so far has exposed a bug the row was hiding - Static Prison's permanent
exile, Faerie Macabre's silent no-op, Chalice matching every cast, Sowing
Mycospawn's dropped intervening-if. The same is true of defensive guards: the
battlefield-only filter in `exile_ability_targets` was silently compensating for
`Game.legal_target` never rechecking an ability's target restriction on
resolution. **Deleting the workaround is how the real defect is found**, so
delete it and run, rather than reasoning about whether it still matters.

**The wiring precedent for every parser:** `parse_search_and_put_effect` -
`parse_X_effect(text) -> AbilityEffect | None`, tried only on a registry miss,
with a guard test that the registry does not shadow the parser, and the
subsumed registry rows deleted. Parsers must FAIL CLOSED: an effect with any
unparseable clause executes none of it, because a half-executed spell is a wrong
game state that looks right.

Related: [[autonomous-playtest-loop]], [[no-mocks-scenario-tests]],
[[verify-agent-findings-against-the-engine]].
