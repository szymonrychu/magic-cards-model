"""An optional blight (CR 701.68a) as an additional cost (CR 118.8b), and the
spell's own "If this spell's additional cost was paid, ... instead"
consequence (CR 614.1a) read back off the announcement as the spell
resolves (CR 608.2c).

Burning Curiosity: "As an additional cost to cast this spell, you may blight
1. Exile the top two cards of your library. If this spell's additional cost
was paid, exile the top three cards instead. Until the end of your next turn,
you may play those cards." The "instead" replaces the count of the exile
before it, and "those cards" (CR 607.1) is whichever set was actually
exiled - two or three.

Cinder Strike is the second printing, off the deck pool, with the same
condition in the other word order (the alternative first, "... instead if
this spell's additional cost was paid") on a damage sentence: "Cinder Strike
deals 2 damage to target creature. It deals 4 damage to that creature instead
if this spell's additional cost was paid." Both ask the one condition reader
(`Game.condition_holds`), not a keyword by name.

The card's own rulings: the counters all go on one creature, and a player who
controls no creature cannot choose to blight at all.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CURIOSITY = "Burning Curiosity"
LIBRARY = ["Forest", "Lightning Bolt", "Island", "Swamp", "Mountain"]


def _board(*, battlefield_extra: list[str] | None = None, library: list[str] | None = None):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CURIOSITY],
            battlefield=["Mountain", "Mountain", "Mountain", *(battlefield_extra or [])],
            library=library if library is not None else list(LIBRARY),
        )
        .player("bob", library=["Island"] * 5, battlefield=["Tarmogoyf"])
    )


def _cast(scenario: Scenario, *, blight=None) -> list:
    before = {state.id for state in scenario.game.exile}
    casting = scenario.cast(CURIOSITY)
    if blight is not None:
        casting.pay_blight(blight)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return [state for state in scenario.game.exile if state.id not in before]


def _end_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()


def test_unblighted_it_exiles_two_and_permits_both():
    scenario = _board(battlefield_extra=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    exiled = _cast(scenario)

    assert [state.name for state in exiled] == ["Forest", "Lightning Bolt"]
    assert bears.counters[Counter.MINUS_ONE] == 0
    for state in exiled:
        assert scenario.game.play_permission_for(state, "alice", PlayAction.PLAY) is not None


def test_blighted_it_exiles_three_instead_and_permits_all_three():
    scenario = _board(battlefield_extra=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    exiled = _cast(scenario, blight=bears)

    assert [state.name for state in exiled] == ["Forest", "Lightning Bolt", "Island"]
    assert bears.counters[Counter.MINUS_ONE] == 1
    assert [state.name for state in scenario.player("alice").library] == ["Swamp", "Mountain"]
    for state in exiled:
        assert scenario.game.play_permission_for(state, "alice", PlayAction.PLAY) is not None


def test_blighting_a_one_toughness_creature_still_counts_as_paid():
    """The ruling: the creature need not survive - the cost was paid."""
    scenario = _board(battlefield_extra=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")

    exiled = _cast(scenario, blight=memnite)

    assert memnite.zone is Zone.GRAVEYARD
    assert len(exiled) == 3


def test_an_opponents_creature_cannot_pay_the_blight():
    """CR 701.68a: "a creature you control"."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "bob")

    casting = scenario.cast(CURIOSITY)
    casting.pay_blight(goyf)
    with pytest.raises(ValueError, match="does not control"):
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
        scenario.put_on_stack(casting)

    assert goyf.counters[Counter.MINUS_ONE] == 0


def test_with_no_creature_to_blight_it_exiles_two():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _cast(scenario)

    assert len(exiled) == 2


def test_blighted_with_a_short_library_it_exiles_what_is_there():
    scenario = _board(battlefield_extra=["Grizzly Bears"], library=["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    exiled = _cast(scenario, blight=bears)

    assert [state.name for state in exiled] == ["Forest", "Island"]
    assert scenario.player("alice").library == []


def test_the_permission_lasts_until_the_end_of_the_casters_next_turn():
    scenario = _board(battlefield_extra=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    exiled = _cast(scenario, blight=bears)

    _end_turn(scenario)
    _end_turn(scenario)
    assert scenario.turn.active_player == "alice"
    assert all(scenario.game.play_permission_for(s, "alice", PlayAction.PLAY) for s in exiled)
    _end_turn(scenario)
    assert not any(scenario.game.play_permission_for(s, "alice", PlayAction.PLAY) for s in exiled)


# --------------------------------------------------------------------------
# Cinder Strike: the same condition, the other word order
# --------------------------------------------------------------------------


def _strike_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Cinder Strike"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
    )


def _strike(scenario: Scenario, target, *, blight=None) -> None:
    casting = scenario.cast("Cinder Strike")
    if blight is not None:
        casting.pay_blight(blight)
    casting.choose_targets([target])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_cinder_strike_unblighted_deals_two():
    scenario = _strike_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Colossal Dreadmaw", "bob")

    _strike(scenario, wurm)

    assert wurm.damage == 2


def test_cinder_strike_blighted_deals_four_instead():
    scenario = _strike_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    _strike(scenario, wurm, blight=bears)

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert wurm.damage == 4
