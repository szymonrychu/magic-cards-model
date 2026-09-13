"""Scenario: countering an activated or triggered ability (CR 113.9).

"Activated and triggered abilities on the stack aren't spells, and therefore
can't be countered by anything that counters only spells. Activated and
triggered abilities on the stack can be countered by spells and abilities that
specifically counter abilities."

Tishana's Tidebinder is the card in the pool that does it: "When this creature
enters, counter up to one target activated or triggered ability. If an ability
of an artifact, creature, or planeswalker is countered this way, that permanent
loses all abilities for as long as this creature remains on the battlefield."

Two halves, and only the first is expressible:

- The counter itself. `Game.counter` already handles an ability correctly - it
  is removed from the stack and put nowhere, because there is no card behind it
  (CR 405.1) - and `machines/effects.py` now has the entry that calls it.
- "That permanent loses all abilities for as long as ..." is a layer 6
  continuous effect (CR 613.1f) with a duration. `Game` does not consult
  `machines/layers.py` and has nowhere to record one, so it does not happen.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with Vampiric Rites to activate; Bob holding Tishana's Tidebinder.

    Vampiric Rites is "{1}{B}, Sacrifice a creature: You gain 1 life and draw a
    card." - an activated ability that is not a mana ability, so it uses the
    stack (CR 602.1a) and can be responded to. Tishana's Tidebinder has flash,
    which is what lets Bob answer it.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[],
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Tishana's Tidebinder"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island"],
        )
    )


def activate_rites(scenario):
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    return scenario.activate(rites, *swamps, username="alice", sacrificing=[bears])


# --------------------------------------------------------------------------
# The ability is a real object on the stack first
# --------------------------------------------------------------------------


def test_an_activated_ability_waits_on_the_stack_where_it_can_be_answered():
    """CR 602.1a and CR 405.1: the ability is its own object, not the card.

    This is the setup every test below needs, asserted once: the ability is on
    the stack under its source's name, and its source is still a permanent.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ability = activate_rites(scenario)

    assert ability is not None
    assert scenario.stack_names() == ["Vampiric Rites's activated ability"]


def test_a_counterspell_cannot_be_aimed_at_an_ability():
    """CR 113.9, first sentence: it "can't be countered by anything that counters
    only spells".

    Counterspell reads "Counter target spell", so the ability is not a legal
    target for it and CR 601.2c refuses the announcement.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[ability])


def test_an_uncountered_ability_resolves_and_does_its_thing():
    """The control: nothing answers it, so CR 608.2 runs the effect.

    Vampiric Rites gains 1 life and draws a card, and CR 608.2n then removes the
    ability from the stack.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate_rites(scenario)

    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21
    assert [card.name for card in scenario.player("alice").hand] == ["Forest"]
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Countering it
# --------------------------------------------------------------------------


def test_tishanas_tidebinder_counters_the_activated_ability():
    """CR 113.9, second sentence: an ability that "specifically counter[s] abilities".

    The Tidebinder's enters-trigger targets the Rites ability on the stack and
    counters it, so the ability never resolves: no life, no card, and CR 608.2n
    takes it off the stack all the same.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    scenario.choose_trigger_targets("Tishana's Tidebinder", [ability])
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    scenario.cast_and_resolve("Tishana's Tidebinder", *islands, username="bob")
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20, "the ability never resolved"
    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []


def test_the_permanent_whose_ability_was_countered_loses_all_abilities():
    """ "That permanent loses all abilities for as long as this creature remains
    on the battlefield."

    An ability-removing effect, so layer 6 (CR 613.1f), lasting as long as a
    condition rather than until end of turn. Nothing in this model can hold one.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    scenario.choose_trigger_targets("Tishana's Tidebinder", [ability])
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    scenario.cast_and_resolve("Tishana's Tidebinder", *islands, username="bob")
    scenario.pass_until_resolved()

    rites = scenario.creature("Vampiric Rites", "alice")
    assert scenario.why_cannot_activate(rites) is not None


