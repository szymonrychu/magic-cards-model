"""Judge scenarios: targets that stop being legal while the spell waits.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#814** - Chaos Warp vs. Commander (the target left the zone; the spell is
  countered on resolution)
- **DDR#694** - Tom Bombadil + Elspeth Conquers Death (some targets illegal, at
  least one still legal)
- **DDR#71** - Electrolyze + Mother of Runes (protection makes a chosen target
  illegal after the fact)

CR 608.2b is the whole file: as a spell resolves it rechecks its targets, "a
target that's no longer in the zone it was in when it was targeted is illegal",
and a spell with no legal targets left does not resolve. Every CR number here
was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_bolt_whose_only_target_was_exiled_in_response_does_nothing():
    """DDR#814: the target changed zones, so the spell is countered by the rules.

    CR 608.2b: the target is no longer in the zone it was in when it was
    targeted, so it is illegal; with no legal targets left the spell "doesn't
    resolve" and is put into its owner's graveyard from the stack. None of its
    effects happen - not even the ones that do not mention the target.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Swords to Plowshares"], battlefield=["Plains", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bears])

    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", plains, username="bob", targets=[bears])

    scenario.resolve_top()  # Swords resolves first: last in, first out (CR 608)
    assert bears.zone is Zone.EXILE

    scenario.resolve_top()  # and now the Bolt has nothing legal left

    assert spell.zone is Zone.GRAVEYARD
    assert spell.id in scenario.game.fizzled
    assert scenario.player("bob").life == 20, "no effects at all, not even redirected ones"


def test_a_bolt_still_resolves_if_its_target_merely_gained_damage():
    """The control: only *illegality* stops resolution, not any change (CR 608.2b).

    "Other changes to the game state may cause a target to no longer be legal" -
    but a creature that simply took damage is still a creature on the
    battlefield, so the Bolt resolves normally.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain", "Mountain"]
        )
        .player("bob", battlefield=["Questing Beast"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.creature("Questing Beast", "bob")

    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", first, username="alice", targets=[beast])
    scenario.cast_and_resolve("Lightning Bolt", second, username="alice", targets=[beast])
    assert beast.damage == 3 and beast.zone is Zone.BATTLEFIELD

    scenario.resolve_top()

    assert spell.id not in scenario.game.fizzled
    assert beast.zone is Zone.GRAVEYARD


def test_a_two_target_spell_resolves_for_whichever_target_is_still_legal():
    """DDR#694: one illegal target does not counter the spell.

    CR 608.2b: the spell is only countered if *all* its targets are illegal. It
    otherwise resolves, doing as much as it can for the targets that remain -
    and its untargeted half (Electrolyze's card draw) happens either way.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Electrolyze"],
            battlefield=["Island", "Mountain", "Mountain"],
            library=["Preordain"],
        )
        .player(
            "bob",
            hand=["Swords to Plowshares"],
            battlefield=["Plains", "Grizzly Bears", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doomed, survivor = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")

    sources = scenario.untapped_sources("Island", "Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Electrolyze", *sources, username="alice", targets=[doomed, survivor])

    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", plains, username="bob", targets=[doomed])
    scenario.resolve_top()

    scenario.resolve_top()

    assert survivor.damage == 1
    assert len(scenario.player("alice").hand) == 1, "the draw happens regardless"


@pytest.mark.xfail(
    strict=True,
    reason="protection is not modelled (CR 702.16) and non-mana activated abilities are "
    "not activatable, so Mother of Runes cannot make the target illegal",
)
def test_protection_gained_in_response_makes_the_creature_an_illegal_target():
    """DDR#71: the target stays in its zone but stops being legal anyway.

    CR 702.16b: "A permanent or player with protection can't be targeted by
    spells with the stated quality." Mother of Runes grants protection from red
    after the Bolt is already on the stack; CR 608.2b rechecks legality on
    resolution and finds none, so the Bolt is countered.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Plains", "Mother of Runes"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.creature("Mother of Runes", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[mother])

    # bob activates Mother of Runes targeting herself, choosing red.
    scenario.game.activate_ability(mother, 0, "bob", targets=[mother])
    scenario.resolve_top()

    scenario.resolve_top()

    assert spell.id in scenario.game.fizzled
    assert mother.zone is Zone.BATTLEFIELD
    assert mother.damage == 0
