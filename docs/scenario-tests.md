# Scenario tests

Scenario tests set up a real board state and play it out through the model, one
mechanic at a time. They live in `tests/scenarios/` and use the harness in
`tests/scenarios/harness.py`.

They exist because the unit tests check a machine in isolation, which is not
where the interesting bugs are. A mechanic is only correct if it holds up
against a real card, in a real zone, at a real point in the turn.

The project is building a full rules engine, so these tests are the measure of
how much of the game actually works. Two things follow:

- **Check `docs/engine-coverage.md` first.** If the mechanic is listed as not
  modelled, the test is still worth writing - as `xfail` with a reason. That
  turns a gap into a tracked one instead of a silent one.
- **Look the rule up.** The `spellslinger` MCP server serves the Comprehensive
  Rules (`knowledge_search(q="...", type="rules")`) and judge transcripts
  (`reveries_search(q="...")`). Cite the CR number in the test docstring. See
  `docs/mcp-tools.md`.

## What a scenario test is for

**One mechanic per file.** `test_cast_a_creature.py` covers the path a permanent
spell takes from library to battlefield. A file about first strike covers first
strike. Do not build a file that plays out a whole game touching nine mechanics -
when it breaks, nobody can tell what broke.

Existing files, as a guide to where a new case belongs:

| File | Mechanic |
|---|---|
| `test_cast_a_creature.py` | A permanent spell from library to battlefield, and paying for it |
| `test_turn_cycle.py` | The turn passing between players; what resets, what untaps |
| `test_priority.py` | CR 117: who may act and when, and what a round of passes causes |
| `test_special_actions.py` | Playing a land: no stack, no priority window, one per turn |
| `test_stack.py` | CR 608 last-in-first-out resolution, counterspells included |
| `test_removal.py` | Damage, and the state-based action that destroys a creature |
| `test_damage_to_players.py` | Damage aimed at a player, life totals, and losing the game at zero |
| `test_exile.py` | Exile as distinct from the graveyard |
| `test_declaring_attackers.py` | CR 508: who may attack, what it taps, what may be attacked |
| `test_summoning_sickness.py` | CR 302.6, 508.1a: how long a creature has been here, and haste |
| `test_declaring_blockers.py` | CR 509: block legality, and what stays true once declared |
| `test_combat_damage.py` | CR 510: assignment, simultaneity, and winning by damage |
| `test_first_strike.py` | CR 702.7, 702.4, 510.4: the extra combat damage step |
| `test_evasion.py` | CR 702.9, 702.17, 702.111, 702.19: flying, reach, menace, trample |
| `test_evasion_restrictions.py` | CR 509.1a: a plain "can't be blocked [by creatures with power N or less]" restriction, read off the attacker's own text rather than a keyword |
| `test_turn_based_actions.py` | CR 703: what a step does by itself - untap, draw, cleanup |
| `test_state_based_actions.py` | CR 704: 0 toughness, the empty library, the legend rule |
| `test_triggered_abilities.py` | CR 603: what triggers, when it goes on the stack, APNAP order, the intervening *if* |
| `test_activated_abilities.py` | CR 602: activating, paying the cost, restrictions, and the mana ability that skips the stack |
| `test_multiplayer.py` | CR 800: three players, turn order, and leaving the game |
| `test_ward.py`, `test_prowess.py`, `test_cascade.py`, `test_persist.py`, `test_mobilize.py` | CR 702 keywords that *are* triggered abilities, generated from the keyword line |
| `test_morph.py` | CR 702.37, 708.2: a card cast face down, and what it is while it is |
| `test_madness.py` | CR 702.35: a discard replaced into exile, and casting from that pile |
| `test_play_from_exile.py` | CR 601.3, 601.1a, 514.2: a resolving ability's time-boxed permission to play *specific* exiled cards - Ugin's −11 and Ragavan's trigger - against `test_madness.py`'s static, keyword-driven grant |
| `test_indestructible.py` | CR 702.12: what "can't be destroyed" does and does not stop |
| `test_exert.py` | CR 701.43: not untapping next untap step, once |
| `test_enchant.py` | CR 702.5, 303.4a: what an Aura may target and be attached to |
| `test_entwine.py` | CR 702.42: every mode, for an additional cost |
| `test_dash.py` | CR 702.109: an alternative cost that is dearer than the printed one |
| `test_counters.py` | CR 122: counters on permanents and players, annihilation, loyalty, layer 7c |
| `test_decisions_during_resolution.py` | CR 608.2d: a resolving effect asking its controller something, and what is not a legal option |
| `test_scry.py` | CR 701.22: scry, and scry 0 not being a scry |
| `test_surveil.py` | CR 701.25: surveil, and the graveyard being a zone change |
| `test_shuffling.py` | CR 701.23, 701.24: searching a hidden zone, and randomizing what is left |
| `test_prevention_effects.py` | CR 615: prevention shields, the damage source, and protection's damage half |
| `test_protection_grants.py` | CR 613.1f, 702.16a, 702.16e, 702.16g: protection *granted* by another permanent's static ability (Akroma's Memorial), as opposed to `test_protection.py`'s printed-on-itself Emrakul |
| `test_tokens.py` | CR 111: what a token is, CR 111.8's refused move, CR 704.5d ceasing to exist |
| `test_token_creation_replacement.py` | CR 701.7b: replacing a token *being created*, and Doubling Season's token half |
| `test_role_tokens.py` | CR 111.10k, 303.7, 704.5z: Roles, and the two state-based actions that police them |
| `test_aura_attachment.py` | CR 704.5m: an Aura on an illegal object or on nothing, against CR 704.5n's Equipment |
| `test_alternative_costs.py` | CR 118.9: finding an alternative cost with `Casting.alternative_costs` and announcing it with `use_alternative_cost` - the printed pitch offer, a static grant from Omniscience, what a cost increase does on top, and the printed mana cost still being payable instead |
| `test_select_from_the_top_of_your_library.py` | CR 701.17a-c, 401.2, 608.2d, 609.3: the "mill or look at the top N, then optionally move one of them" family - one parsed shape across Ostrich-Horse, Ainok Wayfarer, Scout the City's mode and Fecund Greenshell, against `test_six.py`'s single card |
| `test_mana_spend_restrictions.py` | CR 106.6: "Spend this mana only to ..." - the restriction carried by mana in the pool, what it refuses, and which mana pays when both would |

