""" "this `<kind>` attacks or blocks" (CR 508.1, 509.1) and the general
"this `<any card type or subtype word>`" self-reference (CR 700.7) it needs.

Every CR number below was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 700.7** - "'This [type/subtype]' ... refer[s] to the object with that
  ability" - a templating convention over *any* card type or subtype word,
  not a fixed vocabulary of examples. `machines/triggers._SELF_PHRASES` used
  to be exactly that fixed list - "this creature", "this permanent", "this
  artifact", and eight more - with no entry for "this Vehicle" at all.
  `_self_reference_type_words` replaces it with the same CR 205.2a/CR 205.3
  type-and-subtype vocabulary `machines/layers.py` and `machines/
  replacement.py` already share (`Type` plus `data.subtypes.
  subtype_vocabulary`), so a new subtype needs no edit here.
- **CR 508.1** / **CR 509.1** - attacking and blocking.
- **CR 205.3g** - Vehicle is an artifact subtype.

Two engine gaps, read together:

- `triggers._ATTACKS_OR_BLOCKS_RE` used to be hard-coded to "this creature",
  so Smuggler's Copter's and Getaway Car's own "this Vehicle attacks or
  blocks" never expanded into the two separate attack/block conditions
  `_expand_attacks_or_blocks` builds - it fell through as one unread
  compound condition, and `machines.abilities._trigger_event`'s own
  "attacks?" ahead of "blocks?" precedence read it as ATTACKS alone, so a
  Vehicle that blocked and never attacked would never see its own trigger.
  Fixed the same way `_ENTERS_OR_LEAVES_RE` already reads an open `this
  (?P<kind>[a-z]+)` rather than a literal "creature".
- Once the condition parses, `_self_referential` still has to recognise
  "this Vehicle" as *self*-referential (`_SELF_PHRASES` had no entry for
  it) - otherwise `condition_matches`'s own ATTACKS/BLOCKS branches read
  `mine` as `False` and fall into the *non*-self path, which asks only
  whether the attacker/blocker's card types satisfy the condition's type
  words. "vehicle" is a subtype, not one of `_TYPE_WORDS`'s card types, so
  `_types_match` reads it as no restriction at all - every attacking or
  blocking creature would have satisfied it, firing Copter's own trigger
  off ANY creature's attack once its body merger (`test_may_then_if_you_do
  .py`) made the ability parse at all. `test_uncrewed_copter_is_not_
  triggered_by_another_creature_attacking` and `..._by_another_vehicle_
  attacking` below are the regression tests for exactly that.

Getaway Car ("this Vehicle attacks or blocks, return up to one target
creature that crewed it this turn to its owner's hand") isolates the
condition/self-reference half from the body-merger half: its own effect
clause already parses today (`_parse_target_that_crewed_it_this_turn_
clause` or equivalent), so a Getaway Car test failing before this fix and
passing after it is evidence for the condition fix alone, not entangled
with `_merge_may_then_if_you_do_clauses`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def crew(scenario: Scenario, vehicle, *creatures, username: str = "alice"):
    """Activate a Vehicle's crew ability, pay it, and let it resolve (CR
    702.122a)."""
    activation = crew_activation(scenario.game, vehicle, list(creatures), username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def triggered_ability_sources(scenario: Scenario) -> list[str]:
    """Every triggered ability's own source name, wherever it currently sits.

    `Game.declare_attackers`/`declare_blockers` already call `put_triggers_
    on_stack` themselves (CR 603.3) before either ever returns, so a trigger
    from combat is never still in `pending_triggers` by the time a caller
    here reads it - it has already moved to `game.stack`. Checking only
    `pending_triggers` would read as "nothing triggered" even when something
    just did.
    """
    names = [ability.source_name for ability in scenario.pending_triggers]
    names += [item.source_name for item in scenario.game.stack if hasattr(item, "source_name")]
    return names


# --------------------------------------------------------------------------
# (d) Getaway Car: the compound condition fires on a block, not only an
# attack - the plain condition/kind fix, isolated from the body merger.
# --------------------------------------------------------------------------


def test_getaway_car_attacking_returns_the_creature_that_crewed_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Getaway Car", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    car = scenario.find("Getaway Car", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    crew(scenario, car, bears)
    scenario.choose_trigger_targets("Getaway Car", [bears])

    scenario.attack_with(car)
    resolve_all(scenario)

    assert bears in scenario.player("alice").hand


def test_getaway_car_blocking_also_returns_the_creature_that_crewed_it():
    """The regression this file exists for: a Vehicle that blocks and never
    attacks still triggers, exactly as Elder Gargaroth's plain "this
    creature" shape already does."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Getaway Car", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    car = scenario.find("Getaway Car", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    crew(scenario, car, bears, username="bob")
    scenario.choose_trigger_targets("Getaway Car", [bears])

    scenario.attack_with(attacker)
    # Nothing triggers from the bare attack itself - it is alice's own
    # Grizzly Bears attacking, not Getaway Car's. Asserted explicitly (`Game.
    # declare_attackers` already calls `put_triggers_on_stack` itself, so a
    # trigger here would already be on `game.stack`, not `pending_triggers`)
    # rather than just left to a bare `resolve_all`, so a self-reference
    # regression (the non-self branch's permissive type match firing this
    # off *any* attacker - `test_uncrewed_copter_is_not_triggered_by_
    # another_creature_attacking`'s own bug) cannot quietly pre-empt the
    # block half below and still leave this assertion looking satisfied.
    assert triggered_ability_sources(scenario) == []
    resolve_all(scenario)

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(attacker, car)
    resolve_all(scenario)

    assert bears in scenario.player("bob").hand


# --------------------------------------------------------------------------
# (e) Over-trigger regression: an uncrewed Smuggler's Copter sits on the
# battlefield (an artifact, not a creature, so it can never itself be
# declared an attacker), and neither another creature's nor another
# Vehicle's own attack should fire its trigger.
# --------------------------------------------------------------------------


def test_uncrewed_copter_is_not_triggered_by_another_creature_attacking():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Smuggler's Copter", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears)

    assert "Smuggler's Copter" not in triggered_ability_sources(scenario)


def test_uncrewed_copter_is_not_triggered_by_another_vehicle_attacking():
    """Consulate Dreadnought prints no attack/block trigger of its own -
    every assertion here is about Copter's, never Dreadnought's."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Smuggler's Copter",
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Grizzly Bears",
                "Grizzly Bears",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadnought = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD, "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    crew(scenario, dreadnought, *bears)

    scenario.attack_with(dreadnought)

    assert "Smuggler's Copter" not in triggered_ability_sources(scenario)


# --------------------------------------------------------------------------
# (f) Regression: a plain "this creature attacks or blocks" pool card is
# unaffected by widening the shape past a literal "creature".
# --------------------------------------------------------------------------


def test_elder_gargaroth_this_creature_attacks_or_blocks_is_unchanged():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elder Gargaroth"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    scenario.will_choose_mode("You gain 3 life.")
    before = scenario.player("alice").life

    scenario.attack_with(gargaroth)
    resolve_all(scenario)

    assert scenario.player("alice").life == before + 3
