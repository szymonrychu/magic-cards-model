"""Judge scenario: discarding to hand size, and why mayhem cannot use it.

From DDR#967 "Discarding Swarm, Being of Bees to Hand Size". Amy has eight
cards in hand, discards Swarm, Being of Bees to maximum hand size at the end of
her turn, and asks whether she can then cast it with its mayhem cost. The
answer is no, and flash is a red herring:

- **CR 703.4n / CR 514.1** - "Immediately after the cleanup step begins, if the
  active player's hand contains more cards than their maximum hand size
  (normally seven), they discard enough cards to reduce their hand size to that
  number." CR 402.2 sets the seven. CR 701.9a: discarding moves the card from
  hand to graveyard.
- **CR 514.3** - "Normally, no player receives priority during the cleanup
  step, so no spells can be cast and no abilities can be activated." Swarm has
  flash, but flash is permission to cast at instant speed *when you have
  priority*, and nobody does here. CR 514.3a is the exception the episode
  points at: a state-based action or a waiting trigger reopens the step with
  priority, and only then would mayhem be castable.
- **CR 702.187a/b** - "Mayhem is a static ability that functions while the card
  with mayhem is in a player's graveyard"; "'Mayhem [cost]' means 'As long as
  you discarded this card this turn, you may cast it from your graveyard by
  paying [cost] rather than paying its mana cost.'"

The engine models the discard and the priority-free cleanup step. It does not
model mayhem at all - the keyword parses as a keyword and grants nothing - so
the second half is `xfail`.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 402.2, CR 500.3, CR 514.1,
CR 514.3, CR 514.3a, CR 701.9a, CR 702.187a, CR 702.187b, CR 703.4n.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: Seven filler cards plus the Swarm makes eight - one over CR 402.2's maximum.
FILLER = ["Lightning Bolt"] * 7


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Swarm, Being of Bees", *FILLER],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
    )


def _to_cleanup_discarding_the_swarm(scenario):
    scenario.start_at(Step.END_STEP)
    scenario.will_discard(scenario.find("Swarm, Being of Bees", Zone.HAND))
    scenario.advance()
    return scenario.find("Swarm, Being of Bees", Zone.GRAVEYARD, "alice")


def test_the_swarm_is_discarded_to_maximum_hand_size_as_cleanup_begins():
    """CR 703.4n's turn-based action, and CR 701.9a's destination.

    Eight cards becomes seven and the named card is in the graveyard - not
    exiled, not on the stack. The choice of *which* card is CR 701.9b's, made
    here through the harness's queued answer.
    """
    scenario = board().build()
    assert scenario.player("alice").maximum_hand_size == 7

    swarm = _to_cleanup_discarding_the_swarm(scenario)

    assert scenario.step is Step.CLEANUP
    assert swarm.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 7


def test_no_player_receives_priority_during_the_cleanup_step():
    """CR 514.3, which is the whole reason the trick fails.

    CR 500.3 names the untap step and "certain cleanup steps" as the steps in
    which no player receives priority; `machines/turn.NO_PRIORITY` is that
    list, and `grants_priority` is how the rest of the engine asks.
    """
    scenario = board().build()
    _to_cleanup_discarding_the_swarm(scenario)

    assert scenario.step is Step.CLEANUP
    assert not scenario.turn.grants_priority


def test_flash_does_not_create_a_priority_window_of_its_own():
    """ "Even though Swarm has flash, that doesn't mean you can cast it anytime
    you want. You have to have priority to cast it."

    Flash is printed on the card and read by the engine; it still leaves the
    cleanup step with nobody holding priority. The two facts are independent,
    and asserting both together is what says flash is not the missing piece.
    """
    scenario = board().build()
    _to_cleanup_discarding_the_swarm(scenario)

    assert "Flash" in card("Swarm, Being of Bees").keywords
    assert not scenario.turn.grants_priority


@pytest.mark.xfail(
    reason=(
        "Mayhem (CR 702.187a/b) is not modelled. The keyword parses off the "
        "printing but nothing turns it into an alternative cost or a permission "
        "to cast from the graveyard, so `Casting.alternative_costs` is empty and "
        "a card discarded this turn offers nothing at the next priority window."
    ),
    strict=True,
)
def test_mayhem_offers_the_discarded_card_from_the_graveyard():
    """CR 702.187b: "you may cast it from your graveyard by paying [cost]
    rather than paying its mana cost", as long as you discarded it this turn.

    Asked at a legal priority window rather than during cleanup, so the only
    thing being tested is mayhem itself.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Swarm, Being of Bees"],
            battlefield=["Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swarm = scenario.find("Swarm, Being of Bees", Zone.GRAVEYARD, "alice")

    casting = Casting(
        spell=swarm,
        caster="alice",
        origin_zone=Zone.GRAVEYARD,
        game=scenario.game,
    )
    assert [str(cost.mana) for cost in casting.alternative_costs] == ["{B}"]


# --------------------------------------------------------------------------
# The cleanup discard is a discard like any other
# --------------------------------------------------------------------------


def test_the_cleanup_discard_is_counted_and_seen_like_every_other_discard():
    """CR 701.9a does not have a quiet variant for the cleanup step.

    `Player.discard_to_maximum_hand_size` used to move the cards itself, so
    the CR 514.1 discard was the one discard in the engine that neither fed
    `Game.cards_discarded_this_turn` (Hollow One's "for each card you've
    cycled or discarded this turn") nor emitted `TriggerEvent.DISCARDS_A_CARD`
    (Captain Howler's "Whenever you discard one or more cards"). It routes
    through `Game.discard_cards` now, so both see it.

    That this matters at all is CR 514.3a: "the game checks to see if any
    state-based actions would be performed and/or any triggered abilities are
    waiting to be put onto the stack ... those abilities are put onto the
    stack and the active player gets priority" - a discard trigger fired
    during cleanup is not the end of the turn swallowing it, it reopens the
    step.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swarm, Being of Bees", *FILLER],
            battlefield=["Swamp", "Swamp", "Captain Howler, Sea Scourge"],
        )
        .player("bob")
        .build()
    )
    _to_cleanup_discarding_the_swarm(scenario)

    assert scenario.game.cards_discarded_this_turn["alice"] == 1

    fired = scenario.stack_names() + [trigger.source_name for trigger in scenario.pending_triggers]
    assert any("Captain Howler" in name for name in fired), fired