### Counters

Counters live on `CardState.counters` and `Player.counters` (CR 122.1), keyed by
kind - `"+1/+1"`, `"loyalty"`, `"poison"`, or any name a card invents. Put them
on with `add_counters(kind, n)` and take them off with `remove_counters`, which
refuses to remove more than are there (CR 118.3). `CardState.power` and
`.toughness` already count them (CR 122.1a), and so does the layer engine, in
sublayer 7c (CR 613.4c).

Two state-based actions are counter-driven and are **not** dispatched by `Game`:
annihilation (CR 704.5q) and a planeswalker at zero loyalty (CR 704.5i). Call
`scenario.state_based_actions()` instead of `game.check_state_based_actions()`
in a scenario that needs them - it does both. A creature killed by its -1/-1
counters (CR 704.5f) needs neither, since its toughness already counts them.

**Corner cases are the point.** The happy path is one test at the top of the
file. The rest of the file should be the cases that expose whether the model got
the rules right:

- The cost that cannot be paid, and whether the rewind is clean
- Mana left floating after a payment, and what happens to it
- A card in the wrong zone, a permanent already tapped, an empty library
- Timing: sorcery speed in the wrong step, a spell cast with something on the
  stack
- The state a card loses when it changes zones

Each of those is a separate test with a name that says what it asserts. If a
test needs a comment to explain why the case is interesting, put it in the
docstring - future agents read those to decide whether the case is already
covered.

## Writing one

```python
from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_creature_reaches_the_battlefield():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Questing Beast", "Forest"],  # top of library first
            battlefield=["Forest", "Forest", "Sol Ring"],
        )
        .build()
    )

    scenario.start_at(Step.UPKEEP)
    scenario.advance()  # draw step
    scenario.draw()

    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Sol Ring")
    beast = scenario.cast_and_resolve("Questing Beast", *sources)

    assert beast.zone is Zone.BATTLEFIELD
```

### Building the board

`Scenario().player(...)` takes `life` and any of `library`, `hand`,
`battlefield`, `graveyard`, `exile`, each a list of card names. Library order is
top-first. Call `.player()` again for a second player. `.build()` returns a
`PlayedScenario`.

### Driving it

