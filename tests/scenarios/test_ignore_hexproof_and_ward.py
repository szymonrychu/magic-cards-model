"""Targeting "as though they didn't have hexproof", and ward that doesn't
trigger (CR 702.11b, 702.11e, 702.21a).

Verified this session with `mise run rules:find`:

- CR 702.11b: "'Hexproof' on a permanent means 'This permanent can't be the
  target of spells or abilities your opponents control.'"
- CR 702.11e: "... Any effect that allows a player to choose a creature with
  hexproof as a target as though it didn't have hexproof will allow a player
  to choose a creature with a 'hexproof from [quality]' ability."
- CR 702.21a: "Ward is a triggered ability. Ward [cost] means 'Whenever this
  permanent becomes the target of a spell or ability an opponent controls,
  counter that spell or ability unless that player pays [cost].'"

Nowhere to Run: "Creatures your opponents control can be the targets of
spells and abilities as though they didn't have hexproof. Ward abilities of
those creatures don't trigger." Glaring Spotlight (Modern/Pioneer legal, in
no deck) is the second printing: "Creatures your opponents control with
hexproof can be the targets of spells and abilities you control as though
they didn't have hexproof." - a narrower "you control" and no ward half.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice_permanent: str | None, bob_creatures: list[str], alice_hand=None) -> Scenario:
    battlefield = ["Mountain", "Mountain", "Swamp"]
    if alice_permanent is not None:
        battlefield.append(alice_permanent)
    return (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand or ["Lightning Bolt"]),
            battlefield=battlefield,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Mountain"],
            battlefield=[*bob_creatures, "Mountain"],
            library=["Mountain"] * 5,
        )
    )


def _bolt(scenario, target) -> None:
    (mountain, *_) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[target])


def test_without_it_hexproof_refuses_the_target():
    """The control: CR 702.11b refuses alice's Bolt."""
    scenario = _board(None, ["Striped Riverwinder"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "bob")

    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_nowhere_to_run_lets_its_controller_target_a_hexproof_creature():
    scenario = _board("Nowhere to Run", ["Striped Riverwinder"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "bob")

    _bolt(scenario, riverwinder)

    assert riverwinder.damage == 3


def test_hexproof_from_a_quality_is_ignored_too():
    """CR 702.11e: Knight of Grace's hexproof from black is a hexproof ability,
    so a black spell may target it as though it had none."""
    scenario = _board("Nowhere to Run", ["Knight of Grace"], alice_hand=["Fatal Push"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Fatal Push", swamp, targets=[knight])

    assert knight.zone is Zone.GRAVEYARD


def test_it_does_not_help_the_opponent_target_its_controllers_creatures():
    """ "Creatures *your opponents* control": alice's own hexproof creature is
    still hexproof to bob."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nowhere to Run", "Striped Riverwinder"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "alice")

    scenario.pass_priority()  # alice passes on an empty stack; bob may act
    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_the_hexproof_half_ends_when_it_leaves():
    """A static ability applies only while on the battlefield (CR 611.3a)."""
    scenario = _board("Nowhere to Run", ["Striped Riverwinder"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "bob")
    scenario.game.destroy(scenario.find("Nowhere to Run", Zone.BATTLEFIELD))

    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="has hexproof"):
        casting.choose_targets([riverwinder])


def test_without_it_ward_triggers():
    """The control: Sunset Saboteur's ward goes on the stack above the Bolt."""
    scenario = _board(None, ["Sunset Saboteur"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saboteur = scenario.creature("Sunset Saboteur", "bob")

    (mountain, *_) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[saboteur])

    assert scenario.stack_names() == ["Lightning Bolt", "Sunset Saboteur's triggered ability"]


def test_ward_of_an_opponents_creature_does_not_trigger():
    """ "Ward abilities of those creatures don't trigger." - the Bolt resolves
    with nothing paid."""
    scenario = _board("Nowhere to Run", ["Sunset Saboteur"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saboteur = scenario.creature("Sunset Saboteur", "bob")

    (mountain, *_) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[saboteur])

    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.pass_until_resolved()
    assert saboteur.zone is Zone.GRAVEYARD  # 3 damage to a 4/1


def test_ward_of_the_controllers_own_creature_still_triggers_for_the_opponent():
    """ "Those creatures" are the opponents' creatures only: bob targeting
    alice's warded creature still meets ward."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nowhere to Run", "Sunset Saboteur"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saboteur = scenario.creature("Sunset Saboteur", "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority()  # alice passes on an empty stack; bob may act
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[saboteur])

    assert len(scenario.stack_names()) == 2


def test_the_enters_trigger_can_target_a_hexproof_creature():
    """Nowhere to Run's own "target creature an opponent controls gets -3/-3
    until end of turn" - its static is already on the battlefield when the
    trigger's target is chosen (CR 603.3d)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Nowhere to Run"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Striped Riverwinder"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "bob")
    scenario.will_choose_targets(riverwinder, source="Nowhere to Run")

    scenario.cast_and_resolve("Nowhere to Run", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(riverwinder).toughness == 2  # a 5/5, -3/-3


def test_glaring_spotlight_lets_its_controller_target_hexproof_creatures():
    """The second printing: "... spells and abilities you control ..."."""
    scenario = _board("Glaring Spotlight", ["Striped Riverwinder"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riverwinder = scenario.creature("Striped Riverwinder", "bob")

    _bolt(scenario, riverwinder)

    assert riverwinder.damage == 3


def test_glaring_spotlight_does_not_switch_ward_off():
    """No ward sentence on Glaring Spotlight - ward still triggers."""
    scenario = _board("Glaring Spotlight", ["Sunset Saboteur"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saboteur = scenario.creature("Sunset Saboteur", "bob")

    (mountain, *_) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[saboteur])

    assert len(scenario.stack_names()) == 2


def test_the_statics_are_credited_as_handled():
    from magic_cards_model.support import card_support
    from tests.cards import card

    for name in ("Nowhere to Run", "Glaring Spotlight"):
        assert "static_unaudited" not in str(card_support(card(name))), name
