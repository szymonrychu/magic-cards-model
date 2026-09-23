"""Scenario: an activated ability's "`<base>`. If `<condition>`, `<alternative>`
instead." - CR 614.1a's "instead", on an ability rather than a spell - and the
"you control creatures named `<A>` and `<B>`" condition it most often carries
on the Assembly-Workers.

Mine Worker: "{T}: You gain 1 life. If you control creatures named Power Plant
Worker and Tower Worker, you gain 3 life instead." The two names are read out
of the sentence (CR 201.2: an object's name), never out of a table, and both
must name *creatures* you control. The condition is read as the ability
resolves, so the named creatures leaving in response turns the 3 back into a
1. "Instead" replaces the gain: 3, never 1 + 3.

Zimone, Quandrix Prodigy's "{4}, {T}: Draw a card. If you control eight or
more lands, draw two cards instead." is the second printing: the same
ability-side "instead" reader with a different condition (a count) and a
different instruction (draw). Power Plant Worker is the second printing of the
named-creatures condition, on a pump-or-counters "instead" instead of a
life gain.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _mine_worker_board(*alice_extra: str, bob: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Mine Worker", *alice_extra],
            library=["Plains"] * 3,
        )
        .player("bob", battlefield=list(bob), hand=["Lightning Bolt"], library=["Island"] * 3)
        .build()
    )


def _activate_mine_worker(scenario: Scenario) -> None:
    worker = scenario.creature("Mine Worker", "alice")
    scenario.activate(worker)


def test_mine_worker_alone_gains_one():
    scenario = _mine_worker_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_mine_worker_with_both_named_creatures_gains_three_instead():
    scenario = _mine_worker_board("Power Plant Worker", "Tower Worker")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 23, "3 instead of 1, never 1 + 3"


def test_mine_worker_with_only_one_named_creature_gains_one():
    scenario = _mine_worker_board("Tower Worker")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_mine_worker_with_the_other_named_creature_only_gains_one():
    scenario = _mine_worker_board("Power Plant Worker")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_the_named_creatures_must_be_yours():
    """ "If you control" - Bob controlling the other two Workers does not
    count for Alice."""
    scenario = _mine_worker_board(bob=("Power Plant Worker", "Tower Worker"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_one_of_each_side_is_not_both():
    scenario = _mine_worker_board("Power Plant Worker", bob=("Tower Worker",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_a_second_mine_worker_is_not_a_named_partner():
    scenario = _mine_worker_board("Mine Worker", "Tower Worker")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


def test_the_condition_is_read_as_the_ability_resolves():
    """Alice activates with both partners out; Bob bolts Tower Worker (1/3) in
    response, so when the ability resolves she no longer controls a creature
    named Tower Worker and gains 1, not 3."""
    scenario = _mine_worker_board("Power Plant Worker", "Tower Worker", bob=("Mountain",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_mine_worker(scenario)
    tower = scenario.creature("Tower Worker", "alice")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[tower])
    assert tower.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21


# -- Zimone, Quandrix Prodigy: the same "instead" reader, a count condition --


def _zimone_board(lands: int) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Zimone, Quandrix Prodigy", *["Forest"] * lands],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )


def _activate_zimone_draw(scenario: Scenario) -> None:
    zimone = scenario.creature("Zimone, Quandrix Prodigy", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")
    scenario.activate(zimone, *forests, index=1)
    scenario.pass_until_resolved()


def test_zimone_draws_one_with_seven_lands():
    scenario = _zimone_board(7)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_zimone_draw(scenario)

    assert len(scenario.player("alice").hand) == 1


def test_zimone_draws_two_instead_with_eight_lands():
    scenario = _zimone_board(8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_zimone_draw(scenario)

    assert len(scenario.player("alice").hand) == 2, "two instead of one, never three"


# -- Power Plant Worker: the named-creatures condition on a different template


def test_power_plant_worker_needs_both_named_partners_to_be_creatures_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Power Plant Worker", "Mine Worker", "Plains", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Tower Worker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worker = scenario.creature("Power Plant Worker", "alice")
    scenario.activate(worker, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.pass_until_resolved()

    assert worker.counter_count(Counter.PLUS_ONE) == 0


def test_power_plant_worker_with_both_partners_gets_counters():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Power Plant Worker",
                "Mine Worker",
                "Tower Worker",
                "Plains",
                "Plains",
                "Plains",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worker = scenario.creature("Power Plant Worker", "alice")
    scenario.activate(worker, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.pass_until_resolved()

    assert worker.counter_count(Counter.PLUS_ONE) == 2


# -- Scute Swarm: the same "instead" reader on a triggered ability ----------


def _scute_board(lands: int) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Forest"],
            battlefield=["Scute Swarm", *["Forest"] * lands],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )


def _landfall(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Scute Swarm's triggered ability"]
    scenario.resolve_top()


def _alice_creatures(scenario: Scenario) -> list[str]:
    return [
        state.name
        for state in scenario.game.permanents_controlled_by("alice")
        if scenario.game.computed_board().of(state).is_creature
    ]


def test_scute_swarm_with_five_lands_makes_an_insect():
    scenario = _scute_board(4)
    _landfall(scenario)

    creatures = _alice_creatures(scenario)
    assert creatures.count("Scute Swarm") == 1
    assert len(creatures) == 2, "Scute Swarm and one 1/1 Insect"


def test_scute_swarm_with_six_lands_copies_itself_instead():
    """The condition counts the land that just entered: the sixth land's own
    landfall sees six. "Instead": a copy of Scute Swarm, and no Insect."""
    scenario = _scute_board(5)
    _landfall(scenario)

    creatures = _alice_creatures(scenario)
    assert creatures.count("Scute Swarm") == 2
    assert len(creatures) == 2, "no Insect alongside the copy"
    (copy,) = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Scute Swarm" and state.token
    ]
    assert scenario.game.computed_board().of(copy).power_toughness == (1, 1)
