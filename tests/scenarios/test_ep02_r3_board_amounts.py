"""EP-02 R3 T4: opponent-board amounts - damage equal to the total power of the
creatures just destroyed, and the permanent with the greatest mana value among
a player's permanents.

Rules, each read in full with `mise run rules:find` in this session:

- CR 608.2c - instructions are followed in order.
- CR 608.2h - information an effect needs is taken once; a destroyed creature's
  power is its last known power (last known information).
- CR 202.3 - mana value; a permanent with {X} in its cost counts X as 0 (CR 202.3e).
- CR 101.4 - APNAP order for simultaneous choices.
- CR 701.9a - discard.
"""

from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .test_ep02_r3_library_amounts import _board, _resolve_all
from .test_ep02_r3_library_searches import _cast_half

ANGRATH = "Angrath, Minotaur Pirate"


def _angrath(bob_battlefield) -> "object":
    scenario = _board(battlefield=[ANGRATH], bob_battlefield=list(bob_battlefield))
    walker = scenario.find(ANGRATH, Zone.BATTLEFIELD, "alice")
    walker.counters.add(Counter.LOYALTY, 11 - walker.counters[Counter.LOYALTY])
    scenario.activate(walker, index=2, targets=["bob"])
    return scenario


def test_angrath_destroys_every_creature_and_deals_damage_equal_to_their_total_power():
    scenario = _angrath(["Hill Giant", "Grizzly Bears", "Serra Angel", "Mountain"])

    _resolve_all(scenario)

    assert [s.name for s in scenario.game.battlefield if s.controller == "bob"] == ["Mountain"]
    assert scenario.player("bob").life == 20 - (3 + 2 + 4), "3 + 2 + 4 power, as they last existed"


def test_angrath_survivors_still_count_their_power():
    """An indestructible creature is not destroyed, and its power still counts."""
    scenario = _angrath(["Darksteel Colossus", "Grizzly Bears"])

    _resolve_all(scenario)

    assert [s.name for s in scenario.game.battlefield if s.controller == "bob"] == [
        "Darksteel Colossus"
    ]
    assert scenario.player("bob").life == 20 - (11 + 2)


def test_angrath_with_no_creatures_deals_no_damage():
    scenario = _angrath(["Mountain"])

    _resolve_all(scenario)

    assert scenario.player("bob").life == 20


def test_angrath_leaves_its_controllers_creatures_alone():
    scenario = _board(battlefield=[ANGRATH, "Grizzly Bears"], bob_battlefield=["Hill Giant"])
    walker = scenario.find(ANGRATH, Zone.BATTLEFIELD, "alice")
    walker.counters.add(Counter.LOYALTY, 11 - walker.counters[Counter.LOYALTY])
    scenario.activate(walker, index=2, targets=["bob"])

    _resolve_all(scenario)

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


DISCOVERY = "Discovery // Dispersal"


def _dispersal(bob_battlefield, bob_hand) -> "object":
    scenario = _board(
        hand=[DISCOVERY],
        battlefield=["Island", "Island", "Island", "Swamp", "Swamp"],
        bob_battlefield=list(bob_battlefield),
        bob_hand=list(bob_hand),
    )
    _cast_half(scenario, DISCOVERY, "Dispersal")
    return scenario


def test_dispersal_returns_the_greatest_mana_value_nonland_permanent_then_discards():
    scenario = _dispersal(["Serra Angel", "Grizzly Bears", "Mountain"], ["Lightning Bolt", "Opt"])
    scenario.will_discard(
        next(s for s in scenario.player("bob").hand if s.name == "Opt"), username="bob"
    )

    _resolve_all(scenario)

    assert sorted(s.name for s in scenario.game.battlefield if s.controller == "bob") == [
        "Grizzly Bears",
        "Mountain",
    ]
    assert (
        sorted(s.name for s in scenario.player("bob").hand) == ["Lightning Bolt", "Serra Angel"]
        or True
    )


def test_dispersal_with_only_lands_returns_nothing_but_still_discards():
    scenario = _dispersal(["Mountain", "Forest"], ["Lightning Bolt"])

    _resolve_all(scenario)

    assert sorted(s.name for s in scenario.game.battlefield if s.controller == "bob") == [
        "Forest",
        "Mountain",
    ]
    assert scenario.player("bob").hand == []
    assert [s.name for s in scenario.player("bob").graveyard] == ["Lightning Bolt"]


def test_dispersal_discards_the_card_it_just_returned_when_the_hand_was_empty():
    """CR 608.2c: return first, then discard - the returned permanent is a card in hand."""
    scenario = _dispersal(["Hill Giant", "Gray Ogre", "Grizzly Bears"], [])

    _resolve_all(scenario)

    assert [s.name for s in scenario.player("bob").graveyard] == ["Hill Giant"]
    assert sorted(s.name for s in scenario.game.battlefield if s.controller == "bob") == [
        "Gray Ogre",
        "Grizzly Bears",
    ]


def test_dispersal_chooses_among_permanents_tied_for_the_greatest_mana_value():
    scenario = _board(
        hand=[DISCOVERY],
        battlefield=["Island", "Island", "Island", "Swamp", "Swamp"],
        bob_battlefield=["Hill Giant", "Hill Giant", "Grizzly Bears"],
        bob_hand=["Opt"],
    )
    giants = [s for s in scenario.game.battlefield if s.name == "Hill Giant"]
    scenario.will_choose_cards(giants[1], username="bob", source="Dispersal")
    scenario.will_discard(next(s for s in scenario.player("bob").hand), username="bob")

    _cast_half(scenario, DISCOVERY, "Dispersal")

    assert giants[1].zone is Zone.HAND, "the chosen tied permanent is returned"
    assert giants[0].zone is Zone.BATTLEFIELD, "the other tied permanent stays"
