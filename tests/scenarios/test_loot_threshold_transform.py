"""A loot followed by a graveyard-count check that exiles the source and
returns it transformed - Jace, Vryn's Prodigy:

    {T}: Draw a card, then discard a card. If there are five or more cards in
    your graveyard, exile Jace, then return him to the battlefield transformed
    under his owner's control.

The trailing "If <condition>, exile <this>, then return <it> ..." is read by
the same reader as Ifrit, Warden of Inferno's "Add {R}{R}{R}{R}. If Ifrit has
three or more lore counters on it, exile it, then return it to the battlefield
(front face up)." (proven in `test_saga_named_multi_chapters.py`), with a
leading effect and a condition of a different kind.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 608.2c** - the instructions are followed in the order written, so the
  graveyard is counted after the discard.
- **CR 712.14a** - put onto the battlefield "transformed", a double-faced card
  enters back face up.
- **CR 400.7** - the returned permanent is a new object: Jace, Telepath
  Unbound enters untapped with his printed loyalty and may use a loyalty
  ability that turn.
- **CR 113.7a** - once activated, the ability resolves even if Jace has left,
  but the exile-and-return has no Jace to act on.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

JACE = "Jace, Vryn's Prodigy"


def _jace(graveyard_size: int, *, library=("Island", "Island", "Island")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"],
            battlefield=[JACE],
            graveyard=["Forest"] * graveyard_size,
            library=list(library),
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    return scenario, jace


def _loot(scenario, jace):
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "alice"), username="alice")
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()


def test_the_discard_that_makes_five_flips_jace():
    scenario, jace = _jace(4)
    stamp = jace.zone_change_stamp
    _loot(scenario, jace)

    assert len(scenario.player("alice").graveyard) == 5
    assert jace.zone is Zone.BATTLEFIELD
    assert jace.transformed is True
    assert jace.name == "Jace, Telepath Unbound"
    assert jace.zone_change_stamp != stamp


def test_four_cards_after_the_discard_is_not_enough():
    scenario, jace = _jace(3)
    _loot(scenario, jace)

    assert len(scenario.player("alice").graveyard) == 4
    assert jace.name == JACE
    assert jace.transformed is False
    assert jace.tapped is True
    assert len(scenario.player("alice").hand) == 1


def test_the_count_is_taken_at_resolution_not_activation():
    """Three at activation, one more milled before it resolves: the discard
    makes five and Jace flips."""
    scenario, jace = _jace(3)
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "alice"), username="alice")
    scenario.activate(jace, index=0, username="alice")
    top = scenario.player("alice").library[-1]
    scenario.game.put_into_graveyard(top)
    scenario.pass_until_resolved()

    assert jace.transformed is True


def test_the_returned_jace_is_a_fresh_planeswalker():
    """CR 400.7: untapped, with his printed loyalty of 5, and free to activate
    a loyalty ability this very turn."""
    scenario, jace = _jace(4)
    _loot(scenario, jace)

    assert jace.tapped is False
    assert jace.counters[Counter.LOYALTY] == 5
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(jace, index=0, username="alice", targets=[bears])
    scenario.pass_until_resolved()
    assert jace.counters[Counter.LOYALTY] == 6


def test_a_jace_gone_before_resolution_is_not_brought_back():
    """CR 113.7a: the loot still happens; the return needs the Jace that
    activated it, and he is in his owner's hand."""
    scenario, jace = _jace(4)
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "alice"), username="alice")
    scenario.activate(jace, index=0, username="alice")
    scenario.game.return_to_hand(jace)
    scenario.pass_until_resolved()

    assert jace.zone is Zone.HAND
    assert len(scenario.player("alice").graveyard) == 5
