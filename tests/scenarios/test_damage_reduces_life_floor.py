"""A general "damage that would reduce your life total to less than N reduces
it to N instead." replacement (CR 614.1a), in its static form (Elderscale
Wurm, gated on "as long as you have 7 or more life") and its until-end-of-turn
created form (Angel of Grace's enters trigger, CR 611.2a/CR 514.2).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 614.1a** - "instead" replacement effects.
- **CR 604.2** - a static ability's continuous effect is active exactly while
  the permanent is on the battlefield.
- **CR 611.2a** - a continuous effect a resolving ability creates lasts as
  long as it states ("until end of turn"), and CR 514.2 ends it in cleanup.
- **CR 119.2/119.3** - damage to a player is life loss, its own event.

Elderscale Wurm also prints "When this creature enters, if your life total is
less than 7, your life total becomes 7." (`machines/effects.life_total_
becomes_effect_for`, the same reader Providence and Captive Audience use), and
Angel of Grace an activated ability, "{4}{W}{W}, Exile this card from your
graveyard: Your life total becomes 10." - both proven here alongside the
floor replacement since they are this same pair of cards' own clauses.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_next_turn(scenario) -> None:
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


# -- Elderscale Wurm ----------------------------------------------------------


def test_entering_below_seven_life_raises_it_to_seven() -> None:
    scenario = (
        Scenario()
        .player("alice", life=4, hand=["Elderscale Wurm"], battlefield=["Forest"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Elderscale Wurm", auto=True)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 7


def test_entering_at_or_above_seven_life_is_untouched() -> None:
    scenario = (
        Scenario()
        .player("alice", life=12, hand=["Elderscale Wurm"], battlefield=["Forest"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Elderscale Wurm", auto=True)

    assert scenario.player("alice").life == 12


def test_static_floors_damage_at_seven_while_life_is_seven_or_more() -> None:
    scenario = (
        Scenario()
        .player("alice", life=10, battlefield=["Elderscale Wurm"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )

    scenario.game.deal_damage(scenario.player("alice"), 9)  # would take 10 -> 1

    assert scenario.player("alice").life == 7


def test_static_does_not_clamp_below_the_floor() -> None:
    """Damage that does not cross below 7 is untouched."""
    scenario = (
        Scenario().player("alice", life=10, battlefield=["Elderscale Wurm"]).player("bob").build()
    )

    scenario.game.deal_damage(scenario.player("alice"), 2)  # 10 -> 8, still >= 7

    assert scenario.player("alice").life == 8


def test_static_stops_protecting_once_life_is_already_below_seven() -> None:
    """ "As long as you have 7 or more life" - the condition itself must hold
    for the static to apply at all."""
    scenario = (
        Scenario().player("alice", life=5, battlefield=["Elderscale Wurm"]).player("bob").build()
    )

    scenario.game.deal_damage(scenario.player("alice"), 3)  # 5 -> 2, no protection now

    assert scenario.player("alice").life == 2


# -- Angel of Grace -----------------------------------------------------------


def test_entering_creates_an_until_end_of_turn_floor_at_one() -> None:
    scenario = (
        Scenario()
        .player("alice", life=10, hand=["Angel of Grace"], battlefield=["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Angel of Grace", auto=True)
    scenario.pass_until_resolved()

    scenario.game.deal_damage(scenario.player("alice"), 15)  # would take 10 -> -5

    assert scenario.player("alice").life == 1
    assert not scenario.game.is_over


def test_the_floor_does_not_survive_past_the_turn() -> None:
    scenario = (
        Scenario()
        .player("alice", life=10, hand=["Angel of Grace"], battlefield=["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Angel of Grace", auto=True)
    scenario.pass_until_resolved()

    _to_next_turn(scenario)

    assert scenario.game.created_replacements == []
    scenario.game.deal_damage(scenario.player("alice"), 15)
    scenario.game.check_state_based_actions()
    assert not scenario.game.is_in_game("alice")


def test_graveyard_activation_sets_life_to_ten() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=2,
            graveyard=["Angel of Grace"],
            battlefield=["Plains"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Angel of Grace", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*["Plains"] * 6)

    scenario.activate(angel, *sources, exiling=[angel])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 10
    assert angel.zone is Zone.EXILE
