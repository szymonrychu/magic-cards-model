"""Card-in-zone target qualifiers enforced in a real game (CR 115.1, 400.7).

- **Reenact the Crime** - "Exile target nonland card in a graveyard that was
  put there from anywhere this turn." (CR 400.7: a card that changed zones is
  a new object, so only its latest arrival this turn counts)
- **Storrev, Devkarin Lich** - "... target creature or planeswalker card in
  your graveyard that wasn't put there this combat." (CR 506.1: each combat
  phase is its own combat)
- **Scrap Trawler** - "... target artifact card in your graveyard with lesser
  mana value." (than the artifact the trigger event named)
- **Edgewall Inn** - "Return target card that has an Adventure from your
  graveyard" (CR 715.1)

Rules looked up with `mise run rules:find`: CR 115.1, 400.7, 506.1, 715.1.
"""

import pytest

from magic_cards_model.machines import Phase, Step
from magic_cards_model.machines.keywords import discard
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- Reenact the Crime -----------------------------------------------------------


def _reenact_board(**alice) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Reenact the Crime", "Grizzly Bears", "Swamp"],
            battlefield=["Island"] * 4,
        )
        .player("bob", graveyard=["Llanowar Elves"], **alice)
    )


def test_reenact_the_crime_takes_a_card_discarded_this_turn():
    scenario = _reenact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    discard(scenario.game, bears, "alice")

    scenario.cast_onto_stack("Reenact the Crime", auto=True, targets=[bears])


def test_reenact_the_crime_refuses_a_card_already_in_the_graveyard():
    scenario = _reenact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob")

    with pytest.raises(ValueError, match="put there"):
        scenario.cast_onto_stack("Reenact the Crime", auto=True, targets=[elves])


def test_reenact_the_crime_refuses_a_card_that_came_back_and_left_in_another_turn():
    scenario = _reenact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob")
    scenario.game.return_to_hand(elves)
    scenario.game.exile_cards([elves])

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Reenact the Crime", auto=True, targets=[elves])


# -- Storrev -------------------------------------------------------------------


def _enter_combat(scenario) -> None:
    """Walk the turn into its combat phase the way play does, so the phase is
    counted (CR 506.1) - `start_at` places the turn without beginning it."""
    if scenario.step is Step.UNTAP:
        scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.turn.phase is not Phase.COMBAT:
        scenario.advance()


def _storrev_requirement():
    return profile_for_text(card("Storrev, Devkarin Lich").front_oracle_text).requirements[0]


def test_storrev_refuses_a_card_put_there_this_combat():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    _enter_combat(scenario)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    discard(scenario.game, bears, "alice")

    assert _storrev_requirement().rejects(bears, "alice", scenario.game) is not None


def test_storrev_takes_a_card_put_there_before_combat_began():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    discard(scenario.game, bears, "alice")
    _enter_combat(scenario)

    assert _storrev_requirement().rejects(bears, "alice", scenario.game) is None


def test_storrev_takes_a_card_that_was_already_in_the_graveyard():
    scenario = Scenario().player("alice", graveyard=["Grizzly Bears"]).player("bob").build()
    _enter_combat(scenario)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    assert _storrev_requirement().rejects(bears, "alice", scenario.game) is None


# -- Edgewall Inn --------------------------------------------------------------


def test_edgewall_inn_takes_only_a_card_with_an_adventure():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Bonecrusher Giant", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (requirement,) = profile_for_text(card("Edgewall Inn").front_oracle_text).requirements
    giant = scenario.find("Bonecrusher Giant", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    assert requirement.rejects(giant, "alice", scenario.game) is None
    assert "Adventure" in requirement.rejects(bears, "alice", scenario.game)


# -- Scrap Trawler -------------------------------------------------------------


def test_scrap_trawler_takes_only_a_lesser_mana_value_artifact_than_the_event_object():
    scenario = (
        Scenario().player("alice", graveyard=["Sol Ring", "Mind Stone"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    profile = profile_for_text(card("Scrap Trawler").front_oracle_text).for_event_subject(
        mana_value=2, power=None
    )
    (requirement,) = profile.requirements
    sol_ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    mind_stone = scenario.find("Mind Stone", Zone.GRAVEYARD, "alice")

    assert requirement.rejects(sol_ring, "alice", scenario.game) is None
    assert requirement.rejects(mind_stone, "alice", scenario.game) is not None


def test_groffskithur_returns_a_graveyard_copy_named_groffskithur_when_blocked():
    """ "Whenever this creature becomes blocked, you may return target card
    named Groffskithur from your graveyard to your hand." - the name is a
    name test (CR 201.2a), so the copy in the graveyard is a legal target
    when the trigger resolves (CR 608.2b), not only when it is announced."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Groffskithur"], graveyard=["Groffskithur"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature("Groffskithur", "alice")
    scenario.attack_with(attacker, defending="bob")
    scenario.block(attacker, scenario.creature("Grizzly Bears", "bob"))
    copy = scenario.find("Groffskithur", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(copy)
    scenario.will_take_the_may(True)

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert copy.zone is Zone.HAND
