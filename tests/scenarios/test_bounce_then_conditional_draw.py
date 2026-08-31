"""Boomerang Basics: "Return target nonland permanent to its owner's hand. If
you controlled that permanent, draw a card."

One instruction printed as two sentences, which is what
`_parse_return_target_then_conditional_draw` in `machines/effects.py` reads as
a unit. "That permanent" refers back to whatever the first sentence returned,
and the question the second sentence asks - *who controlled it* - has an answer
only while it is still on the battlefield: the moment it reaches a hand it is a
new object (CR 400.7) and a card in a hand has no controller at all (CR 108.4,
CR 109.4).

The happy path is the first test. The rest of the file is the conditional's
edges: the opponent's permanent that draws nothing, the target that is gone by
resolution and so does neither half, the ordering of the controller question
against the return, and the land the spell may not name at all.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written."
- **CR 608.2b** - "If the spell or ability specifies targets, it checks whether
  the targets are still legal. A target that's no longer in the zone it was in
  when it was targeted is illegal. ... The spell or ability is countered if all
  its targets ... are now illegal."
- **CR 115.2** - "Only permanents are legal targets for spells and abilities,
  unless a spell or ability (a) specifies that it can target an object in
  another zone or a player ..." - "nonland permanent" is that, narrowed by card
  type.
- **CR 601.2c** - "The player announces their choice of an appropriate object
  or player for each target the spell requires", which is where an illegal
  choice is refused.
- **CR 108.4** - "A card doesn't have a controller unless that card represents
  a permanent or spell."
- **CR 108.4a** - "If anything asks for the controller of a card that doesn't
  have one (because it's not a permanent or spell), use its owner instead."
- **CR 109.4** - "Only objects on the stack or on the battlefield have a
  controller. Objects that are neither on the stack nor on the battlefield
  aren't controlled by any player."
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence."
- **CR 400.3** - "If an object would go to any library, graveyard, or hand
  other than its owner's, it goes to its owner's corresponding zone."
- **CR 110.2** - "A permanent's controller is, by default, the player under
  whose control it entered the battlefield."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_bouncing_your_own_permanent_returns_it_and_draws_a_card():
    """Both sentences in printed order (CR 608.2c): the permanent goes back to
    its owner's hand, and because alice controlled it she draws.

    CR 110.2 is what makes "you controlled that permanent" true here - the
    Bears entered under alice's control and never changed hands.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Boomerang Basics"],
            battlefield=["Island", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (island,) = scenario.untapped_sources("Island")
    bears = scenario.creature("Grizzly Bears", "alice")
    boomerang = scenario.cast_and_resolve("Boomerang Basics", island, targets=[bears])

    assert boomerang.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.HAND
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears", "Forest"]
    assert scenario.player("alice").library == [], "the draw really came off the library"


# --------------------------------------------------------------------------
# The conditional half
# --------------------------------------------------------------------------


def test_bouncing_an_opponents_permanent_draws_nothing():
    """The clause "if you controlled that permanent" is a condition, not
    decoration.

    Bob's Sol Ring is returned all the same - the first sentence is
    unconditional - but the second sentence's condition is false, so alice's
    library is untouched. Note the two halves separate cleanly: the return
    happens on the object's own terms (CR 400.3 sends it to *bob's* hand), and
    only the draw is gated on who controlled it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Boomerang Basics"], battlefield=["Island"], library=["Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (island,) = scenario.untapped_sources("Island")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    scenario.cast_and_resolve("Boomerang Basics", island, targets=[ring])

    assert scenario.zones_containing(ring) == ["bob:hand"], "CR 400.3: its owner's hand"
    assert scenario.player("alice").hand == [], "no card was drawn"
    assert [state.name for state in scenario.player("alice").library] == ["Forest"]


def test_the_controller_question_is_answered_before_the_return():
    """CR 109.4: "Only objects on the stack or on the battlefield have a
    controller. Objects that are neither on the stack nor on the battlefield
    aren't controlled by any player." CR 108.4 says the same of a card, and
    CR 108.4a's fallback - "use its owner instead" - is a different question
    from the one this card asks.

    So "if you controlled that permanent" can only be answered while the target
    is still a permanent. By the time the second sentence is reached the object
    is a card in a hand, and CR 400.7 has already made it a new object with no
    relation to the permanent it was. The observable proof that the engine asks
    in the right order is this test's pairing: the card ends up in the hand
    *and* the draw still happened, which an after-the-return reading could not
    produce from an object that no longer has a controller.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Boomerang Basics"],
            battlefield=["Island", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (island,) = scenario.untapped_sources("Island")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Boomerang Basics", island, targets=[bears])

    assert scenario.zones_containing(bears) == ["alice:hand"], "it is no longer a permanent"
    assert bears not in scenario.game.battlefield
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears", "Forest"]


def test_a_target_gone_by_resolution_returns_nothing_and_draws_nothing():
    """CR 608.2b: a target that is no longer in the zone it was in when it was
    targeted is illegal, and a spell whose every target is illegal is
    countered.

    Bob answers the Boomerang by killing his own creature. There is no "that
    permanent" left for the second sentence to have been controlled, so neither
    half happens: nothing comes back, and alice's library still holds the card
    she would have drawn had she been the one controlling the target.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Boomerang Basics"], battlefield=["Island"], library=["Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (island,) = scenario.untapped_sources("Island")
    bears = scenario.creature("Grizzly Bears", "bob")
    boomerang = scenario.cast_onto_stack("Boomerang Basics", island, targets=[bears])

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert boomerang.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD, "the return found nothing to return"
    assert scenario.player("bob").hand == []
    assert scenario.player("alice").hand == [], "and nothing was drawn"
    assert [state.name for state in scenario.player("alice").library] == ["Forest"]


# --------------------------------------------------------------------------
# What the spell may name at all
# --------------------------------------------------------------------------


def test_a_land_is_not_a_legal_target():
    """CR 115.2 makes every permanent a legal target by default; "nonland
    permanent" is the printed narrowing that takes lands back out.

    CR 601.2c puts the choice at announcement, so naming a land is refused
    there rather than fizzling later - the spell never reaches the stack, the
    land stays put, and Boomerang Basics is still in alice's hand.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Boomerang Basics"], battlefield=["Island"], library=["Forest"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.find("Forest", Zone.BATTLEFIELD)

    try:
        scenario.cast("Boomerang Basics", targets=[forest])
    except ValueError as error:
        assert "illegal target" in str(error)
    else:  # pragma: no cover - the assertion below reports the failure
        raise AssertionError("a land was accepted as a target")

    assert forest.zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Boomerang Basics"]
    assert scenario.game.stack == []
