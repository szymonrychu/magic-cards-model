"""Judge scenarios: the ante zone, and the cards that move things into it.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#666** - How does Ante Work?

Ante is still in the Comprehensive Rules (CR 407), and the episode is a tour of
it: the ante zone is a public zone (CR 400.2), only a card's owner may ante a
card (CR 407.4), and an ante card's own ability fails closed when the ante it
depends on cannot happen.

The zone itself is built now: `Zone.ANTE` is CR 400.1's optional eighth, shared
and public, and `Game.ante` is CR 407.4's verb with its owner check. What is
still missing is Jeweled Bird's own effect, which has no entry in
`machines/effects.py`, so the two `xfail` tests below stay red. Jeweled Bird's real oracle
text, confirmed with `resolve_cards`: "Remove this card from your deck before
playing if you're not playing for ante. / {T}: Ante this artifact. If you do,
put all other cards you own from the ante into your graveyard, then draw a
card."

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_seven_rules_zones_are_modelled_and_so_is_ante():
    """CR 400.1: "There are normally seven zones: library, hand, battlefield,
    graveyard, stack, exile, and command. Some older cards also use the ante
    zone."

    The engine models the seven, that optional eighth, and the sideboard - which
    is not a zone at all (CR 400.11a). CR 400.2 makes the ante zone a public
    zone alongside the graveyard, battlefield, stack and exile, which is the
    episode's "all cards in it are face up", and CR 400.1 makes it shared rather
    than one pile per player.
    """
    assert {zone.value for zone in Zone} == {
        "library",
        "hand",
        "battlefield",
        "graveyard",
        "stack",
        "exile",
        "command",
        "ante",
        "sideboard",
    }
    assert Zone.ANTE.is_shared
    assert not Zone.ANTE.is_hidden, "CR 400.2: ante is a public zone"
    assert not Zone.ANTE.is_outside_the_game


def test_only_the_owner_can_ante_a_card():
    """CR 407.4: "To ante an object is to put that object into the ante zone
    from whichever zone it's currently in. The owner of an object is the only
    player who can ante that object."

    The stolen-Bird half of DDR#666, at the level of the verb: bob, who does not
    own the Bird, cannot ante it, and `Game.ante` answers False without moving
    anything - which is what makes Jeweled Bird's own "If you do" false.
    """
    scenario = Scenario().player("alice", battlefield=["Jeweled Bird"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    assert scenario.game.ante(bird, "bob") is False
    assert bird.zone is Zone.BATTLEFIELD
    assert scenario.game.ante_zone == []

    assert scenario.game.ante(bird, "alice") is True
    assert bird.zone is Zone.ANTE
    assert scenario.game.ante_zone == [bird]
    assert bird not in scenario.game.battlefield


def test_anteing_a_card_from_a_hidden_zone_takes_it_out_of_that_zone_too():
    """ "from whichever zone it's currently in" - the ante verb is not a
    battlefield-only move, so a card in hand goes just as readily."""
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    assert scenario.game.ante(bears, "alice") is True

    assert bears.zone is Zone.ANTE
    assert [state.name for state in scenario.player("alice").hand] == []


@pytest.mark.xfail(
    strict=True,
    reason="Zone.ANTE and Game.ante (CR 400.1, CR 407.4) are built now, but "
    "Jeweled Bird's own ability still has no entry in `machines/effects.py` - "
    "there is no activated_effect_for('Jeweled Bird', ...) row - so activating "
    "it resolves and does nothing.",
)
def test_anteing_the_bird_moves_it_out_of_the_battlefield():
    """CR 407.4: "To ante an object is to put that object into the ante zone
    from whichever zone it's currently in."

    Jeweled Bird's own first instruction is to ante itself, so a resolution that
    worked would leave the battlefield without it.
    """
    scenario = Scenario().player("alice", battlefield=["Jeweled Bird"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD


@pytest.mark.xfail(
    strict=True,
    reason="Same remaining gap: with no ('Jeweled Bird', ...) entry in "
    "`machines/effects.py`, nothing calls Game.ante, so the 'If you do' the "
    "rest of the ability hangs off never becomes true and no card is drawn.",
)
def test_the_owner_antes_the_bird_and_draws_a_card():
    """The half of the episode's Jeweled Bird question that is supposed to work.

    CR 407.4: "The owner of an object is the only player who can ante that
    object" - and here the owner is doing it, so the ante happens, and the "If
    you do" clause that follows it does too. The stolen-Bird case the episode
    actually asks about is the mirror image: with the ante refused, that same
    "if you do" is false and *nothing* in the ability happens. This engine
    reaches the stolen-Bird answer by accident (it can never ante anything), so
    only the case it should get right is asserted here.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Grizzly Bears"], battlefield=["Jeweled Bird"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
