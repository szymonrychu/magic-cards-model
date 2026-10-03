"""A returned creature that is exiled instead of leaving the battlefield.

Geth, Thane of Contracts: "{1}{B}{B}, {T}: Return target creature card from
your graveyard to the battlefield. It gains "If this creature would leave the
battlefield, exile it instead of putting it anywhere else." Activate only as a
sorcery." - a quoted ability the returned creature gains.

Whip of Erebos (the second printing, differently worded): "{2}{B}{B}, {T}:
Return target creature card from your graveyard to the battlefield. It gains
haste. Exile it at the beginning of the next end step. If it would leave the
battlefield, exile it instead of putting it anywhere else. Activate only as a
sorcery and only once each turn." - the same replacement as an unquoted rider,
which is an effect of the resolving ability rather than an ability the
creature has.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 614.1a** - an effect that uses the word "instead" is a replacement
  effect.
- **CR 614.6** - a replaced event never happens: the creature never reaches
  the hand, library or graveyard, so it did not die and was not bounced.
- **CR 400.7** - a creature that leaves and returns is a new object with no
  memory of the old one, so neither the grant nor the rider follows it.
- **CR 611.2a** - no stated duration: it lasts as long as the object does, so
  the returning ability's own source leaving changes nothing.
- **CR 613.1f** - the quoted ability is a layer 6 grant.
- **CR 701.21a** - sacrificing moves a permanent to the graveyard, so the
  replacement applies to it.
- **CR 602.5d** - "Activate only as a sorcery".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LINE = "If this creature would leave the battlefield, exile it instead of putting it anywhere else."


def _geth_board(*, graveyard=("Grizzly Bears",), hand=(), extra=()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Geth, Thane of Contracts", *["Swamp"] * 3, *extra],
            graveyard=list(graveyard),
            library=["Swamp"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Unsummon", "Diabolic Edict"],
            battlefield=["Mountain", "Island", "Swamp"],
            library=["Swamp"] * 5,
        )
    )


def _whip_board(*, graveyard=("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Whip of Erebos", *["Swamp"] * 4],
            graveyard=list(graveyard),
            library=["Swamp"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Unsummon", "Diabolic Edict"],
            battlefield=["Mountain", "Island", "Swamp"],
            library=["Swamp"] * 5,
        )
    )


def _geth_returns(scenario, name="Grizzly Bears"):
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    target = scenario.find(name, Zone.GRAVEYARD, "alice")
    scenario.activate(
        geth,
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[target],
    )
    scenario.pass_until_resolved()
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def _whip_returns(scenario, name="Grizzly Bears"):
    whip = scenario.find("Whip of Erebos", Zone.BATTLEFIELD, "alice")
    target = scenario.find(name, Zone.GRAVEYARD, "alice")
    scenario.activate(
        whip,
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice"),
        targets=[target],
    )
    scenario.pass_until_resolved()
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def _bob_casts(scenario, spell, source_land, target):
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        spell,
        *scenario.untapped_sources(source_land, username="bob"),
        targets=[target],
        username="bob",
    )


@pytest.fixture(params=["geth", "whip"])
def printing(request):
    """The two printings, so each corner case runs against the quoted grant and
    the unquoted rider alike."""
    if request.param == "geth":
        scenario = _geth_board().build()
        scenario.start_at(Step.PRECOMBAT_MAIN)
        return scenario, _geth_returns(scenario)
    scenario = _whip_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, _whip_returns(scenario)


# -- the grant ----------------------------------------------------------------


def test_geth_returns_the_creature_and_it_gains_the_quoted_replacement():
    scenario = _geth_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _geth_returns(scenario)
    assert bears.zone is Zone.BATTLEFIELD
    assert LINE in scenario.game.computed_board().of(bears).abilities


def test_geths_minus_one_minus_one_applies_to_the_returned_creature_but_not_geth():
    """ "Other creatures you control get -1/-1." - Grizzly Bears 2/2 becomes 1/1."""
    scenario = _geth_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _geth_returns(scenario)
    board = scenario.game.computed_board()
    assert (board.of(bears).power, board.of(bears).toughness) == (1, 1)
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    assert (board.of(geth).power, board.of(geth).toughness) == (3, 4)


def test_a_one_toughness_creature_dies_to_geths_shrink_and_is_exiled_not_buried():
    """Llanowar Elves returns as a 0/0 (CR 704.5f) - the replacement is already
    there when state-based actions put it into a graveyard, so it is exiled."""
    scenario = _geth_board(graveyard=("Llanowar Elves",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.activate(
        geth,
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[elves],
    )
    scenario.pass_until_resolved()
    scenario.state_based_actions()
    assert elves.zone is Zone.EXILE


def test_a_creature_that_geth_did_not_return_dies_to_the_graveyard_normally():
    scenario = _geth_board(extra=["Serra Angel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _geth_returns(scenario)
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(angel)
    assert angel.zone is Zone.GRAVEYARD


def test_geth_cannot_be_activated_outside_a_main_phase_with_an_empty_stack():
    """CR 602.5d."""
    scenario = _geth_board().build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    assert scenario.why_cannot_activate(geth) is not None


def test_geth_will_not_return_a_noncreature_card():
    scenario = _geth_board(graveyard=("Lightning Bolt",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        scenario.activate(
            geth,
            *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
            targets=[bolt],
        )


# -- every way off the battlefield (both printings) ----------------------------


def test_destroyed_it_is_exiled_instead_of_going_to_the_graveyard(printing):
    scenario, bears = printing
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE
    assert bears not in scenario.player("alice").graveyard


def test_bounced_it_is_exiled_instead_of_returning_to_hand(printing):
    scenario, bears = printing
    scenario.game.return_to_hand(bears)
    assert bears.zone is Zone.EXILE
    assert bears not in scenario.player("alice").hand


def test_sacrificed_it_is_exiled_instead_of_going_to_the_graveyard(printing):
    scenario, bears = printing
    scenario.game.sacrifice(bears)
    assert bears.zone is Zone.EXILE


def test_put_into_a_library_it_is_exiled_instead(printing):
    scenario, bears = printing
    library_before = len(scenario.player("alice").library)
    scenario.game.put_cards_into_library([bears])
    assert bears.zone is Zone.EXILE
    assert len(scenario.player("alice").library) == library_before


def test_killed_by_damage_it_is_exiled(printing):
    scenario, bears = printing
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        targets=[bears],
        username="bob",
    )
    scenario.state_based_actions()
    assert bears.zone is Zone.EXILE


def test_a_bounce_spell_exiles_it(printing):
    scenario, bears = printing
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        targets=[bears],
        username="bob",
    )
    assert bears.zone is Zone.EXILE


def test_already_exiled_it_stays_exiled_once(printing):
    scenario, bears = printing
    scenario.game.exile_permanent(bears)
    assert bears.zone is Zone.EXILE
    assert scenario.game.exile.count(bears) == 1


def test_it_does_not_die_when_exiled_instead(printing):
    """CR 614.6: the graveyard move never happened, so nothing died."""
    scenario, bears = printing
    died_before = scenario.game.creatures_died_this_turn
    scenario.game.destroy(bears)
    assert scenario.game.creatures_died_this_turn == died_before


def test_the_replacement_does_not_follow_a_creature_that_left_and_came_back(printing):
    """CR 400.7: put it onto the battlefield again and it is a new object."""
    scenario, bears = printing
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE
    again = scenario.game.put_onto_battlefield(bears, "alice")
    scenario.game.destroy(again)
    assert again.zone is Zone.GRAVEYARD


# -- the source leaving -------------------------------------------------------


def test_geth_leaving_does_not_end_the_granted_replacement():
    scenario = _geth_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _geth_returns(scenario)
    geth = scenario.find("Geth, Thane of Contracts", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(geth)
    assert geth.zone is Zone.GRAVEYARD
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE


def test_whip_leaving_does_not_end_the_replacement():
    scenario = _whip_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _whip_returns(scenario)
    whip = scenario.find("Whip of Erebos", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(whip)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE


def test_whip_still_gives_haste_and_exiles_at_the_next_end_step():
    scenario = _whip_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _whip_returns(scenario)
    assert scenario.game.computed_board().of(bears).has_ability("Haste")
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.EXILE


def test_two_returned_creatures_each_carry_their_own_replacement():
    scenario = _geth_board(graveyard=("Grizzly Bears", "Llanowar Elves"), extra=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _geth_returns(scenario)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert elves.zone is Zone.GRAVEYARD


# -- CR 702.84a: unearth expands to the same sentence ---------------------------


def test_an_unearthed_creature_is_exiled_instead_of_dying_before_the_end_step():
    """Unearth's reminder is this same rider; it used to be unmodelled."""
    from magic_cards_model.machines.keywords import unearth_activation
    from tests.scenarios.harness import mana_from

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Cityscape Leveler"], battlefield=["Mountain"] * 8)
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    activation = unearth_activation(scenario.game, leveler, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*(["Mountain"] * 8)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    entered = activation.resolve()

    scenario.game.destroy(entered)
    assert entered.zone is Zone.EXILE
