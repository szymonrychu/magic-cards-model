"""Graveyard-wide instructions (EP-01 R2, T2 residual clauses).

CR numbers verified with `mise run rules:find`:

- CR 406.2 / CR 701.13a: to exile an object is to move it to the exile zone
  from wherever it is - a whole graveyard, a permanent, or both at once.
- CR 700.4: "dies" is "is put into a graveyard from the battlefield".
- CR 608.2c: the controller follows an ability's instructions in the order
  written, which is what makes "exile it and each player returns ..." read as
  exile first, return second (the exiled source is never among the returned).

Printings: Silent Gravestone ("Exile this artifact and all cards from all
graveyards. Draw a card.") and Underworld Cerberus ("When this creature dies,
exile it and each player returns all creature cards from their graveyard to
their hand."). Empty the Catacombs is the second printing of the "each player
returns all <cards> from their graveyard to their hand" shape.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _names(cards) -> list[str]:
    return sorted(card.name for card in cards)


def test_silent_gravestone_exiles_itself_and_every_graveyard_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"],
            battlefield=["Silent Gravestone", "Mountain", "Mountain", "Mountain", "Mountain"],
            graveyard=["Llanowar Elves", "Lightning Bolt"],
        )
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gravestone = scenario.find("Silent Gravestone", Zone.BATTLEFIELD, "alice")
    lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.activate(gravestone, *lands, tapping_for_cost=[gravestone])
    scenario.pass_until_resolved()

    assert not scenario.player("alice").graveyard
    assert not scenario.player("bob").graveyard
    assert _names(scenario.game.exile) == [
        "Grizzly Bears",
        "Lightning Bolt",
        "Llanowar Elves",
        "Silent Gravestone",
    ]
    assert gravestone.zone is Zone.EXILE
    assert [c.name for c in scenario.player("alice").hand] == ["Island"]


def test_silent_gravestone_sweep_still_runs_when_the_gravestone_is_already_gone():
    """CR 400.7: the ability exists independently of its source (CR 113.7a);
    if the Gravestone left first, only the graveyard half and the draw happen."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"],
            battlefield=["Silent Gravestone", "Mountain", "Mountain", "Mountain", "Mountain"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gravestone = scenario.find("Silent Gravestone", Zone.BATTLEFIELD, "alice")
    lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.activate(gravestone, *lands, tapping_for_cost=[gravestone])
    scenario.game.exile_permanent(gravestone)
    scenario.pass_until_resolved()

    assert not scenario.player("bob").graveyard
    assert not scenario.player("alice").graveyard
    assert [c.name for c in scenario.player("alice").hand] == ["Island"]


def test_underworld_cerberus_dies_exiles_itself_and_returns_creatures_for_each_player():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Underworld Cerberus"],
            graveyard=["Llanowar Elves", "Lightning Bolt"],
        )
        .player("bob", graveyard=["Grizzly Bears", "Shock"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cerberus = scenario.find("Underworld Cerberus", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(cerberus)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert cerberus.zone is Zone.EXILE
    assert _names(scenario.player("alice").hand) == ["Llanowar Elves"]
    assert _names(scenario.player("bob").hand) == ["Grizzly Bears"]
    assert _names(scenario.player("alice").graveyard) == ["Lightning Bolt"]
    assert _names(scenario.player("bob").graveyard) == ["Shock"]


def test_underworld_cerberus_is_not_among_the_cards_it_returns():
    """The exile comes first (CR 608.2c), so the dead Cerberus is never one of
    the creature cards returned to its owner's hand."""
    scenario = Scenario().player("alice", battlefield=["Underworld Cerberus"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cerberus = scenario.find("Underworld Cerberus", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(cerberus)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert cerberus.zone is Zone.EXILE
    assert not scenario.player("alice").hand


def test_empty_the_catacombs_returns_creature_cards_for_each_player():
    """Second printing of "each player returns all creature cards from their
    graveyard to their hand" - a sorcery, so the spell path."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Empty the Catacombs"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            graveyard=["Llanowar Elves", "Lightning Bolt"],
        )
        .player("bob", graveyard=["Grizzly Bears", "Shock"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Empty the Catacombs", *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    )

    assert _names(scenario.player("alice").hand) == ["Llanowar Elves"]
    assert _names(scenario.player("bob").hand) == ["Grizzly Bears"]
    assert _names(scenario.player("alice").graveyard) == ["Empty the Catacombs", "Lightning Bolt"]
    assert _names(scenario.player("bob").graveyard) == ["Shock"]
