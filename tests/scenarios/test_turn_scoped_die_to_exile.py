"""A spell's turn-long die-to-exile replacement, created on resolution beside
a mass -X/-X: "If a creature [an opponent controls] would die this turn,
exile it instead." (Malicious Malfunction, Flaying Tendrils, Malicious
Eclipse, Cry of the Carnarium), and Cry of the Carnarium's "Exile all
creature cards in all graveyards that were put there from the battlefield
this turn."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 614.1a** - an effect using "instead" is a replacement effect.
- **CR 611.2c** - the -2/-2 (it modifies characteristics) affects only the
  creatures on the battlefield as it resolves; the replacement modifies the
  rules of the game, so it applies to creatures that were not there then.
- **CR 700.4** - "dies" means put into a graveyard from the battlefield.
- **CR 608.2c** - instructions are followed in the order written: Cry's
  graveyard exile happens before the creatures its -2/-2 kills leave the
  battlefield, and those are exiled by the replacement afterwards (the
  card's own ruling, 2019-01-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _next_turn(scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        _resolve_stack(scenario)


def _board(spell, *, alice=(), bob=(), alice_hand=(), bob_hand=(), alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell, *alice_hand],
            battlefield=["Swamp", "Swamp", "Swamp", "Mountain", *alice],
            graveyard=list(alice_graveyard),
            library=["Swamp"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Mountain", *bob],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell) -> None:
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve(spell, *swamps)
    scenario.state_based_actions()
    _resolve_stack(scenario)


def _bolt(scenario, target, username="alice") -> None:
    (mountain, *_) = scenario.untapped_sources("Mountain", username=username)
    scenario.cast_and_resolve("Lightning Bolt", mountain, username=username, targets=[target])
    scenario.state_based_actions()
    _resolve_stack(scenario)


# -- "If a creature would die this turn, exile it instead." -----------------


def test_malicious_malfunction_exiles_every_creature_its_minus_two_kills():
    scenario = _board(
        "Malicious Malfunction", alice=["Grizzly Bears"], bob=["Grizzly Bears", "Hill Giant"]
    )
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast(scenario, "Malicious Malfunction")

    assert alice_bears.zone is Zone.EXILE
    assert bob_bears.zone is Zone.EXILE
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").graveyard == [
        scenario.find("Malicious Malfunction", Zone.GRAVEYARD, "alice")
    ]
    assert scenario.player("bob").graveyard == []


def test_a_creature_dying_later_this_turn_for_another_reason_is_exiled_too():
    """The card's own ruling: the replacement covers any death this turn,
    not only one the -2/-2 caused."""
    scenario = _board("Malicious Malfunction", bob=["Hill Giant"], alice_hand=["Lightning Bolt"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Malicious Malfunction")
    assert giant.zone is Zone.BATTLEFIELD

    _bolt(scenario, giant)

    assert giant.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []


def test_flaying_tendrils_exiles_a_creature_that_entered_after_it_resolved():
    """CR 611.2c: the replacement is not locked to the creatures present on
    resolution, unlike the -2/-2 (the entering creature does not shrink)."""
    scenario = _board("Flaying Tendrils", alice_hand=["Lightning Bolt", "Grizzly Bears"])
    _cast(scenario, "Flaying Tendrils")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    assert scenario.game.characteristics_of(bears).toughness == 2

    _bolt(scenario, bears)

    assert bears.zone is Zone.EXILE


def test_the_replacement_ends_with_the_turn():
    scenario = _board(
        "Malicious Malfunction",
        bob=["Hill Giant"],
        bob_hand=["Lightning Bolt"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Malicious Malfunction")
    assert scenario.game.created_replacements

    _next_turn(scenario)
    assert scenario.game.created_replacements == []
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, giant, username="bob")

    assert giant.zone is Zone.GRAVEYARD


# -- "If a creature an opponent controls would die this turn, ..." ----------


def test_malicious_eclipse_exiles_only_the_opponents_creatures():
    scenario = _board("Malicious Eclipse", alice=["Grizzly Bears"], bob=["Grizzly Bears"])
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario, "Malicious Eclipse")

    assert bob_bears.zone is Zone.EXILE
    assert alice_bears.zone is Zone.GRAVEYARD


def test_malicious_eclipse_still_exiles_an_opponents_creature_dying_later():
    scenario = _board("Malicious Eclipse", bob=["Hill Giant"], alice_hand=["Lightning Bolt"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Malicious Eclipse")

    _bolt(scenario, giant)

    assert giant.zone is Zone.EXILE


# -- Cry of the Carnarium ---------------------------------------------------


def test_cry_exiles_creature_cards_that_died_this_turn_but_not_older_ones():
    scenario = _board(
        "Cry of the Carnarium",
        alice=["Llanowar Elves"],
        alice_hand=["Lightning Bolt"],
        alice_graveyard=["Savannah Lions"],
        bob=["Hill Giant"],
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    lions = scenario.find("Savannah Lions", Zone.GRAVEYARD, "alice")
    _bolt(scenario, elves)
    assert elves.zone is Zone.GRAVEYARD

    _cast(scenario, "Cry of the Carnarium")

    assert elves.zone is Zone.EXILE
    assert lions.zone is Zone.GRAVEYARD


def test_cry_exiles_the_creatures_its_minus_two_kills_through_the_replacement():
    scenario = _board("Cry of the Carnarium", alice=["Grizzly Bears"], bob=["Grizzly Bears"])
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario, "Cry of the Carnarium")

    assert alice_bears.zone is Zone.EXILE
    assert bob_bears.zone is Zone.EXILE