| Call | What it does |
|---|---|
| `start_at(step)` | Advance to a step, running the untap step if it is passed |
| `advance()` | One step forward; each step resets priority to the active player |
| `draw(n)` | Draw from the library into hand |
| `turn_based_actions()` | Run the current step's CR 703.4 actions once, by hand |
| `play_land(name)` | Special action: straight to the battlefield, no stack, no priority pass |
| `cast(name, targets=[...])` | Begin casting; returns the `Casting` mid-announcement |
| `pay_with(payment, *sources)` | Tap each source for mana and pay |
| `put_on_stack(casting)` | Finish casting; the caster keeps priority |
| `cast_onto_stack(name, *sources, targets=[...])` | Cast and leave it on the stack, unresolved |
| `resolve_top()` | Resolve the top of the stack, effect and all |
| `cast_and_resolve(name, *sources, targets=[...])` | All of the above, when nobody responds |

Use `cast_and_resolve` only when the middle steps are not what the test is
about. A test that cares about payment, responses, or the stack should drive the
parts itself, so the failure points at the step that broke. `cast_onto_stack` is
the one to reach for when the scenario is about what happens while a spell waits.

### Combat

| Call | What it does |
|---|---|
| `attack_with(*creatures, defending=...)` | Declare attackers (CR 508.1). `defending` defaults to the only opponent |
| `can_attack(creature, defending=...)` | Whether the declaration would be legal |
| `block(attacker, *blockers)` | Declare blockers on one attacker, in damage assignment order |
| `no_blocks()` | The defending player declares no blockers |
| `combat_damage()` | Run the damage step, or both of them if first strike is involved |
| `attackers()`, `blockers()` | The creatures currently in combat |
| `creature(name, username)` | A creature on the battlefield, narrowed to one controller |
| `creatures(*names, username=...)` | Distinct copies, in order |

An illegal declaration raises `ValueError` carrying the rule's reason, and
changes nothing - a refused attack leaves the creature untapped and out of
combat. `block` recombines with earlier `block` calls and rechecks the whole
declaration each time, which is what makes a lone blocker on a creature with
menace illegal (CR 702.111b).

`combat_damage()` returns the assignment as `(target, amount)` pairs, in the
order it was assigned, so a scenario can assert on how the damage was split
rather than only on what died.

Nothing drives these automatically: reaching `Step.DECLARE_ATTACKERS` does not
declare anything, because combat's turn-based actions (CR 703.4i, 703.4j) are
not modelled. A combat scenario calls the moves itself.

### Turn-based actions

By default `advance()` moves the step and nothing else, so a scenario drives
the draw step and the cleanup discard by hand. `Scenario().automatic_turn_based_actions()`
turns on the CR 703.4 actions the engine does implement - untap, draw, discard
to maximum hand size, wipe marked damage - and then `advance()` performs them
as each step begins, followed by state-based actions (CR 703.3, CR 704.3).

It is opt-in because most scenario boards have a short or empty library: an
automatic draw step would lose them the game on the spot (CR 104.3c). Reach for
it when the scenario is *about* the turn driving itself; otherwise leave it off
and call `draw()` where the scenario needs a card.

Note `start_at(step)` walks the turn machine directly and never performs
turn-based actions, whatever the flag says. Use repeated `advance()` when they
matter.

### Decisions made while an effect resolves

CR 608.2d lets a resolving spell or ability ask its controller a question, and
there is no player agent to answer. A scenario answers in advance; the answers
queue on the game and each is matched to the next question of its kind.

| Call | What it answers |
|---|---|
| `will_take_the_may(taken)` | The next plain "you may" |
| `will_pay_the_life(paid)` | The next "you may pay N life" (CR 119.4) |
| `scry_keeping_everything_on_top()` | The next scry, bottoming nothing (CR 701.22a) |
| `scry_bottoming(*cards, top_order=[...])` | The next scry, naming the cards by identity |
| `surveil_keeping_everything_on_top()` | The next surveil (CR 701.25a) |
| `surveil_to_graveyard(*cards, top_order=[...])` | The next surveil, naming what is binned |
| `top_of_library(n)` | The cards to name in the calls above |
| `questions_asked()` | Every question put so far, to assert one was *not* asked |

Each takes `username=`, `source=` (the card name asking) and `times=`
(`None` for "every one of them"). An answer that names an option CR 608.2d makes
illegal - paying 2 life at 1 life - raises rather than being silently corrected.

