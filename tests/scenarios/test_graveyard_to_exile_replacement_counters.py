"""A card bound for an opponent's graveyard is exiled instead, with a counter
on it (CR 614.1a, CR 122.1), and the linked "choose an exiled card ... with a
<kind> counter on it. You may play it this turn without paying its mana cost"
(CR 118.9, CR 601.3).

Dauthi Voidwalker: "If a card would be put into an opponent's graveyard from
anywhere, instead exile it with a void counter on it." and "{T}, Sacrifice
this creature: Choose an exiled card an opponent owns with a void counter on
it. You may play it this turn without paying its mana cost."

CR 614.1a: "Effects that use the word 'instead' are replacement effects." The
"instead" leads its clause here, which is why the old graveyard-exile reader
(Leyline of the Void's trailing "exile it instead") never claimed it. The
shared compiler now reads both word orders and an optional counter rider, so
Leyline of the Void (Modern legal, in no deck) is the second printing that
proves the widened compiler still performs its own counter-less line.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

VOIDWALKER = "Dauthi Voidwalker"


def _board(alice_battlefield=(VOIDWALKER,), bob_hand=("Lightning Bolt",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice_battlefield, "Island"],
            hand=["Thought Scour"],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Mountain", "Grizzly Bears"],
            library=["Lightning Bolt", "Grizzly Bears", "Mountain", "Mountain"],
        )
    )


def test_an_opponents_resolved_spell_is_exiled_with_a_void_counter():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority()  # bob may cast
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert bolt.zone is Zone.EXILE
    assert bolt.counter_count("void") == 1
    assert scenario.player("alice").life == 17


def test_an_opponents_dying_creature_is_exiled_with_a_void_counter():
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE
    assert bears.counter_count("void") == 1


def test_milled_cards_from_the_library_are_exiled_with_void_counters():
    """ "from anywhere" - the library included."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _scour(scenario, "bob")

    exiled = [card for card in scenario.game.exile if card.owner == "bob"]
    assert len(exiled) == 2
    assert all(card.counter_count("void") == 1 for card in exiled)
    assert scenario.player("bob").graveyard == []


def test_its_controllers_own_cards_go_to_the_graveyard():
    """ "an opponent's graveyard" - alice's own cards are untouched."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _scour(scenario, "alice")

    # Two milled Islands and the Thought Scour itself.
    assert len(scenario.player("alice").graveyard) == 3


def test_the_voidwalker_itself_goes_to_its_owners_graveyard():
    scenario = _board().build()
    walker = scenario.creature(VOIDWALKER, "alice")

    scenario.game.destroy(walker)

    assert walker.zone is Zone.GRAVEYARD


def test_leyline_of_the_void_still_exiles_without_a_counter():
    """The second printing on the shared compiler: "If a card would be put
    into an opponent's graveyard from anywhere, exile it instead." - the
    trailing word order, no counter."""
    scenario = _board(alice_battlefield=("Leyline of the Void",)).build()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE
    assert bears.counter_count("void") == 0


def _scour(scenario, who: str) -> None:
    """Thought Scour: "Target player mills two cards. Draw a card." """
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Thought Scour", island, targets=[who])


def _exile_bolt_with_void(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority()
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])
    assert bolt.zone is Zone.EXILE
    return bolt


def test_sacrificing_it_lets_its_controller_cast_a_void_card_for_free():
    scenario = _board().build()
    bolt = _exile_bolt_with_void(scenario)
    walker = scenario.creature(VOIDWALKER, "alice")
    scenario.will_choose_cards(bolt)

    scenario.activate(walker, sacrificing=[walker])
    scenario.pass_until_resolved()

    assert walker.zone is Zone.GRAVEYARD
    casting = scenario.cast("Lightning Bolt", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    # Bob owns it: to bob's graveyard now that no Voidwalker replaces it.
    assert bolt.zone is Zone.GRAVEYARD


def test_a_card_without_a_void_counter_cannot_be_chosen():
    """A card exiled some other way carries no void counter - nothing to
    choose, so no permission is granted."""
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    walker = scenario.creature(VOIDWALKER, "alice")
    # Exiled straight from the battlefield - never graveyard-bound, so the
    # replacement never applied and there is no counter.
    scenario.game.exile_permanent(bears)
    assert bears.counter_count("void") == 0

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.activate(walker, sacrificing=[walker])
    scenario.pass_until_resolved()

    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    with pytest.raises(ValueError):
        casting.use_permission()


def test_a_void_land_can_be_played_as_the_land_drop():
    """ "You may play it" - CR 601.1a's wider verb reaches a land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[VOIDWALKER, "Island"],
            hand=["Thought Scour"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Mountain", "Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _scour(scenario, "bob")
    mountain = next(
        card for card in scenario.game.exile if card.name == "Mountain" and card.owner == "bob"
    )
    assert mountain.counter_count("void") == 1
    walker = scenario.creature(VOIDWALKER, "alice")
    scenario.will_choose_cards(mountain)

    scenario.activate(walker, sacrificing=[walker])
    scenario.pass_until_resolved()
    scenario.play_land("Mountain", username="alice", from_zone=Zone.EXILE)

    assert mountain.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(mountain).username == "alice"


def test_the_permission_ends_with_the_turn():
    """ "this turn" - CR 514.2 ends it at cleanup."""
    scenario = _board().build()
    bolt = _exile_bolt_with_void(scenario)
    walker = scenario.creature(VOIDWALKER, "alice")
    scenario.will_choose_cards(bolt)
    scenario.activate(walker, sacrificing=[walker])
    scenario.pass_until_resolved()

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.cleanup_step()

    casting = scenario.cast("Lightning Bolt", username="alice", from_zone=Zone.EXILE)
    with pytest.raises(ValueError):
        casting.use_permission()


def test_every_clause_is_credited():
    from magic_cards_model.support import card_support
    from tests.cards import card

    support = str(card_support(card(VOIDWALKER)))
    assert "static_unaudited" not in support
    assert "'silent'" not in support
