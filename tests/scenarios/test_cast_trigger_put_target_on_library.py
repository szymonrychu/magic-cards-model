"""Scenario: a cast trigger's optional targeted action puts a nonland
permanent on top of its owner's library, rather than exiling it or bouncing
it to hand - Lashweed Lurker's own "you may put target nonland permanent on
top of its owner's library."

Lashweed Lurker: "When you cast this spell, you may put target nonland
permanent on top of its owner's library." (Modern).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 608.2d** - a plain "you may" targeted action is a choice made as the
  effect applies; declining it is always legal.
- **CR 401.1/401.2** - a library is a face-down, ordered pile; putting a
  card "on top" is a plain move, never CR 701.24's shuffle.
- **CR 603.3d** - the remainder of putting a triggered ability on the stack
  follows CR 601.2c-d; with no legal target for the mandatory "target
  nonland permanent", the ability is simply removed from the stack.
- **CR 608.2b** - a target no longer in the zone it was in when targeted is
  illegal, and the rest of the resolving ability's effect still happens
  (here: nothing else to happen, so the ability does nothing at all).

`put_ability_targets_on_top_of_owners_library` already existed for a card
targeting a graveyard card (`_PUT_TARGET_FROM_GRAVEYARD_TOP_OF_LIBRARY_RE`)
and is zone-agnostic; only the battlefield-target regex
(`_PUT_TARGET_PERMANENT_TOP_OF_OWNERS_LIBRARY_RE`) was missing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lashweed Lurker"],
            battlefield=["Wastes"] * 8,
        )
        .player("bob", library=["Forest"], battlefield=bob_battlefield)
        .build()
    )


def test_paid_puts_the_target_on_top_of_its_owners_library():
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Lashweed Lurker", [bears])
    scenario.will_take_the_may(True)
    sources = scenario.untapped_sources(*["Wastes"] * 8)

    scenario.cast_onto_stack("Lashweed Lurker", *sources)
    scenario.pass_until_resolved()  # the cast trigger

    bob = scenario.player("bob")
    assert bears.zone is Zone.LIBRARY
    assert bob.library[0] is bears


def test_declined_leaves_the_target_on_the_battlefield():
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Lashweed Lurker", [bears])
    scenario.will_take_the_may(False)
    sources = scenario.untapped_sources(*["Wastes"] * 8)

    scenario.cast_onto_stack("Lashweed Lurker", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_no_legal_target_removes_the_trigger_before_it_reaches_the_stack():
    """With no nonland permanent on the battlefield at all when Lashweed
    Lurker is cast, the mandatory "target nonland permanent" trigger has no
    legal choice and never goes on the stack (CR 603.3d) - the spell itself
    still resolves."""
    scenario = _board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Wastes"] * 8)

    scenario.cast_onto_stack("Lashweed Lurker", *sources)

    assert scenario.stack_names() == ["Lashweed Lurker"]

    scenario.pass_until_resolved()
    assert "Lashweed Lurker" in scenario.battlefield_names()


def test_a_target_removed_in_response_fizzles_the_library_placement():
    """CR 608.2b: the target is legal when chosen but leaves the battlefield
    (destroyed) before the trigger resolves - the ability does nothing, and
    the spell underneath still resolves normally."""
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Lashweed Lurker", [bears])
    scenario.will_take_the_may(True)
    sources = scenario.untapped_sources(*["Wastes"] * 8)

    scenario.cast_onto_stack("Lashweed Lurker", *sources)
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()  # the cast trigger, now targetless

    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()  # Lashweed Lurker itself
    assert "Lashweed Lurker" in scenario.battlefield_names()
