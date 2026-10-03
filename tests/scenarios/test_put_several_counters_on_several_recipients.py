"""A "put" that names several counters and, sometimes, several recipients.

Arwen, Mortal Queen: "{1}, Remove an indestructible counter from Arwen:
Another target creature gains indestructible until end of turn. Put a +1/+1
counter and a lifelink counter on that creature and a +1/+1 counter and a
lifelink counter on Arwen."

Second printing, differently worded: Guide of Souls' reflexive trigger puts
"two +1/+1 counters and a flying counter on target attacking creature" - the
counters are named by a count, the recipient is a target rather than an
anaphor, and the whole thing is a triggered ability.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 122.1b** - a keyword counter makes its object gain the keyword.
- **CR 118.3** - a cost can't be paid unless the player can do all of it, so
  with no indestructible counter left the ability cannot be activated.
- **CR 608.2b** - an ability whose only target is illegal on resolution does
  not resolve: Arwen gets nothing either.
- **CR 608.2c** - the instructions are followed in the order written.
- **CR 613.1f** - the keyword counters and the granted indestructible are
  layer 6.
- **CR 514.2** - "until end of turn" ends in the cleanup step; counters stay.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.counter_effects import expand_compound_counter_puts
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arwen, Mortal Queen"],
            battlefield=["Grizzly Bears", "Plains", *["Forest"] * 5],
            library=["Forest"] * 5,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arwen = scenario.cast_and_resolve(
        "Arwen, Mortal Queen", *scenario.untapped_sources("Plains", "Forest", "Forest")
    )
    return scenario, arwen, scenario.creature("Grizzly Bears", "alice")


def _activate(scenario, arwen, bears):
    return scenario.activate(
        arwen, *scenario.untapped_sources("Forest", username="alice"), targets=[bears]
    )


def test_arwen_gives_both_creatures_both_counters_and_the_target_indestructible():
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.pass_until_resolved()

    assert bears.counters["+1/+1"] == 1
    assert bears.counters["lifelink"] == 1
    assert arwen.counters["+1/+1"] == 1
    assert arwen.counters["lifelink"] == 1
    assert has_keyword(bears, "indestructible", scenario.game)
    assert has_keyword(bears, "lifelink", scenario.game), "CR 122.1b"
    assert has_keyword(arwen, "lifelink", scenario.game), "CR 122.1b"


def test_the_indestructible_counter_was_the_cost_so_arwen_is_no_longer_indestructible():
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.pass_until_resolved()
    assert arwen.counters["indestructible"] == 0
    assert not has_keyword(arwen, "indestructible", scenario.game)


def test_with_no_indestructible_counter_left_the_ability_cannot_be_activated():
    """CR 118.3: the cost's counter is gone after one use."""
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(arwen) is not None
    with pytest.raises(ValueError):
        _activate(scenario, arwen, bears)


def test_arwen_without_the_counter_to_begin_with_cannot_activate():
    scenario, arwen, bears = _board()
    arwen.remove_counters("indestructible", 1)
    assert scenario.why_cannot_activate(arwen) is not None


def test_the_counter_is_removed_when_the_ability_is_activated_not_when_it_resolves():
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    assert arwen.counters["indestructible"] == 0
    assert bears.counters["+1/+1"] == 0, "nothing has resolved yet"


def test_arwen_is_not_a_legal_target_for_another_target_creature():
    scenario, arwen, bears = _board()
    with pytest.raises(ValueError):
        _activate(scenario, arwen, arwen)


def test_indestructible_ends_at_cleanup_but_the_counters_stay():
    """CR 514.2."""
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.pass_until_resolved()
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert not has_keyword(bears, "indestructible", scenario.game)
    assert bears.counters["+1/+1"] == 1
    assert has_keyword(bears, "lifelink", scenario.game)


def test_a_target_that_is_gone_on_resolution_means_arwen_gets_no_counters_either():
    """CR 608.2b: the only target is illegal, so the ability doesn't resolve."""
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.game.exile_permanent(bears)
    scenario.pass_until_resolved()
    assert arwen.counters["+1/+1"] == 0
    assert arwen.counters["lifelink"] == 0


def test_the_target_destroyed_in_response_is_not_saved_by_a_later_grant():
    """The grant resolves with the rest, so a destroy in response wins."""
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()
    assert arwen.counters["+1/+1"] == 0


def test_the_counters_come_on_in_the_order_written_the_target_first():
    scenario, arwen, bears = _board()
    _activate(scenario, arwen, bears)
    scenario.pass_until_resolved()
    # Two +1/+1 counters made two 3/3s' worth of difference: 2/2 -> 3/3, 3/4 -> 4/5.
    board = scenario.game.computed_board()
    assert (board.of(bears).power, board.of(bears).toughness) == (3, 3)


# -- the shape, on text -------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "expanded"),
    [
        (
            "Put a +1/+1 counter and a lifelink counter on that creature and a +1/+1 counter "
            "and a lifelink counter on this permanent.",
            "Put a +1/+1 counter on that creature. Put a lifelink counter on that creature. "
            "Put a +1/+1 counter on this permanent. Put a lifelink counter on this permanent.",
        ),
        (
            "Put two +1/+1 counters and a flying counter on target attacking creature.",
            "Put two +1/+1 counters on target attacking creature. "
            "Put a flying counter on that creature.",
        ),
        (
            "Put a +1/+1 counter, a flying counter, and a lifelink counter on up to one target "
            "creature you control.",
            "Put a +1/+1 counter on up to one target creature you control. "
            "Put a flying counter on that creature. Put a lifelink counter on that creature.",
        ),
    ],
)
def test_a_compound_put_is_the_sequence_of_its_simple_puts(printed, expanded):
    assert expand_compound_counter_puts(printed) == expanded


@pytest.mark.parametrize(
    "text",
    [
        "Put a +1/+1 counter on target creature.",
        "Put a +1/+1 counter on target creature and a +1/+1 counter on this permanent.",
        "Put a +1/+1 counter and a flying counter on target creature or planeswalker.",
        "Put a +1/+1 counter and a flying counter on each of two target creatures.",
        'Create a token with "Put a +1/+1 counter and a flying counter on this token."',
    ],
)
def test_text_it_cannot_say_twice_without_guessing_is_left_alone(text):
    assert expand_compound_counter_puts(text) == text
