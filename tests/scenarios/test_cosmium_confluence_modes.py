"""Cosmium Confluence (CR 700.2, CR 700.2d, CR 205.1b).

"Choose three. You may choose the same mode more than once.
- Search your library for a Cave card, put it onto the battlefield tapped, then
  shuffle.
- Put three +1/+1 counters on a Cave you control. It becomes a 0/0 Elemental
  creature with haste. It's still a land.
- Destroy target enchantment."

The Cave of the second mode is not targeted ("a Cave you control" is chosen as
the mode resolves, CR 608.2d), the animation lasts for the rest of the game
(CR 611.2a, no duration), and the 0/0 is kept alive by the counters
(CR 613.4b/c, CR 704.5f). A mode chosen twice resolves twice (CR 700.2d).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAVE_MODE = 2
SEARCH_MODE = 1
DESTROY_MODE = 3


def _board(*, library=None, bob=None, extra_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cosmium Confluence"],
            battlefield=["Forest"] * 5 + ["Captivating Cave", *extra_battlefield],
            library=library or ["Forest"] * 5,
        )
        .player("bob", battlefield=bob or [], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, modes, targets=()):
    casting = scenario.cast("Cosmium Confluence")
    casting.choose_modes(list(modes))
    if targets:
        casting.choose_targets(list(targets))
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    casting.cast()
    scenario.pass_until_resolved()
    scenario.state_based_actions()


def _computed(scenario, card):
    return scenario.game.computed_board().of(card)


def test_the_cave_mode_puts_three_counters_and_makes_it_a_hasty_elemental_land():
    scenario = _board()
    cave = scenario.find("Captivating Cave", Zone.BATTLEFIELD, "alice")
    _cast(scenario, [CAVE_MODE] * 3)

    assert cave.counters[Counter.PLUS_ONE] == 9, "the same mode three times, CR 700.2d"
    computed = _computed(scenario, cave)
    assert computed.is_creature and computed.is_land, "CR 205.1b: it's still a land"
    assert "Cave" in computed.subtypes and "Elemental" in computed.subtypes
    assert (computed.power, computed.toughness) == (9, 9)
    assert computed.has_ability("Haste")
    assert cave.zone is Zone.BATTLEFIELD


def test_the_animation_has_no_duration_it_outlasts_the_turn():
    scenario = _board()
    cave = scenario.find("Captivating Cave", Zone.BATTLEFIELD, "alice")
    _cast(scenario, [CAVE_MODE, SEARCH_MODE, SEARCH_MODE])
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player == "bob":
        scenario.advance()
    computed = _computed(scenario, cave)
    assert computed.is_creature and (computed.power, computed.toughness) == (3, 3)


def test_the_search_mode_puts_a_cave_onto_the_battlefield_tapped():
    scenario = _board(library=["Forest", "Echoing Deeps", "Forest"])
    deeps = scenario.find("Echoing Deeps", Zone.LIBRARY, "alice")
    _cast(scenario, [SEARCH_MODE, SEARCH_MODE, SEARCH_MODE])
    assert deeps.zone is Zone.BATTLEFIELD
    assert deeps.tapped


def test_the_destroy_mode_destroys_the_targeted_enchantment():
    scenario = _board(bob=["Abundance"])
    abundance = scenario.find("Abundance", Zone.BATTLEFIELD, "bob")
    _cast(scenario, [DESTROY_MODE, SEARCH_MODE, SEARCH_MODE], targets=[abundance])
    assert abundance.zone is Zone.GRAVEYARD


def test_modes_mix_a_search_a_counter_mode_and_a_destroy():
    scenario = _board(library=["Forest", "Echoing Deeps"], bob=["Abundance"])
    cave = scenario.find("Captivating Cave", Zone.BATTLEFIELD, "alice")
    deeps = scenario.find("Echoing Deeps", Zone.LIBRARY, "alice")
    abundance = scenario.find("Abundance", Zone.BATTLEFIELD, "bob")
    _cast(scenario, [SEARCH_MODE, CAVE_MODE, DESTROY_MODE], targets=[abundance])
    assert deeps.zone is Zone.BATTLEFIELD
    assert abundance.zone is Zone.GRAVEYARD
    assert cave.counters[Counter.PLUS_ONE] + deeps.counters[Counter.PLUS_ONE] == 3


def test_with_two_caves_the_controller_chooses_which_one_each_time():
    """CR 608.2d: "a Cave you control" is chosen on resolution, per mode."""
    scenario = _board(extra_battlefield=["Echoing Deeps"])
    first = scenario.find("Captivating Cave", Zone.BATTLEFIELD, "alice")
    second = scenario.find("Echoing Deeps", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(second, times=2)
    scenario.will_choose_cards(first)
    _cast(scenario, [CAVE_MODE] * 3)
    assert second.counters[Counter.PLUS_ONE] == 6
    assert first.counters[Counter.PLUS_ONE] == 3
    assert scenario.game.computed_board().of(second).power == 6


def test_with_no_cave_the_counter_mode_does_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Cosmium Confluence"], battlefield=["Forest"] * 5, library=["Forest"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast(scenario, [CAVE_MODE] * 3)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest.counters[Counter.PLUS_ONE] == 0
    assert not scenario.game.computed_board().of(forest).is_creature
