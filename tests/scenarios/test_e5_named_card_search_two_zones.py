"""Oko's Hospitality: "Creatures you control have base power and toughness 3/3
until end of turn. You may search your library and/or graveyard for a card
named Oko, the Trickster, reveal it, and put it into your hand. If you search
your library this way, shuffle."

- **CR 701.23a** a search looks at a zone for a card matching a description;
  "and/or" lets the player search either zone or both.
- **CR 701.24a** the library is shuffled only if it was searched.
- **CR 608.2d** "may" can be declined; nothing is searched then.
- **CR 613.4b** the base power and toughness set is layer 7b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

HOSPITALITY = "Oko's Hospitality"
OKO = "Oko, the Trickster"
BOTH, LIBRARY_ONLY, GRAVEYARD_ONLY = "library and graveyard", "library", "graveyard"


def _board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HOSPITALITY],
            battlefield=["Forest", "Forest", "Forest", "Island", "Island", "Grizzly Bears", "Serra Angel"],
            library=["Shock", OKO, "Opt", "Island", "Forest"],
            graveyard=[OKO],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario):
    return scenario.cast_and_resolve(HOSPITALITY, *scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island"))


def test_creatures_you_control_become_three_three_and_opponents_are_untouched():
    scenario = _board()
    scenario.will_take_the_may(False, source=HOSPITALITY)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario)
    for creature in (bears, angel):
        chars = scenario.game.characteristics_of(creature)
        assert (chars.power, chars.toughness) == (3, 3), creature.name
    assert scenario.game.characteristics_of(giant).power == 3
    assert scenario.game.characteristics_of(giant).toughness == 3


def test_finding_it_in_the_library_shuffles():
    scenario = _board()
    in_library = scenario.find(OKO, Zone.LIBRARY, "alice")
    shuffles = scenario.game.shuffles_performed
    scenario.will_take_the_may(True, source=HOSPITALITY)
    scenario.will_choose(LIBRARY_ONLY, username="alice", source=HOSPITALITY)
    scenario.will_choose_cards(in_library, username="alice", source=HOSPITALITY)
    _cast(scenario)
    assert in_library.zone is Zone.HAND
    assert scenario.game.shuffles_performed == shuffles + 1, "the library was shuffled"


def test_finding_it_in_the_graveyard_alone_does_not_shuffle():
    scenario = _board()
    in_graveyard = scenario.find(OKO, Zone.GRAVEYARD, "alice")
    shuffles = scenario.game.shuffles_performed
    scenario.will_take_the_may(True, source=HOSPITALITY)
    scenario.will_choose(GRAVEYARD_ONLY, username="alice", source=HOSPITALITY)
    scenario.will_choose_cards(in_graveyard, username="alice", source=HOSPITALITY)
    _cast(scenario)
    assert in_graveyard.zone is Zone.HAND
    assert scenario.game.shuffles_performed == shuffles, "library never searched: no shuffle"


def test_searching_both_zones_takes_one_card_and_shuffles():
    scenario = _board()
    in_graveyard = scenario.find(OKO, Zone.GRAVEYARD, "alice")
    in_library = scenario.find(OKO, Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=HOSPITALITY)
    scenario.will_choose(BOTH, username="alice", source=HOSPITALITY)
    scenario.will_choose_cards(in_graveyard, username="alice", source=HOSPITALITY)
    shuffles = scenario.game.shuffles_performed
    _cast(scenario)
    assert in_graveyard.zone is Zone.HAND
    assert in_library.zone is Zone.LIBRARY, "only one card is put into hand"
    assert scenario.game.shuffles_performed == shuffles + 1, "library was searched: shuffled"


def test_declining_the_may_searches_nothing_and_does_not_shuffle():
    scenario = _board()
    before = [c.id for c in scenario.player("alice").library]
    shuffles = scenario.game.shuffles_performed
    scenario.will_take_the_may(False, source=HOSPITALITY)
    _cast(scenario)
    assert [c.id for c in scenario.player("alice").library] == before
    assert scenario.game.shuffles_performed == shuffles
    assert scenario.find(OKO, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_searching_the_library_for_a_card_that_is_not_there_still_shuffles():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HOSPITALITY],
            battlefield=["Forest", "Forest", "Forest", "Island", "Island"],
            library=["Shock", "Opt", "Island", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shuffles = scenario.game.shuffles_performed
    scenario.will_take_the_may(True, source=HOSPITALITY)
    scenario.will_choose(LIBRARY_ONLY, username="alice", source=HOSPITALITY)
    scenario.cast_and_resolve(HOSPITALITY, *scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island"))
    assert scenario.game.shuffles_performed == shuffles + 1
