"""A card put into a library from a public zone is known where it went.

CR 400.2: "Public zones are zones in which all players can see the cards'
faces ... Graveyard, battlefield, stack, exile, ante, and command are public
zones." A spell on the stack is seen by every player, and so is the owner
putting it on the top or the bottom of their library. What is recorded is the
same knowledge policy a public-zone-to-hand move already follows (battle 5,
B5-04): every player knows the card, at that position, until the library is
reordered (CR 701.20d) or the card moves again (CR 400.7), and a draw carries
it into the hand, where it stays known until it leaves.

CR 401.4 is the limit: "If an effect puts two or more cards in a specific
position in a library at the same time, the owner of those cards may arrange
them in any order. That library's owner doesn't reveal the order". One card
has one position; two at once have none anybody else knows.

Battle 8 (B8-03): Subtlety put Endurance on top of alice's library and neither
player's known cards listed it, before or after the draw. Memory Lapse is off
the deck pool and puts the countered spell there by a different template.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.scenarios.harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def subtlety_board() -> Scenario:
    return (
        Scenario()
        .player(
            "bob",
            hand=["Grizzly Bears"],
            library=["Island", "Island", "Island"],
            battlefield=["Forest", "Forest"],
        )
        .player("alice", hand=["Subtlety"], battlefield=["Island"] * 4)
    )


def subtlety_on_the_bears(scenario: Scenario, *, top: bool):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(top, username="bob")
    scenario.cast_onto_stack("Subtlety", *islands, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    return bears


def test_a_spell_put_on_top_of_its_owners_library_is_known_to_every_player():
    scenario = subtlety_board().build()
    bears = subtlety_on_the_bears(scenario, top=True)

    assert scenario.player("bob").library[0] is bears
    assert known(scenario.game, "alice") == [("Grizzly Bears", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == [("Grizzly Bears", Zone.LIBRARY, 0, False)]


def test_a_spell_put_on_the_bottom_is_known_at_the_bottom():
    scenario = subtlety_board().build()
    bears = subtlety_on_the_bears(scenario, top=False)

    library = scenario.player("bob").library
    assert library[-1] is bears
    assert known(scenario.game, "alice") == [
        ("Grizzly Bears", Zone.LIBRARY, len(library) - 1, False)
    ]


def test_the_card_stays_known_after_it_is_drawn():
    scenario = subtlety_board().build()
    bears = subtlety_on_the_bears(scenario, top=True)

    scenario.draw(username="bob")

    assert bears.zone is Zone.HAND
    assert known(scenario.game, "alice") == [("Grizzly Bears", Zone.HAND, None, True)]


def test_the_card_stops_being_known_once_it_leaves_the_hand():
    """CR 400.7: put into the graveyard, it is a new object in a public zone,
    not a known card in a hidden one."""
    scenario = subtlety_board().build()
    bears = subtlety_on_the_bears(scenario, top=True)
    scenario.draw(username="bob")
    scenario.game.put_into_graveyard(bears)

    assert known(scenario.game, "alice") == []


def test_a_countered_spell_put_on_top_of_its_owners_library_is_known():
    """Off the deck pool: Memory Lapse's "put it on top of its owner's library
    instead of into that player's graveyard" (CR 701.6a's destination,
    replaced by the spell's own text)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], library=["Forest"], battlefield=["Mountain"])
        .player("bob", hand=["Memory Lapse"], library=["Forest"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Memory Lapse", *islands, username="bob", targets=[bolt])
    scenario.pass_until_resolved()

    assert scenario.player("alice").library[0] is bolt
    assert scenario.player("bob").life == 20
    assert known(scenario.game, "bob") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]


def test_a_later_card_put_on_top_ends_the_known_position():
    """CR 701.20d, CR 401.2: a second insertion above it leaves no true
    record of the first card's position."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            library=["Forest"],
            battlefield=["Mountain", "Mountain"],
        )
        .player(
            "bob",
            hand=["Memory Lapse", "Memory Lapse"],
            library=["Forest"],
            battlefield=["Island"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first_mountain, second_mountain = scenario.untapped_sources("Mountain", "Mountain")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="bob")
    first = scenario.cast_onto_stack(
        "Lightning Bolt", first_mountain, targets=[scenario.player("bob")]
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Memory Lapse", *islands[:2], username="bob", targets=[first])
    scenario.pass_until_resolved()
    second = scenario.cast_onto_stack(
        "Lightning Bolt", second_mountain, targets=[scenario.player("bob")]
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Memory Lapse", *islands[2:], username="bob", targets=[second])
    scenario.pass_until_resolved()

    library = scenario.player("alice").library
    assert library[0] is second and library[1] is first
    assert known(scenario.game, "bob") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert [entry.card_id for entry in scenario.game.known_to("bob")] == [second.id]
