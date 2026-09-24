"""Land-play permissions from a permanent's static abilities: "You may play an
additional land on each of your turns." and "You may play lands from your
graveyard." (Icetill Explorer, which prints both).

Second printings, each legal in Modern and Pioneer and in no deck in the api's
pool: Azusa, Lost but Seeking's "You may play two additional lands on each of
your turns." (a count other than one) and Crucible of Worlds' "You may play
lands from your graveyard." (on an artifact). This is the land-play template,
not the cast-from-graveyard one: nothing here lets a land be *cast*.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 305.2** - "A player can normally play one land during their turn;
  however, continuous effects may increase this number."
- **CR 305.2a** / **CR 305.2b** - compare the lands a player can play with the
  lands already played; a player can't play a land when the second is not
  less than the first.
- **CR 305.1** - playing a land is a special action, normally "from their
  hand"; the graveyard permission widens where from.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

EXPLORER = "Icetill Explorer"


def board(
    alice: list[str],
    *,
    hand: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice,
            hand=hand or [],
            graveyard=graveyard or [],
            library=["Island"] * 10,
        )
        .player(
            "bob",
            battlefield=bob or [],
            graveyard=bob_graveyard or [],
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def play(scenario: PlayedScenario, name: str, from_zone: Zone = Zone.HAND) -> None:
    """Play a land, then let the Explorer's own landfall mill resolve, so the
    stack is empty again for the next land drop (CR 305.1)."""
    scenario.play_land(name, from_zone=from_zone)
    while scenario.game.pending_triggers or scenario.game.stack:
        scenario.pass_until_resolved()


def land_actions(scenario: PlayedScenario, username: str = "alice") -> list[tuple[str, Zone]]:
    found = []
    for action in legal_actions(scenario.game, username):
        if action.kind is ActionKind.PLAY_LAND:
            state = scenario.game.find_by_id(action.card_id)
            found.append((state.name, action.from_zone))
    return sorted(found)


@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        (EXPLORER, "additional land"),
        (EXPLORER, "from your graveyard"),
        ("Azusa, Lost but Seeking", "additional lands"),
        ("Crucible of Worlds", "from your graveyard"),
        ("Dryad of the Ilysian Grove", "additional land"),
        ("Ancient Greenwarden", "from your graveyard"),
    ],
)
def test_the_permission_line_is_handled(name: str, phrase: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if phrase in c.text]

    assert clause.category == HANDLED


# -- an additional land (CR 305.2) ---------------------------------------------


def test_the_explorer_allows_a_second_land_drop() -> None:
    scenario = board([EXPLORER], hand=["Forest", "Island", "Swamp"])

    assert scenario.game.land_allowance("alice") == 2
    play(scenario, "Forest")
    play(scenario, "Island")

    with pytest.raises(ValueError, match=r"CR 305\.2a"):
        scenario.play_land("Swamp")


def test_without_it_one_land_is_the_limit() -> None:
    scenario = board([], hand=["Forest", "Island"])
    scenario.play_land("Forest")

    with pytest.raises(ValueError, match=r"CR 305\.2a"):
        scenario.play_land("Island")


def test_two_explorers_allow_three_land_drops() -> None:
    scenario = board([EXPLORER, EXPLORER])

    assert scenario.game.land_allowance("alice") == 3


def test_a_count_of_two_additional_lands_is_read() -> None:
    """Azusa: "two additional lands" - three in all."""
    scenario = board(["Azusa, Lost but Seeking"])

    assert scenario.game.land_allowance("alice") == 3


def test_an_opponent_s_explorer_gives_me_nothing() -> None:
    scenario = board([], bob=[EXPLORER])

    assert scenario.game.land_allowance("alice") == 1
    assert scenario.game.land_allowance("bob") == 2


def test_the_extra_drop_goes_when_the_explorer_does() -> None:
    scenario = board([EXPLORER], hand=["Forest", "Island"])
    play(scenario, "Forest")
    scenario.game.put_into_graveyard(scenario.creature(EXPLORER, "alice"))

    with pytest.raises(ValueError, match=r"CR 305\.2a"):
        scenario.play_land("Island")


# -- lands from your graveyard ------------------------------------------------


def test_a_land_in_your_graveyard_may_be_played() -> None:
    scenario = board([EXPLORER], graveyard=["Forest"])

    assert ("Forest", Zone.GRAVEYARD) in land_actions(scenario)
    forest = scenario.play_land("Forest", from_zone=Zone.GRAVEYARD)

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").graveyard == []
    assert scenario.game.lands_played["alice"] == 1


def test_without_the_permission_the_graveyard_is_closed() -> None:
    scenario = board([], graveyard=["Forest"])

    assert ("Forest", Zone.GRAVEYARD) not in land_actions(scenario)
    with pytest.raises(ValueError, match="nothing allows"):
        scenario.play_land("Forest", from_zone=Zone.GRAVEYARD)


def test_an_opponent_s_graveyard_is_not_your_graveyard() -> None:
    """ "your graveyard" - bob's Forest is not alice's to play."""
    scenario = board([EXPLORER], bob_graveyard=["Forest"])

    assert land_actions(scenario) == []


def test_a_nonland_card_in_the_graveyard_is_not_offered() -> None:
    scenario = board([EXPLORER], graveyard=["Grizzly Bears"])

    assert land_actions(scenario) == []


def test_a_graveyard_land_uses_a_land_drop() -> None:
    """Crucible of Worlds grants no extra drop: the graveyard land is the one."""
    scenario = board(["Crucible of Worlds"], hand=["Island"], graveyard=["Forest"])
    scenario.play_land("Forest", from_zone=Zone.GRAVEYARD)

    with pytest.raises(ValueError, match=r"CR 305\.2a"):
        scenario.play_land("Island")


def test_the_explorer_gives_both_a_second_drop_and_the_graveyard() -> None:
    scenario = board([EXPLORER], hand=["Island"], graveyard=["Forest"])

    play(scenario, "Forest", Zone.GRAVEYARD)
    play(scenario, "Island")

    assert sorted(s.name for s in scenario.game.battlefield if s.card.is_land) == [
        "Forest",
        "Island",
    ]


def test_the_permission_ends_when_the_source_leaves() -> None:
    scenario = board(["Crucible of Worlds"], graveyard=["Forest"])
    crucible = next(s for s in scenario.game.battlefield if s.name == "Crucible of Worlds")
    scenario.game.put_into_graveyard(crucible)

    assert land_actions(scenario) == []


def test_it_is_not_a_play_on_the_opponent_s_turn() -> None:
    """CR 305.3 still applies: never on another player's turn."""
    scenario = board([], bob=[EXPLORER], bob_graveyard=["Forest"])

    assert land_actions(scenario, "bob") == []
