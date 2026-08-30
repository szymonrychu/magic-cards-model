"""Scenario: the land allowance - how many lands a player may play this turn.

The mechanic is CR 305.2 and its comparison CR 305.2a/305.2b: one land a turn
by default, and a continuous effect from a static ability may increase the
number (CR 611.3d is the rule that lets a static ability allow it). The user's
example that this file exists for: with Azusa, Lost but Seeking ("You may play
two additional lands on each of your turns") on the battlefield, the engine
still refused the second land, because `Game.can_play_land` hardcoded the
allowance at one.

Rules cited below were verified in this session: `knowledge_search` gave the
rule numbers, and the full text was read from the 2026-08-19 CR release whose
sha256 matches the one `knowledge_search(type="cr_versions")` publishes.

- **CR 305.2** - "A player can normally play one land during their turn;
  however, continuous effects may increase this number."
- **CR 305.2a** - the comparison: "the number of lands the player can play
  this turn" against "the number of lands they have already played this turn
  (including lands played as special actions and lands played during the
  resolution of spells and abilities)". Greater, and the play is legal.
- **CR 305.2b** - "A player can't play a land, for any reason, if the number
  of lands the player can play this turn is equal to or less than the number
  of lands they have already played this turn."
- **CR 305.3** - "A player can't play a land, for any reason, if it isn't
  their turn. Ignore any part of an effect that instructs a player to do so."
  This is also what makes Azusa's "on each of your turns" restriction come
  free: the allowance is only ever consulted for the active player.
- **CR 305.4** - "Effects may also allow players to 'put' lands onto the
  battlefield. This isn't the same as 'playing a land' and doesn't count as a
  land played during the current turn."

Already covered elsewhere and referenced rather than duplicated: the plain
one-land limit with no Azusa is
`test_special_actions.py::test_only_one_land_per_turn` (the per-turn reset is
`test_turn_cycle.py`'s business), and a fetchland not using the land drop with
no Azusa is
`test_fetching_a_land.py::test_the_fetch_does_not_use_the_land_drop`. The test
below reruns the fetch arithmetic WITH Azusa on the board, because CR 305.4's
"put" must stay out of CR 305.2a's count at any allowance, not just at one.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def azusa_board(hand: list[str]) -> Scenario:
    """Alice controls Azusa, with the given hand and a land to find later."""
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            library=["Forest"],
            battlefield=["Azusa, Lost but Seeking"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Forest"])
    )


# -- the user's example -----------------------------------------------------


def test_azusa_makes_three_lands_playable_on_her_controllers_turn():
    """ "You may play two additional lands on each of your turns."

    One land by default plus two more is three: the first three plays go
    through, and the fourth is refused with the reason naming the numbers.
    """
    scenario = azusa_board(hand=["Forest", "Mountain", "Plains", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")
    assert scenario.game.can_play_land("alice"), "Azusa grants two additional lands"
    scenario.play_land("Mountain")
    assert scenario.game.can_play_land("alice"), "the third land play is still legal"
    scenario.play_land("Plains")

    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="3 of the 3 they may play this turn"):
        scenario.play_land("Island")

    assert scenario.find("Island", Zone.HAND), "the refused land stays in hand"
    names = scenario.battlefield_names()
    for played in ("Forest", "Mountain", "Plains"):
        assert played in names


def test_without_azusa_the_default_one_land_limit_still_holds():
    """The default is CR 305.2's one land, and the registry grants nothing when
    no granting permanent is controlled.

    The plain form of this is `test_special_actions.py::test_only_one_land_per_turn`;
    this is the same question asked from the other side of the fix - that the
    allowance code's default branch still reads one, not that Azusa works.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Forest", "Mountain"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")

    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="1 of the 1 they may play this turn"):
        scenario.play_land("Mountain")
    assert scenario.find("Mountain", Zone.HAND)


# -- whose Azusa ------------------------------------------------------------


def test_azusa_controlled_by_the_opponent_grants_the_player_nothing():
    """A static ability grants its controller and nobody else. Bob's Azusa is
    on the battlefield and gives Alice nothing, so the default one land holds
    for Alice however grand the card in play is.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Forest", "Mountain"], library=["Forest"])
        .player("bob", library=["Forest"], battlefield=["Azusa, Lost but Seeking"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")

    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="1 of the 1 they may play this turn"):
        scenario.play_land("Mountain")


# -- "put" is not "play" (CR 305.4) -----------------------------------------


def test_a_fetched_land_does_not_consume_the_allowance():
    """Arid Mesa finds a Plains and PUTS it onto the battlefield; CR 305.4 says
    that "doesn't count as a land played during the current turn". With Azusa
    up, the allowance is three, and the fetch must leave all three of them
    intact: the Forest, the Mountain and the second Plains all play afterwards.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest", "Mountain", "Plains"],
            library=["Plains", "Forest"],
            battlefield=["Azusa, Lost but Seeking", "Arid Mesa"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.find("Plains", Zone.BATTLEFIELD), "the fetch found its land"

    # None of the fetched Plains's arrival counted as a land play, so the
    # hand still holds the full allowance of three.
    scenario.play_land("Forest")
    scenario.play_land("Mountain")
    scenario.play_land("Plains")

    assert not scenario.game.can_play_land("alice"), "the allowance was three, now spent"


# -- the grant is only as durable as Azusa ----------------------------------


def test_azusa_leaving_mid_turn_drops_the_allowance_back():
    """CR 611.3b: a static ability's effect applies "at all times that the
    permanent generating it is on the battlefield". Azusa dies to a Lightning
    Bolt mid-turn, and the two land plays already made are now one more than
    the fallen allowance - so the third land is refused, even though it was
    legal before the Bolt resolved.
    """
    scenario = azusa_board(hand=["Forest", "Mountain", "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    azusa = scenario.find("Azusa, Lost but Seeking", Zone.BATTLEFIELD)

    scenario.play_land("Forest")
    scenario.play_land("Mountain")

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[azusa])

    assert azusa.zone is Zone.GRAVEYARD
    assert not scenario.game.can_play_land("alice")
    with pytest.raises(ValueError, match="2 of the 1 they may play this turn"):
        scenario.play_land("Plains")
    assert scenario.find("Plains", Zone.HAND)