An unanswered question falls through to the default table documented in
`machines/decisions.py`: a "you may" is taken, a life payment is made when legal,
and a scry or surveil keeps everything on top. A scenario that cares says so.

### Priority

| Call | What it does |
|---|---|
| `priority_holder` | Who currently holds priority |
| `pass_priority(username)` | Pass; raises if that player does not hold it |
| `pass_until_resolved()` | Everyone passes, resolving the top of the stack |

Passing is what resolves things. A round of passes with a non-empty stack
returns `PriorityOutcome.RESOLVE_TOP` and resolves the top item; on an empty
stack it returns `END_STEP`, meaning the caller should `advance()`. Casting
resets the round and gives priority back to the caster, so a scenario that casts
in response does not need to count passes by hand.

### Inspecting it

| Call | What it returns |
|---|---|
| `find(name, zone)` | The first copy in a zone; raises listing the zone if absent |
| `untapped_sources(*names)` | Distinct untapped permanents, in order |
| `battlefield_names()` | Names on the battlefield |
| `player(username)` | A `Player`, defaulting to the active one |
| `scenario.game`, `scenario.turn`, `scenario.step` | The underlying objects |

`find` and `untapped_sources` raise `AssertionError` with the contents of the
zone when they miss, so a scenario that drifts tells you what was actually there.

## The card pool

Every card is a real Scryfall printing in `tests/fixtures/cards/`, loaded by
name through `tests/cards.py`. **Never hand-write card json.** These tests are
only worth running because the data is the real shape, with the real oddities.

To add a card:

```sh
uv run python scripts/add_card.py "Birds of Paradise"
```

Then use it by name. `card("...")` raises with the full pool listing if a name
is missing, so a typo tells you what is available.

### Mana sources

`pay_with` reads each source's own `{T}: Add ...` text through
`machines/abilities.py`, so Sol Ring correctly makes two colourless and a basic
makes one of its colour. No per-card table to maintain.

A source offering a choice of colours is ambiguous, so `mana_from` raises rather
than guessing. Tap it yourself with the colour chosen:

```python
payment.tap_for_mana(tinder_farm, [Color.GREEN])
```

### What a spell does

Resolution runs the card's effect from the registry in `machines/effects.py`,
keyed by card name. **A card with no entry resolves and does nothing.** That is
correct for a vanilla creature and silently wrong for anything with text.

Adding a card to the pool does not teach the model what it does. If a scenario
depends on a card's text actually happening, add its effect there too. The
existing entries - damage, counter, exile - show the shape.

### Choosing targets

`targets=` takes permanents, players, or usernames, mixed freely. A `CardState`
is read as an object target and a `str` as a player target, so a Bolt at a
creature is `targets=[bears]` and a Bolt at a face is `targets=["bob"]`.
Underneath, both become a `TargetRef` on the spell (CR 115.1).

Legality **is** checked at announcement (CR 601.2c): `machines/targeting.py`
reads the spell's own text, so a creature-only spell aimed at a player raises,
as do a target in a zone the spell cannot reach, a target the wrong player
controls, and more targets than the spell takes. Choosing *fewer* targets than
required is still allowed, and a card whose text the parser cannot read is not
checked at all - see `docs/engine-coverage.md`.

### Damage and dying

Damage is marked on the `CardState` and stays until the card changes zones.
Nothing dies at the moment damage is dealt: `resolve_top` calls
`check_state_based_actions`, which destroys creatures whose marked damage is
lethal (CR 704.5g). A scenario asserting a creature died should assert on its
zone after resolution, not call the check itself.

## Conventions

- Name the test after what it asserts, not what it does:
  `test_one_land_short_leaves_the_spell_in_hand`, not `test_bad_payment`.
- A shared board goes in a module-level helper returning an unbuilt `Scenario`,
  so each test calls `.build()` on a fresh game.
- Assert on zones and state, not on internals. `beast.zone is Zone.BATTLEFIELD`
  survives a refactor; reaching into `game.shared_zones[...]` by index does not.
- When a scenario cannot be written because the model lacks a rule, that is a
  finding. Write the test, mark it `@pytest.mark.xfail(reason=...)`, and say so
  in the report rather than quietly reshaping the scenario until it passes.
