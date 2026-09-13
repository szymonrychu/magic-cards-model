"""Scenario: an activated or triggered ability as a target (CR 115.2, CR 113.1c).

CR 115.2 says only permanents are legal targets "unless a spell or ability (a)
specifies that it can target an object in another zone or a player, or (b)
targets an object that can't exist on the battlefield, such as a spell or
ability on the stack". CR 113.1c is what makes such an ability an object at all:
"an ability can be an activated or triggered ability on the stack. This kind of
ability is an object."

Tishana's Tidebinder is the card in the pool that reaches for one: "When this
creature enters, counter up to one target activated or triggered ability."

This file is about the *targeting* half - who may be aimed at what. The
countering itself lives in `test_countering_an_ability.py`.

Two rules bound the shape of it:

- A **mana ability** never becomes a target, because it never becomes an object
  on the stack: CR 605.3b, "an activated mana ability doesn't go on the stack,
  so it can't be targeted, countered, or otherwise responded to", and CR 605.4a
  for the triggered kind. That is why the Tidebinder prints the reminder.
- "Counter target **spell**" is a different requirement, and CR 113.9 spells out
  the consequence: abilities "can't be countered by anything that counters only
  spells".

The requirement itself is printed inside a triggered ability, not in the card's
spell text, so `targeting_profile` never sees it - `profile_for_text` reads an
ability's own words instead.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text, targeting_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def tidebinder_requirement():
    """The one target Tishana's Tidebinder's enters-trigger asks for."""
    (requirement,) = profile_for_text(card("Tishana's Tidebinder").oracle_text).requirements
    return requirement


def board() -> Scenario:
    """Alice with an activatable Vampiric Rites and a Llanowar Elves; Bob answering.

    Vampiric Rites is "{1}{B}, Sacrifice a creature: You gain 1 life and draw a
    card." - not a mana ability, so it uses the stack (CR 602.1a). Llanowar Elves
    is the control: "{T}: Add {G}" is a mana ability and never gets there.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears", "Llanowar Elves"],
        )
        .player(
            "bob",
            hand=["Tishana's Tidebinder", "Counterspell"],
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
# What the requirement says
# --------------------------------------------------------------------------


def test_the_requirement_is_an_ability_on_the_stack_and_nothing_else():
    """CR 115.2(b): an object that cannot exist on the battlefield."""
    requirement = tidebinder_requirement()

    assert requirement.allows_abilities
    assert not requirement.allows_cards
    assert not requirement.allows_players
    assert requirement.zones == frozenset({Zone.STACK})


def test_up_to_one_means_the_trigger_may_choose_none():
    """CR 115.6: a requirement that "may allow zero targets to be chosen"."""
    requirement = tidebinder_requirement()

    assert (requirement.minimum, requirement.count) == (0, 1)
    assert requirement.optional


def test_casting_the_tidebinder_itself_targets_nothing():
    """The creature spell has no targets; the trigger it makes does (CR 113.1c)."""
    assert targeting_profile(card("Tishana's Tidebinder")).requirements == ()


# --------------------------------------------------------------------------
# Against a real ability on a real stack
# --------------------------------------------------------------------------


def test_a_real_activated_ability_on_the_stack_is_a_legal_target():
    """The Rites ability is an object (CR 113.1c) sitting in the stack zone."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ability = activate_rites(scenario)

    assert ability is not None and ability.zone is Zone.STACK
    assert tidebinder_requirement().rejects(ability, caster="bob") is None


def test_a_creature_is_not_an_ability():
    """The other direction of CR 115.2: the trigger cannot be aimed at a permanent."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    reason = tidebinder_requirement().rejects(elves, caster="bob")

    assert reason is not None and "can only target an ability" in reason


def test_a_player_is_not_an_ability():
    reason = tidebinder_requirement().rejects("alice", caster="bob")

    assert reason is not None and "cannot target the player" in reason


def test_counter_target_spell_refuses_an_ability():
    """CR 113.9: abilities "can't be countered by anything that counters only
    spells"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)

    profile = targeting_profile(card("Counterspell"))
    reason = profile.requirements[0].rejects(ability, caster="bob")

    assert reason is not None and "is an ability on the stack" in reason


def test_a_counterspell_cast_at_an_ability_is_refused_at_announcement():
    """The same rule reached through CR 601.2c, on a real board."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")

    with pytest.raises(ValueError, match="ability on the stack"):
        scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[ability])


# --------------------------------------------------------------------------
# The abilities that can never be targets
# --------------------------------------------------------------------------


def test_a_mana_ability_never_reaches_the_stack_to_be_targeted():
    """CR 605.3b: "an activated mana ability doesn't go on the stack, so it can't
    be targeted, countered, or otherwise responded to".

    Llanowar Elves' "{T}: Add {G}" resolves immediately and leaves nothing for
    the Tidebinder to point at - which is what its reminder text says out loud.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    elves.summoning_sick = False

    ability = scenario.activate(elves, username="alice")

    assert ability is None, "a mana ability is not an object on the stack"
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


def test_the_engine_can_find_the_ability_a_target_points_at():
    """CR 608.2b decides legality by looking the target up, so the lookup has to work.

    The targeting parser now reads "target activated or triggered ability" and
    `TargetRequirement.rejects` accepts a real `AbilityOnStack`, so announcement
    is settled. Resolution is not: nothing can turn the `TargetRef` back into the
    ability it names.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")

    scenario.choose_trigger_targets("Tishana's Tidebinder", [ability])
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    scenario.cast_and_resolve("Tishana's Tidebinder", *islands, username="bob")
    (trigger,) = [
        item
        for item in scenario.game.stack
        if getattr(item, "source_name", None) == "Tishana's Tidebinder"
    ]

    assert trigger.targets, "the trigger went on the stack carrying its target"
    assert scenario.game.resolve_target(trigger.targets[0]) is ability
    assert not scenario.game.spell_fizzles(trigger)