def test_the_tidebinder_enters_the_battlefield_either_way():
    """Whatever happens to the trigger, the creature itself resolves and stays.

    CR 608.2b removes an ability whose targets are all illegal from the stack;
    it has nothing to do with the permanent that put it there. This is the part
    that works today, and it is what the two xfails above are hung off.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    scenario.choose_trigger_targets("Tishana's Tidebinder", [ability])
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    tidebinder = scenario.cast_and_resolve("Tishana's Tidebinder", *islands, username="bob")

    assert tidebinder.zone is Zone.BATTLEFIELD
    assert scenario.creature("Tishana's Tidebinder", "bob") is tidebinder


# --------------------------------------------------------------------------
# Repudiate: a *spell* that counters an ability, not a triggered ability's
# own side effect - "Counter target activated or triggered ability. (Mana
# abilities can't be targeted.)" `_COUNTER_TARGET_ABILITY_RE` in
# `machines/effects.py` is what reaches `counter_targets` for this exact
# shape (Tishana's Tidebinder's own "... or spell" cousin was already read by
# `_COUNTER_TARGET_ABILITY_OR_SPELL_RE`); `counter_targets`, `resolve_target`,
# and `Game.counter` needed nothing new - `Game.find_ability_by_id` already
# resolves a `TargetRef` against an ability on the stack (built for Tishana's
# Tidebinder), and `Game.counter` already accepts either kind of
# `StackObject` (CR 113.9, asserted directly on `Game.counter`'s own
# docstring this session).
# --------------------------------------------------------------------------


def _board_with_repudiate() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Repudiate // Replicate"],
            battlefield=["Island", "Island"],
        )
    )


def test_repudiate_counters_the_activated_ability():
    """CR 113.9: a spell that "specifically counter[s] abilities" reaches the
    same ability Tishana's Tidebinder's trigger does, with no new mechanism."""
    scenario = _board_with_repudiate().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Repudiate", *islands, username="bob", targets=[ability])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20, "the ability never resolved"
    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []


def test_repudiate_cannot_target_a_mana_ability():
    """ "(Mana abilities can't be targeted.)" - CR 605.3b's own reason: a mana
    ability never uses the stack at all, so there is nothing there to aim at."""
    scenario = _board_with_repudiate().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.cast("Repudiate", username="bob", targets=[swamp])


# --------------------------------------------------------------------------
# An activated ability that counters an ability (CR 113.9 via CR 602.2b)
#
# "Counter target activated ability." printed after an activation cost is the
# same clause Repudiate prints, and CR 701.6a's counter does not care whether
# a spell or an ability does it. Rimewind Cryomancer is the reported card;
# Azorius Guildmage, in no deck pool, proves the shape rather than the card.
# --------------------------------------------------------------------------


def _alice_activates_rites_against(bob_battlefield: list[str]) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", library=["Forest"], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")
    return scenario, ability


def test_rimewind_cryomancers_activated_ability_counters_the_ability():
    """CR 113.9 and CR 701.6a: the Cryomancer's "{1}, {T}: Counter target
    activated ability" removes the Rites ability from the stack, so it never
    resolves - no life, no card."""
    scenario, ability = _alice_activates_rites_against(
        ["Rimewind Cryomancer"] + ["Snow-Covered Forest"] * 4
    )
    cryomancer = scenario.creature("Rimewind Cryomancer", "bob")
    cryomancer.summoning_sick = False
    (forest,) = scenario.untapped_sources("Snow-Covered Forest", username="bob")

    scenario.activate(cryomancer, forest, username="bob", targets=[ability])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20, "the ability never resolved"
    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []


def test_azorius_guildmages_activated_ability_counters_the_ability():
    """The same printed clause on a different card: Azorius Guildmage's
    "{2}{U}: Counter target activated ability." reaches the same counter."""
    scenario, ability = _alice_activates_rites_against(["Azorius Guildmage"] + ["Island"] * 3)
    guildmage = scenario.creature("Azorius Guildmage", "bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")

    scenario.activate(guildmage, *islands, index=1, username="bob", targets=[ability])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20, "the ability never resolved"
    assert scenario.player("alice").hand == []
    assert scenario.stack_names() == []
