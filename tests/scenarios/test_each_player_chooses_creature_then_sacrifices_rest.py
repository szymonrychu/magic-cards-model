"""Scenario: "For each player, choose a creature that player controls. Each
player sacrifices all creatures they control not chosen this way." -
The Eternal Wanderer's own `-4`, CR 608.2c's two-instruction order: every
player's protective choice (CR 608.2d) is made first, in CR 101.4 APNAP
order, and only once every choice is in does the second instruction sweep
each player's *other* creatures to the graveyard (CR 701.21a).

A player with no creatures is asked nothing (CR 608.2d never offers an
impossible choice) and loses nothing. A player with exactly one creature has
no real choice - `Game.ask` is never called for them either - and it is the
one kept.

Every CR number here was looked up with `mise run rules:find <number>` in
the session that wrote this file: CR 608.2c, CR 608.2d, CR 101.4,
CR 701.21a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

WANDERER = "The Eternal Wanderer"


def _wanderer_index(scenario) -> int:
    wanderer = scenario.find(WANDERER, Zone.BATTLEFIELD, "alice")
    return next(
        i
        for i, ability in enumerate(scenario.game.activated_abilities(wanderer))
        if ability.raw.strip().lower().startswith("−4") or ability.raw.strip().startswith("-4")
    )


def test_each_players_chosen_creature_survives_and_the_rest_are_sacrificed():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[WANDERER, "Grizzly Bears", "Elvish Mystic", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Watchwolf", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()
    wanderer = scenario.find(WANDERER, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")
    memnite = scenario.creature("Memnite", "bob")

    index = _wanderer_index(scenario)
    scenario.will_choose_cards(bears, username="alice", source=WANDERER)
    scenario.will_choose_cards(watchwolf, username="bob", source=WANDERER)

    scenario.activate(wanderer, index=index, username="alice")
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD, "alice's own chosen creature survives"
    assert mystic.zone is Zone.GRAVEYARD, "an unchosen creature is sacrificed"
    assert elves.zone is Zone.GRAVEYARD, "an unchosen creature is sacrificed"
    assert watchwolf.zone is Zone.BATTLEFIELD, "bob's own chosen creature survives"
    assert memnite.zone is Zone.GRAVEYARD, "bob's unchosen creature is sacrificed"


def test_a_player_with_no_creatures_is_asked_nothing_and_loses_nothing():
    """CR 608.2d never offers an impossible choice - bob controls no
    creatures, so he is never asked to choose one, and nothing of his is
    swept (there is nothing to sweep)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[WANDERER, "Grizzly Bears", "Elvish Mystic"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()
    wanderer = scenario.find(WANDERER, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    index = _wanderer_index(scenario)
    scenario.will_choose_cards(bears, username="alice", source=WANDERER)

    scenario.activate(wanderer, index=index, username="alice")
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert mystic.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.BATTLEFIELD, "bob has no creature, so nothing of his moves"


def test_a_player_with_exactly_one_creature_is_never_asked_and_it_is_kept():
    """No real choice to make (CR 608.2d), so `Game.ask` is never called for
    bob - his single creature is simply the one kept."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[WANDERER, "Grizzly Bears", "Elvish Mystic"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()
    wanderer = scenario.find(WANDERER, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")

    index = _wanderer_index(scenario)
    scenario.will_choose_cards(bears, username="alice", source=WANDERER)

    scenario.activate(wanderer, index=index, username="alice")
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert mystic.zone is Zone.GRAVEYARD
    assert watchwolf.zone is Zone.BATTLEFIELD, "bob's only creature is kept without being asked"