# --------------------------------------------------------------------------
# Which kind of ability the words name (CR 113.3b, CR 113.3c)
# --------------------------------------------------------------------------
#
# "target activated or triggered ability" names both categories, but the
# shorter phrases name one: Consign to Memory's "target triggered ability or
# colorless spell" cannot be aimed at an activated ability, and Rimewind
# Cryomancer's "{1}, {T}: Counter target activated ability." cannot be aimed at
# a trigger. CR 113.3b and CR 113.3c define the two categories; each ability on
# the stack is one or the other (`AbilityOnStack.kind`).


def consign_requirement():
    (requirement,) = targeting_profile(card("Consign to Memory")).requirements
    return requirement


def cryomancer_requirement():
    """The target of Rimewind Cryomancer's activated ability, read off its own
    effect text (the part after the cost, CR 602.1a)."""
    line = card("Rimewind Cryomancer").oracle_text.split("\n")[0]
    (requirement,) = profile_for_text(line.split(": ", 1)[1]).requirements
    return requirement


def kitchen_finks_trigger():
    """Alice's Kitchen Finks resolves and its "When this creature enters, you
    gain 2 life." trigger is on the stack. Returns the scenario and trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Kitchen Finks"],
            library=["Forest"],
            battlefield=["Plains", "Plains", "Plains"],
        )
        .player("bob", library=["Forest"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Kitchen Finks", *plains)
    (trigger,) = scenario.game.stack
    assert getattr(trigger, "is_ability", False) and trigger.source_name == "Kitchen Finks"
    return scenario, trigger


def test_a_triggered_only_target_refuses_an_activated_ability():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)

    reason = consign_requirement().rejects(ability, caster="bob")

    assert reason is not None and "activated ability" in reason


def test_a_triggered_only_target_accepts_a_trigger():
    _, trigger = kitchen_finks_trigger()

    assert consign_requirement().rejects(trigger, caster="bob") is None


def test_an_activated_only_target_refuses_a_trigger():
    """Rimewind Cryomancer is not in either deck pool, and its phrase is the
    other single category, so this is the same rule on different words."""
    _, trigger = kitchen_finks_trigger()

    reason = cryomancer_requirement().rejects(trigger, caster="bob")

    assert reason is not None and "triggered ability" in reason


def test_an_activated_only_target_accepts_an_activated_ability():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)

    assert cryomancer_requirement().rejects(ability, caster="bob") is None


def test_activated_or_triggered_still_accepts_both():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    _, trigger = kitchen_finks_trigger()

    assert tidebinder_requirement().rejects(ability, caster="bob") is None
    assert tidebinder_requirement().rejects(trigger, caster="bob") is None


def test_consign_to_memory_cast_at_an_activated_ability_is_refused_at_announcement():
    """The same rule through CR 601.2c on a real board, with the engine's own
    words as the refusal."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", hand=["Consign to Memory"], library=["Forest"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")
    (island,) = scenario.untapped_sources("Island", username="bob")

    with pytest.raises(ValueError, match="activated ability"):
        scenario.cast_onto_stack("Consign to Memory", island, username="bob", targets=[ability])


def cryomancer_against_rites():
    """Alice's Vampiric Rites ability is on the stack; Bob holds priority with
    an untapped Rimewind Cryomancer and four snow lands (its "Activate only if
    you control four or more snow permanents")."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player(
            "bob",
            library=["Forest"],
            battlefield=["Rimewind Cryomancer"] + ["Snow-Covered Forest"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ability = activate_rites(scenario)
    scenario.pass_priority("alice")
    cryomancer = scenario.creature("Rimewind Cryomancer", "bob")
    cryomancer.summoning_sick = False
    return scenario, ability, cryomancer


def test_an_ability_on_the_stack_is_among_the_legal_target_candidates():
    """CR 115.2(b): the ability is an object a spell or ability may target,
    so the engine's own candidate list for a requirement naming one has to
    contain it - otherwise a mandatory "target activated ability" reads as
    having no legal target at all (CR 601.2c, 602.2b)."""
    scenario, ability, _ = cryomancer_against_rites()
    profile = profile_for_text(
        card("Rimewind Cryomancer").oracle_text.split("\n")[0].split(": ", 1)[1]
    )

    candidates = scenario.game._legal_target_candidates(profile, "bob", None)

    assert ability in candidates


def test_an_activation_announced_without_targets_asks_for_the_ability():
    """`begin_activating` with no targets asks for them (CR 602.2b), offering
    the ability on the stack, rather than refusing for want of a target."""
    scenario, ability, cryomancer = cryomancer_against_rites()
    scenario.will_choose_targets(ability, username="bob")

    payment = scenario.game.begin_activating(cryomancer, 0, "bob")

    assert payment is not None
