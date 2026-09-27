"""Scenario: "Counter target spell that targets `<description>`." - CR 601.2c's
ordinary "target spell" requirement, further restricted by a property of
*that spell's own targets* rather than of the spell itself.

Two printings, both read by the same widened `machines/targeting.py` grammar
(`TargetRequirement.must_target_you`/`must_target_types`/`must_target_you_
control`, `_read_phrase`'s new "spell [or ability] that targets
`<description>`" branch):

- **Fugitive Droid**: "{U}, Sacrifice this creature: Counter target spell
  that targets an artifact or creature you control." - a type-list
  disjunction ("an artifact or creature"), no "you" option at all.
- **Siren Stormtamer** (proof printing - Modern/Pioneer legal, not a listed
  card, not in any deck list, verified with `resolve_cards`/Scryfall this
  session, 2026-09-27): "{U}, Sacrifice this creature: Counter target spell
  or ability that targets you or a creature you control." - the "you"
  disjunct *and* a type list *and* "or ability" all in one sentence, proving
  the reader generalises beyond Fugitive Droid's own narrower wording rather
  than being fitted to it.

CR 601.2c (the announcement that makes a target legal in the first place) and
CR 608.2b (the same restriction rechecked as the counter tries to resolve)
were both looked up this session with `mise run rules:find <n>`; the ability
that carries the restriction is itself CR 602.1 activated.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def test_fugitive_droid_counters_a_spell_targeting_its_own_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fugitive Droid", "Grizzly Bears", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    droid = scenario.creature("Fugitive Droid")
    bears = scenario.creature("Grizzly Bears")
    (island,) = scenario.untapped_sources("Island")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.pass_priority()
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    scenario.pass_priority(username="bob")
    scenario.activate(droid, island, sacrificing=[droid], targets=[bolt], username="alice")
    scenario.resolve_top()  # Fugitive Droid's own counter ability

    assert bolt.zone.value == "graveyard"
    assert bears.damage == 0, "the Bolt never resolved"


def test_fugitive_droid_cannot_target_a_spell_that_targets_something_else():
    """The Bolt targets bob's own player, not an artifact or creature alice
    controls - CR 601.2c refuses Fugitive Droid's own activation outright,
    since no legal target for it exists."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fugitive Droid", "Island"])
        .player("bob", hand=["Lightning Bolt"], life=20, battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    droid = scenario.creature("Fugitive Droid")
    (island,) = scenario.untapped_sources("Island")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.pass_priority()
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    with pytest.raises(ValueError):
        scenario.activate(droid, island, sacrificing=[droid], targets=[bolt], username="alice")


def test_siren_stormtamer_counters_a_spell_targeting_you():
    """The "you" disjunct - a second, differently-worded printing of the
    same "that targets `<description>`" template."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Siren Stormtamer", "Island"])
        .player("bob", hand=["Lightning Bolt"], life=20, battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stormtamer = scenario.creature("Siren Stormtamer")
    (island,) = scenario.untapped_sources("Island")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.pass_priority()
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority(username="bob")
    scenario.activate(
        stormtamer, island, sacrificing=[stormtamer], targets=[bolt], username="alice"
    )
    scenario.resolve_top()

    assert bolt.zone.value == "graveyard"
    assert scenario.player("alice").life == 20, "the Bolt never resolved"


def test_siren_stormtamer_counters_a_spell_targeting_its_own_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Siren Stormtamer", "Grizzly Bears", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stormtamer = scenario.creature("Siren Stormtamer")
    bears = scenario.creature("Grizzly Bears")
    (island,) = scenario.untapped_sources("Island")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.pass_priority()
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    scenario.pass_priority(username="bob")
    scenario.activate(
        stormtamer, island, sacrificing=[stormtamer], targets=[bolt], username="alice"
    )
    scenario.resolve_top()

    assert bolt.zone.value == "graveyard"
    assert bears.damage == 0


def test_siren_stormtamer_cannot_target_a_spell_that_targets_an_opponent():
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Siren Stormtamer", "Island"])
        .player("bob", hand=["Lightning Bolt"], life=20, battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stormtamer = scenario.creature("Siren Stormtamer")
    (island,) = scenario.untapped_sources("Island")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.pass_priority()
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["bob"])
    with pytest.raises(ValueError):
        scenario.activate(
            stormtamer, island, sacrificing=[stormtamer], targets=[bolt], username="alice"
        )
